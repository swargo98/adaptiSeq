"""System-benchmark runner.

Runs each tool adapter for each accession under the per-second :class:`Sampler`,
writes raw per-second traces + a ``meta.json`` per run, and (via ``report.py``) an
aggregated summary. Standalone: launch as ``python -m sysbench.run_bench ...`` from
the repo root.

    python -m sysbench.run_bench \
        --tools adaptiseq sra-toolkit pysradb \
        --accessions SRR22904257 SRR22904260 \
        --repeats 3 --out sysbench/runs

Fairness controls: files deleted between runs, optional method-order shuffle,
per-run bytes/format recorded so wall-clock/CPU/IO are comparable across tools that
fetch different payloads (.fastq.gz vs .sra).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List

from .phases import PhaseTimeline
from .sampler import Sampler
from .adapters.adaptiseq_adapter import AdaptiseqAdapter
from .adapters.sratoolkit_adapter import SraToolkitAdapter
from .adapters.pysradb_adapter import PysradbAdapter
from .adapters.iseq_adapter import IseqAdapter
from .adapters.edgeturbo_adapter import EdgeturboAdapter

ADAPTERS = {
    "adaptiseq": lambda: AdaptiseqAdapter(),
    "adaptiseq-classic": lambda: AdaptiseqAdapter(engine_args=["--engine", "classic"]),
    "adaptiseq-segmented": lambda: AdaptiseqAdapter(engine_args=["--no-adaptive"]),
    "sra-toolkit": lambda: SraToolkitAdapter(),
    "pysradb": lambda: PysradbAdapter(),
    "iseq": lambda: IseqAdapter(),
    # GSA-only; pass a /gsa/... path as the "accession". Transport stalls from
    # non-NGDC-reachable hosts (see adapter docstring) — reported honestly.
    "edgeturbo": lambda: EdgeturboAdapter(),
}


def _write_trace(path: Path, samples) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["t", "phase", "cpu_pct", "rss_mb", "read_mbps", "write_mbps",
            "net_recv_mbps", "net_sent_mbps", "nprocs"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in samples:
            w.writerow(s.as_row())


def run_one(tool: str, accession: str, rep: int, out: Path,
            interval: float = 1.0) -> Dict:
    adapter = ADAPTERS[tool]()
    reason = adapter.available()
    # Absolute: adapters set the subprocess cwd to rundir AND pass it as -o/-O, so a
    # relative path would nest (wd/wd/...). Resolve once here.
    rundir = (out / tool / accession / f"rep{rep}").resolve()
    if rundir.exists():
        shutil.rmtree(rundir)
    rundir.mkdir(parents=True, exist_ok=True)
    if reason:
        meta = {"tool": tool, "accession": accession, "rep": rep,
                "skipped": True, "reason": reason}
        (rundir / "meta.json").write_text(json.dumps(meta, indent=2))
        return meta

    timeline = PhaseTimeline()
    # Sample the runner process tree (adapter spawns tools as children).
    sampler = Sampler(os.getpid(), timeline, interval=interval)
    t0 = time.time()
    sampler.start()
    try:
        rr = adapter.run(accession, rundir, timeline)
    finally:
        samples = sampler.stop()
    wall = time.time() - t0

    _write_trace(rundir / "trace.csv", samples)
    meta = {
        "tool": tool, "accession": accession, "rep": rep, "skipped": False,
        "ok": rr.ok, "wall_s": round(wall, 2),
        "bytes": rr.bytes_downloaded, "formats": rr.formats,
        "note": rr.note,
        "phase_durations": timeline.durations(),
        "steps": [{"phase": s.phase, "rc": s.returncode,
                   "seconds": round(s.seconds, 2)} for s in rr.steps],
        "n_samples": len(samples),
    }
    (rundir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="adaptiSeq system benchmark")
    ap.add_argument("--tools", nargs="+", default=["adaptiseq", "sra-toolkit"],
                    choices=list(ADAPTERS))
    ap.add_argument("--accessions", nargs="+", required=True)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", type=Path, default=Path("sysbench/runs"))
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--shuffle", action="store_true",
                    help="randomize method order each repeat (cache-fairness)")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    from . import envinfo
    print(f"[bench] env -> {envinfo.write(args.out)}", flush=True)
    results: List[Dict] = []
    for rep in range(1, args.repeats + 1):
        order = list(args.tools)
        if args.shuffle:
            random.shuffle(order)
        for acc in args.accessions:
            for tool in order:
                print(f"[bench] rep{rep} {tool} {acc} …", flush=True)
                m = run_one(tool, acc, rep, args.out, args.interval)
                tag = "skip" if m.get("skipped") else (
                    "ok" if m.get("ok") else "FAIL")
                extra = m.get("reason", "") if m.get("skipped") else \
                    f"{m.get('wall_s')}s {m.get('bytes',0)/1e6:.1f}MB {m.get('formats')}"
                print(f"        -> {tag}: {extra}", flush=True)
                results.append(m)

    (args.out / "index.json").write_text(json.dumps(results, indent=2))
    print(f"[bench] wrote {len(results)} runs to {args.out}")
    print(f"[bench] now run:  python -m sysbench.report --runs {args.out}")


if __name__ == "__main__":
    main()
