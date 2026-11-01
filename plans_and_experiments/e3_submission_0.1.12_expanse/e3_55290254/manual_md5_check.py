#!/usr/bin/env python3
"""Gate check: does the md5 verifier agree with a check done by hand?

Every E3 number rests on verify_output.py matching payload md5s against the
dataset manifest. Before a long run, confirm that chain on a few runs using
nothing but `curl` and `hashlib`:

  1. ask ENA's filereport API for each run's fastq URLs and md5s (live);
  2. download every file of the run with curl (no benchmarked tool involved);
  3. hash it and compare with BOTH the live ENA md5 and the manifest md5;
  4. run verify_output.py on the downloaded tree and require it to report
     exactly these runs complete.

Step 3 also catches a stale manifest (ENA re-processed the run since
make_datasets.py was last run) and a mirror serving bytes that do not match
ENA's own md5 -- either would cap every tool's "runs completed" below 100%.

    python bench/e3/manual_md5_check.py --manifest datasets/D1_full_PRJNA916347.manifest
    python bench/e3/manual_md5_check.py --manifest ... --runs SRR22904401 SRR22904341

Default selection is 3 runs, seeded, including one 3-file run when the manifest
has any. Exit status 0 only if everything agrees.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILEREPORT = (
    "https://www.ebi.ac.uk/ena/portal/api/filereport?accession={run}"
    "&result=read_run&fields=run_accession,fastq_ftp,fastq_md5,fastq_bytes&format=tsv"
)


def load_manifest(path: Path) -> dict[str, list[tuple[str, int, str]]]:
    runs: dict[str, list[tuple[str, int, str]]] = {}
    for line in path.read_text().splitlines()[1:]:
        if line.strip():
            run, name, nbytes, md5 = line.split("\t")
            runs.setdefault(run, []).append((name, int(nbytes), md5))
    return runs


def ena_files(run: str) -> list[tuple[str, str]]:
    """[(https_url, md5), ...] for a run, straight from ENA."""
    with urllib.request.urlopen(FILEREPORT.format(run=run), timeout=60) as resp:
        lines = resp.read().decode().splitlines()
    if len(lines) < 2:
        return []
    row = dict(zip(lines[0].split("\t"), lines[1].split("\t")))
    urls = [u for u in row.get("fastq_ftp", "").split(";") if u]
    md5s = [m for m in row.get("fastq_md5", "").split(";") if m]
    return [("https://" + u, m) for u, m in zip(urls, md5s)]


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_runs(manifest: dict, n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    three = sorted(r for r, rows in manifest.items() if len(rows) >= 3)
    rest = sorted(r for r in manifest if r not in three)
    picked = [rng.choice(three)] if three else []
    picked += rng.sample(rest, min(len(rest), n - len(picked)))
    return picked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--runs", nargs="*", help="run accessions to check (default: 3, seeded)")
    ap.add_argument("-n", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--workdir", type=Path, help="keep downloads here (default: temp dir, removed)")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    runs = args.runs or pick_runs(manifest, args.n, args.seed)
    unknown = [r for r in runs if r not in manifest]
    if unknown:
        print(f"not in manifest: {', '.join(unknown)}", file=sys.stderr)
        return 2

    tmp = None
    if args.workdir:
        args.workdir.mkdir(parents=True, exist_ok=True)
        work = args.workdir
    else:
        tmp = tempfile.TemporaryDirectory(prefix="e3_manual_md5_")
        work = Path(tmp.name)

    ok = True
    for run in runs:
        want = {name: md5 for (name, _b, md5) in manifest[run]}
        live = ena_files(run)
        live_md5 = {url.rsplit("/", 1)[1]: md5 for url, md5 in live}
        if live_md5 != want:
            ok = False
            print(f"{run}  MANIFEST STALE: manifest={want} ena_now={live_md5}")
        for url, ena_md5 in live:
            name = url.rsplit("/", 1)[1]
            dest = work / name
            rc = subprocess.run(
                ["curl", "-sS", "--fail", "--retry", "3", "-o", str(dest), url]
            ).returncode
            if rc != 0:
                ok = False
                print(f"{run}  {name}  DOWNLOAD FAILED (curl rc={rc})")
                continue
            got = md5_of(dest)
            verdict = "ok" if got == ena_md5 == want.get(name) else "MISMATCH"
            ok = ok and verdict == "ok"
            print(f"{run}  {name}  got={got}  ena={ena_md5}  manifest={want.get(name)}  {verdict}")

    out = subprocess.run(
        [sys.executable, str(HERE / "verify_output.py"),
         "--manifest", str(args.manifest), "--outdir", str(work), "--jobs", "4"],
        capture_output=True, text=True,
    ).stdout.strip()
    fields = dict(kv.split("=", 1) for kv in out.split())
    agrees = fields.get("runs_complete") == str(len(runs)) and fields.get("extra_files") == "0"
    print(f"verify_output.py: runs_complete={fields.get('runs_complete')} "
          f"(expected {len(runs)})  extra_files={fields.get('extra_files')}  "
          f"{'agrees' if agrees else 'DISAGREES'}")
    ok = ok and agrees

    if tmp is not None:
        tmp.cleanup()
    print("GATE PASS" if ok else "GATE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
