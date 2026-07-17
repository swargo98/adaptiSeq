#!/usr/bin/env python3
"""Build the exact E3 accession lists + fairness manifests from the live ENA API.

Every list committed under `datasets/` is produced by this script, so the paper's
Data Availability section can point at a one-command regeneration. Re-run on
Expanse before the benchmark: public DBs grow, and the manifest must describe the
bytes that actually exist on the day of the run.

For each dataset it writes two artefacts:

  datasets/<name>.txt       one run/experiment accession per line -- fed to every tool
  datasets/<name>.manifest  TSV: run_accession, file_name, bytes, md5

The manifest is the *fairness instrument*. Tools name and lay out their output
differently (fastq-dl renames, fetchngs restructures, kingfisher may emit .sra),
so E3 never trusts a tool's own success report or a naive `du -sb`. It hashes the
output tree and matches against the manifest's md5 set -- name- and
layout-independent. See verify_output.py.

Usage:
    python bench/e3/make_datasets.py [--outdir datasets] [--seed 20260717]
"""

from __future__ import annotations

import argparse
import random
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, NamedTuple

ENA_API = "https://www.ebi.ac.uk/ena/portal/api/filereport"
FIELDS = "run_accession,fastq_bytes,fastq_md5,fastq_ftp"


class Run(NamedTuple):
    acc: str
    files: List[str]   # basenames
    sizes: List[int]
    md5s: List[str]

    @property
    def nbytes(self) -> int:
        return sum(self.sizes)

    @property
    def nfiles(self) -> int:
        return len(self.files)


def fetch_report(accession: str) -> List[Run]:
    """Pull read_run rows for a project/experiment from the ENA portal API."""
    url = f"{ENA_API}?accession={accession}&result=read_run&fields={FIELDS}&format=tsv"
    with urllib.request.urlopen(url, timeout=180) as fh:
        text = fh.read().decode("utf-8", errors="replace")

    runs: List[Run] = []
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        acc, sizes_s, md5s_s, ftp_s = parts[0], parts[1], parts[2], parts[3]
        if not acc or not ftp_s:
            # No ENA mirror (empty fastq_ftp) -> SRA-only run. Callers that want
            # those (D4) handle them separately; they have no fastq bytes to list.
            continue
        ftps = [p for p in ftp_s.split(";") if p]
        sizes = [int(p) for p in sizes_s.split(";") if p]
        md5s = [p for p in md5s_s.split(";") if p]
        if not (len(ftps) == len(sizes) == len(md5s)):
            continue
        runs.append(Run(acc, [u.rsplit("/", 1)[-1] for u in ftps], sizes, md5s))
    return runs


