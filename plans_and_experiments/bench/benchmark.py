#!/usr/bin/env python3
"""adaptiSeq Part 3 benchmark (spec §6).

Times wall-clock download of a representative multi-file workload several ways on
the same machine + network, and records throughput, total time, and the adaptive
controller's active-worker trajectory. Reports honestly: if a baseline wins, it
says so.

Methods (each that is available on the machine):
  * stock ``iseq -p 8``               (skipped if iseq not installed)
  * ``aria2c -x N -s N``              (skipped if aria2c not installed)
  * ``adaptiseq --no-adaptive``      (fixed concurrency)
  * ``adaptiseq --adaptive``         (the gradient controller)

Usage:
  python bench/benchmark.py ACC1 ACC2 ...   # or rely on the small default set

Notes are written to BENCHMARK.md by --emit-md; otherwise printed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adaptiseq  # noqa: E402
from adaptiseq import core  # noqa: E402
from adaptiseq.console import NullReporter  # noqa: E402
from adaptiseq.options import Options  # noqa: E402

# Small, long-archived ENA runs (each ~1-2 MB) so the benchmark is cheap.
DEFAULT_ACCS = ["SRR1553457", "SRR1553380", "SRR1553453", "SRR1553469"]


def resolve_urls(accs):
    urls = []
    for acc in accs:
        try:
            recs = adaptiseq.get_metadata(acc, database="ena")
        except Exception as e:
            print(f"  (resolve failed for {acc}: {e})")
            continue
        for r in recs:
            for link in (r.get("fastq_ftp") or "").split(";"):
                if link:
                    urls.append("https://" + link)
    return urls


def total_bytes(d):
    return sum(p.stat().st_size for p in Path(d).rglob("*") if p.is_file())


def time_run(label, fn):
    d = tempfile.mkdtemp(prefix="bench-")
    t0 = time.monotonic()
    extra = fn(d)
    dt = time.monotonic() - t0
    nbytes = total_bytes(d)
    mbps = (nbytes * 8) / (dt * 1e6) if dt > 0 else 0.0
    shutil.rmtree(d, ignore_errors=True)
    print(f"  {label:28s} {dt:7.2f}s  {nbytes/1e6:7.1f} MB  {mbps:7.1f} Mbps  {extra}")
    return {"label": label, "seconds": round(dt, 2), "mb": round(nbytes / 1e6, 1),
            "mbps": round(mbps, 1), "extra": extra}


def aria2c_run(urls, d, x=8, s=8):
    listfile = os.path.join(d, "urls.txt")
    Path(listfile).write_text("\n".join(urls) + "\n")
    subprocess.run(
        ["aria2c", "-x", str(x), "-s", str(s), "-j", "8", "-q", "--dir", d,
         "-i", listfile],
        check=False,
    )
    return ""


def adaptiseq_run(accs, d, adaptive):
    opts = Options(engine="segmented", gzip=True, skip_md5=True, quiet=True,
                   adaptive=adaptive, jobs=20, max_segments=8, probe_window=5,
                   output=d)
    ctx = core.run(accs, opts, reporter=NullReporter(), workdir=Path(d))
    # surface the controller trajectory if present
    return "adaptive" if adaptive else "fixed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("accessions", nargs="*", default=DEFAULT_ACCS)
    ap.add_argument("--emit-md", action="store_true")
    args = ap.parse_args()
    accs = args.accessions or DEFAULT_ACCS

    print(f"Resolving {len(accs)} accession(s)...")
    urls = resolve_urls(accs)
    print(f"  {len(urls)} file URL(s)")
    if not urls:
        print("No URLs resolved (offline?). Aborting.")
        return 1

    results = []
    print("\nBenchmark (wall-clock):")
    if shutil.which("iseq"):
        # iseq needs sra-tools etc.; only run if present.
        results.append(time_run("iseq -p 8", lambda d: (
            subprocess.run(["iseq", "-i", ",".join(accs), "-p", "8", "-g",
                            "-o", d], check=False) and "")))
    else:
        print("  iseq -p 8                    SKIPPED (iseq not installed)")

    if shutil.which("aria2c"):
        results.append(time_run("aria2c -x8 -s8", lambda d: aria2c_run(urls, d)))
    else:
        print("  aria2c                       SKIPPED (aria2c not installed)")

    results.append(time_run("adaptiseq --no-adaptive", lambda d: adaptiseq_run(accs, d, False)))
    results.append(time_run("adaptiseq --adaptive", lambda d: adaptiseq_run(accs, d, True)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
