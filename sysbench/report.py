"""Aggregate sysbench raw traces into a per-phase, per-tool summary.

Reads the per-run ``trace.csv`` + ``meta.json`` written by ``run_bench`` and emits:
* a console/markdown table of mean/peak CPU, mean/peak RSS, mean read/write MB/s,
  net MB/s, total bytes, wall time — overall and **broken down per phase**;
* ``RESULTS.md`` in the runs dir.

Pure stdlib (no pandas) so it runs anywhere. Plots are optional (matplotlib) and
skipped if it is not installed.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

PHASES = ("request", "metadata", "data", "md5")


def _load_traces(runs: Path):
    runs_data = []
    for meta_path in runs.rglob("meta.json"):
        meta = json.loads(meta_path.read_text())
        if meta.get("skipped"):
            runs_data.append((meta, []))
            continue
        trace_path = meta_path.parent / "trace.csv"
        rows = []
        if trace_path.exists():
            with trace_path.open() as f:
                for r in csv.DictReader(f):
                    rows.append({k: (r[k] if k == "phase" else float(r[k]))
                                 for k in r})
        runs_data.append((meta, rows))
    return runs_data


def _phase_stats(rows: List[dict]) -> Dict[str, dict]:
    by_phase = defaultdict(list)
    for r in rows:
        by_phase[r["phase"]].append(r)
    out = {}
    for ph, rs in by_phase.items():
        out[ph] = {
            "secs": len(rs),
            "cpu_mean": st.mean(x["cpu_pct"] for x in rs) if rs else 0,
            "cpu_peak": max((x["cpu_pct"] for x in rs), default=0),
            "rss_mean": st.mean(x["rss_mb"] for x in rs) if rs else 0,
            "rss_peak": max((x["rss_mb"] for x in rs), default=0),
            "read_mean": st.mean(x["read_mbps"] for x in rs) if rs else 0,
            "write_mean": st.mean(x["write_mbps"] for x in rs) if rs else 0,
            "net_recv_mean": st.mean(x["net_recv_mbps"] for x in rs) if rs else 0,
        }
    return out


def aggregate(runs: Path):
    data = _load_traces(runs)
    # group by tool
    by_tool = defaultdict(list)
    for meta, rows in data:
        by_tool[meta["tool"]].append((meta, rows))
    summary = {}
    for tool, entries in by_tool.items():
        ran = [(m, r) for m, r in entries if not m.get("skipped")]
        if not ran:
            summary[tool] = {"skipped": entries[0][0].get("reason", "skipped")}
            continue
        all_rows = [r for _, rows in ran for r in rows]
        walls = [m["wall_s"] for m, _ in ran]
        byts = [m["bytes"] for m, _ in ran]
        summary[tool] = {
            "n_runs": len(ran),
            "wall_mean": st.mean(walls), "wall_sd": st.pstdev(walls),
            "bytes_mean": st.mean(byts),
            "formats": sorted({f for m, _ in ran for f in m.get("formats", [])}),
            "overall": _phase_stats(all_rows).get("overall", {}),
            "phases": {ph: _phase_stats([r for r in all_rows if r["phase"] == ph]).get(ph, {})
                       for ph in PHASES},
        }
    return summary


def render_md(summary: dict) -> str:
    L = ["# adaptiSeq system benchmark — results", "",
         "Per-second resource sampling of each tool's process tree, attributed to "
         "the four task phases (request / metadata / data / md5). "
         "`*_mbps` columns are **megabytes/s** (decimal MB). Net is system-wide.", ""]
    L.append("## Headline (per run, mean ± sd)")
    L.append("")
    L.append("| tool | runs | wall s | bytes MB | formats |")
    L.append("|---|---|---|---|---|")
    for tool, s in summary.items():
        if "skipped" in s:
            L.append(f"| {tool} | — | _skipped: {s['skipped']}_ | | |")
            continue
        L.append(f"| {tool} | {s['n_runs']} | {s['wall_mean']:.1f}±{s['wall_sd']:.1f} "
                 f"| {s['bytes_mean']/1e6:.1f} | {','.join(s['formats'])} |")
    L.append("")
    L.append("## Per-phase resource breakdown")
    L.append("")
    L.append("| tool | phase | secs | CPU% mean/peak | RSS MB mean/peak | "
             "read MB/s | write MB/s | net recv MB/s |")
    L.append("|---|---|---|---|---|---|---|---|")
    for tool, s in summary.items():
        if "skipped" in s:
            continue
        for ph in PHASES:
            p = s["phases"].get(ph) or {}
            if not p:
                continue
            L.append(f"| {tool} | {ph} | {p.get('secs',0)} | "
                     f"{p.get('cpu_mean',0):.0f}/{p.get('cpu_peak',0):.0f} | "
                     f"{p.get('rss_mean',0):.0f}/{p.get('rss_peak',0):.0f} | "
                     f"{p.get('read_mean',0):.2f} | {p.get('write_mean',0):.2f} | "
                     f"{p.get('net_recv_mean',0):.2f} |")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=Path("sysbench/runs"))
    args = ap.parse_args(argv)
    summary = aggregate(args.runs)
    md = render_md(summary)
    (args.runs / "RESULTS.md").write_text(md)
    print(md)
    print(f"\n[report] wrote {args.runs / 'RESULTS.md'}")


if __name__ == "__main__":
    main()