def write(outdir: Path, name: str, runs: List[Run], note: str) -> None:
    lst = outdir / f"{name}.txt"
    man = outdir / f"{name}.manifest"
    lst.write_text("".join(f"{r.acc}\n" for r in runs))
    with man.open("w") as fh:
        fh.write("run_accession\tfile_name\tbytes\tmd5\n")
        for r in runs:
            for f, s, m in zip(r.files, r.sizes, r.md5s):
                fh.write(f"{r.acc}\t{f}\t{s}\t{m}\n")
    nb = sum(r.nbytes for r in runs)
    nf = sum(r.nfiles for r in runs)
    print(f"  {name:22s} runs={len(runs):5d} files={nf:5d} "
          f"total={nb/1e9:8.2f} GB  avg={nb/nf/1e6 if nf else 0:7.1f} MB/file   {note}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="datasets")
    ap.add_argument("--seed", type=int, default=20260717,
                    help="Seed for the D2/D3 subset draws; committed lists used 20260717.")
    ap.add_argument("--d2-runs", type=int, default=8,
                    help="Runs sampled from PRJNA762469 for the byte-dominated panel.")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    # ---- D1: overhead-dominated (PRJNA916347) -------------------------------
    print("D1  PRJNA916347 (overhead-dominated)")
    d1 = fetch_report("PRJNA916347")
    d1.sort(key=lambda r: r.acc)

    # The full list is the ROBUSTNESS workload: ~40 runs ship 3 fastq files
    # (orphan + _1 + _2), which stock iseq drops (multiline-URL wget bug).
    write(outdir, "D1_full_PRJNA916347", d1,
          "robustness panel (3a-robust): runs-completed per tool")

    # The <=2-file subset is the FAIR TIMING workload: every tool can complete it,
    # so wall time / MB/s are apples-to-apples. Splitting these two is what lets us
    # report speed and correctness without either contaminating the other.
    d1_fair = [r for r in d1 if r.nfiles <= 2]
    d1_three = [r for r in d1 if r.nfiles >= 3]
    write(outdir, "D1_fair_PRJNA916347", d1_fair,
          "fair timing panel (3a): all tools can complete")
    write(outdir, "D1_threefile_PRJNA916347", d1_three,
          "the runs iseq drops (E3 robustness call-out / E7e)")

    # ---- D2: byte-dominated (PRJNA762469) -----------------------------------
    # Full D2 is 206 GB. Ten arms x 10 reps would move ~20 TB -- infeasible and
    # pointless: the panel's job is to show the per-run overhead advantage SHRINKS
    # when bytes dominate, which a bounded subset demonstrates just as well.
    print("D2  PRJNA762469 (byte-dominated, seeded subset)")
    d2_all = fetch_report("PRJNA762469")
    d2_all.sort(key=lambda r: r.acc)
    write(outdir, "D2_full_PRJNA762469", d2_all, "reference only -- NOT run at 10 reps")
    d2 = sorted(rng.sample(d2_all, min(args.d2_runs, len(d2_all))), key=lambda r: r.acc)
    write(outdir, "D2_subset_PRJNA762469", d2,
          f"byte-dominated panel (3b), seed={args.seed}")

    # ---- D3: large per-file (PRJNA540705) -----------------------------------
    print("D3  PRJNA540705 (large per-file)")
    d3 = fetch_report("PRJNA540705")
    d3.sort(key=lambda r: r.acc)
    write(outdir, "D3_full_PRJNA540705", d3, "large-file arm (3b-large / feeds E4a)")

    # ---- D4: cross-database mixed -------------------------------------------
    # Exercises every resolver branch in one list. Sizes are deliberately small:
    # this panel tests ROUTING CORRECTNESS + resolution, not raw bandwidth.
    print("D4  mixed cross-database")
    d4_ena = rng.sample(d1_fair, 12)
    # SRA-only: PRJNA48479 returns empty fastq_ftp for 100% of its 11,245 runs,
    # so these runs force the .sra + fasterq-dump branch. Verified 2026-07-17.
    sra_only = ["SRR1031060", "SRR1031066", "SRR1031074",
                "SRR1031080", "SRR1031090", "SRR1031101"]
    # GSA: iSeq's own paper accessions (btae641 Data Availability) -> direct turf
    # comparison on the Huawei-Cloud path. Sizes come from NGDC, not ENA, so these
    # rows are intentionally absent from the manifest.
    gsa = ["CRX095512", "CRX917377"]

    lst = outdir / "D4_mixed.txt"
    with lst.open("w") as fh:
        for r in sorted(d4_ena, key=lambda r: r.acc):
            fh.write(f"{r.acc}\n")
        for a in sra_only + gsa:
            fh.write(f"{a}\n")
    man = outdir / "D4_mixed.manifest"
    with man.open("w") as fh:
        fh.write("run_accession\tfile_name\tbytes\tmd5\n")
        for r in sorted(d4_ena, key=lambda r: r.acc):
            for f, s, m in zip(r.files, r.sizes, r.md5s):
                fh.write(f"{r.acc}\t{f}\t{s}\t{m}\n")
    print(f"  {'D4_mixed':22s} runs={len(d4_ena)+len(sra_only)+len(gsa):5d} "
          f"(ENA={len(d4_ena)} SRA-only={len(sra_only)} GSA={len(gsa)})  "
          "manifest covers the ENA rows only")

    # ---- D0: single-run controls for the meta-jobs / -j sweeps ---------------
    print("D0  sweep workload (D2 subset, 4 runs)")
    d0 = sorted(rng.sample(d2_all, 4), key=lambda r: r.acc)
    write(outdir, "D0_sweep_PRJNA762469", d0, "concurrency sweep (3d): bounded")

    # ---- SMOKE: the 3 smallest D1 runs --------------------------------------
    # Exists so the full harness (every arm, verification, TSV, aggregation) can
    # be exercised end-to-end on Expanse in ~2 minutes BEFORE committing 48 h of
    # walltime. Finding a broken competitor invocation on rep 1 of panel 3a is a
    # 12-hour mistake; finding it here is a coffee break.
    print("SMOKE  (3 smallest D1 runs)")
    smoke = sorted(d1_fair, key=lambda r: r.nbytes)[:3]
    write(outdir, "SMOKE_D1", smoke, "harness validation only -- NOT a result")

    print("\nWrote lists + manifests to", outdir.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
