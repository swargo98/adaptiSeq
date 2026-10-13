#!/usr/bin/env python3
"""E10a/E10b — resolution throughput & overlap value (download stripped out).

adaptiSeq's parallel resolution is `batch.resolve_all(..., meta_jobs=N)`. The
public `resolve()` / CLI `-m` are SERIAL (the parallel path only runs inside the
download batch phase), so isolating C3b means calling `resolve_all` directly — no
bytes are transferred, only metadata/URL resolution. We instrument the real
per-endpoint request counts by spying on `net._run` (the single subprocess seam
every wget goes through), so each row also reports how many ENA/GSA/NCBI requests
the resolution actually issued.

Competitors (iSeq, pysradb, ffq, Kingfisher) have no parallel-resolution mode;
each is a serial per-accession CLI. We time them resolving the same accessions
one-by-one (metadata-only invocation) and report accessions/sec so the number is
comparable to adaptiSeq's.

Emits TSV rows on stdout (schema in EXPERIMENT_PLAN_E10.md §4). One row per
(tool, meta_jobs, rep).
"""
from __future__ import annotations

import argparse
import collections
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from adaptiseq import ratelimits          # noqa: E402
from adaptiseq.batch import resolve_all    # noqa: E402
from adaptiseq.options import Options       # noqa: E402
import adaptiseq.net as _net                # noqa: E402


def _spy_net(counter: collections.Counter):
    """Wrap net._run so every metadata request is counted by endpoint."""
    orig = _net._run

    def spy(cmd):
        url = next((c for c in cmd if isinstance(c, str)
                    and c.startswith(("http", "ftp"))), "")
        ep = ratelimits.endpoint_for_url(url) or "other"
        counter[ep] += 1
        return orig(cmd)

    _net._run = spy
    return orig


def _restore_net(orig):
    _net._run = orig


def run_adaptiseq(accs, meta_jobs):
    """One adaptiSeq parallel-resolution run. Returns (wall_s, n_tasks,
    n_unresolved, endpoint_counter)."""
    opts = Options(gzip=True, database="auto")
    counter = collections.Counter()
    orig = _spy_net(counter)
    try:
        with tempfile.TemporaryDirectory(prefix="e10-aseq-") as td:
            t0 = time.time()
            tasks, unresolved = resolve_all(accs, opts, Path(td),
                                            meta_jobs=meta_jobs)
            wall = time.time() - t0
    finally:
        _restore_net(orig)
    return wall, len(tasks), len(unresolved), counter


def _competitor_cmd(tool, acc, workdir):
    if tool == "iseq":
        return ["iseq", "-i", acc, "-m", "-o", str(workdir)]
    if tool == "pysradb":
        return ["pysradb", "metadata", acc]
    if tool == "ffq":
        return ["ffq", acc]
    if tool == "kingfisher":
        return ["kingfisher", "annotate", "-r", acc]
    raise ValueError(tool)


def run_competitor(tool, accs, timeout_each=90):
    """Serial per-accession resolution for a competitor CLI. Returns
    (wall_s, n_ok, n_fail)."""
    n_ok = n_fail = 0
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix=f"e10-{tool}-") as td:
        for acc in accs:
            cmd = _competitor_cmd(tool, acc, td)
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=timeout_each)
                # Judge by output, not exit code (tools differ): non-trivial
                # stdout OR a written metadata file counts as resolved.
                out = (r.stdout or "") + (r.stderr or "")
                got_file = any(Path(td).glob("*.tsv")) or any(Path(td).glob("*.csv"))
                if len(r.stdout or "") > 40 or got_file:
                    n_ok += 1
                else:
                    n_fail += 1
            except (subprocess.TimeoutExpired, FileNotFoundError):
                n_fail += 1
    return time.time() - t0, n_ok, n_fail


def emit(row):
    print("\t".join(str(x) for x in row), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default="10a")
    ap.add_argument("--dataset", required=True, help="accession list file")
    ap.add_argument("--n", type=int, default=150, help="accessions to use")
    ap.add_argument("--meta-jobs", default="1,3,8,16")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--tools", default="adaptiseq",
                    help="comma list: adaptiseq,iseq,pysradb,ffq,kingfisher")
    ap.add_argument("--n-comp", type=int, default=20,
                    help="accessions for serial competitors")
    ap.add_argument("--comp-reps", type=int, default=2)
    args = ap.parse_args()

    accs_all = [l.strip() for l in open(args.dataset) if l.strip()]
    accs = accs_all[:args.n]
    comp_accs = accs_all[:args.n_comp]
    mjs = [int(x) for x in args.meta_jobs.split(",") if x]
    tools = [t.strip() for t in args.tools.split(",") if t.strip()]
    host = os.uname().nodename.split(".")[0]

    for tool in tools:
        if tool == "adaptiseq":
            for mj in mjs:
                for rep in range(1, args.reps + 1):
                    wall, ntasks, nunres, cnt = run_adaptiseq(accs, mj)
                    aps = len(accs) / wall if wall > 0 else 0.0
                    print(f"[adaptiseq] mj={mj} rep={rep} N={len(accs)} "
                          f"wall={wall:.2f}s acc/s={aps:.2f} tasks={ntasks} "
                          f"reqs={dict(cnt)}", file=sys.stderr)
                    emit([args.panel, Path(args.dataset).stem, "adaptiseq", mj,
                          len(accs), rep, f"{wall:.3f}", f"{aps:.3f}", ntasks,
                          nunres, cnt.get("ena", 0), cnt.get("gsa", 0),
                          cnt.get("ncbi", 0), host, time.strftime("%FT%T")])
        else:
            for rep in range(1, args.comp_reps + 1):
                wall, n_ok, n_fail = run_competitor(tool, comp_accs)
                aps = len(comp_accs) / wall if wall > 0 else 0.0
                print(f"[{tool}] serial rep={rep} N={len(comp_accs)} "
                      f"wall={wall:.2f}s acc/s={aps:.2f} ok={n_ok} fail={n_fail}",
                      file=sys.stderr)
                emit([args.panel, Path(args.dataset).stem, tool, 1,
                      len(comp_accs), rep, f"{wall:.3f}", f"{aps:.3f}", n_ok,
                      n_fail, "", "", "", host, time.strftime("%FT%T")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
