"""Plots for the sysbench results — reproduces the iSeq paper's Fig. 1D style.

Two figure families, written as PNGs into the runs dir:

1. ``phase_timeline_<tool>_<acc>.png`` — per-second stacked view of one run: net
   recv (data rate) + CPU% + RSS over time, with phase bands shaded
   (request/metadata/data/md5). This is the "Send request / Fetch metadata / Fetch
   NGS data / MD5 check" timeline from the paper.
2. ``summary_bars.png`` — grouped bars across tools: wall time, peak CPU%, peak RSS,
   mean data-phase throughput (the paper's execution-time/memory/CPU/IO bars).

matplotlib only; no seaborn/pandas. Import-guarded so the rest of sysbench works
without it.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PHASE_COLORS = {
    "request": "#cfe8ff", "metadata": "#ffe7ba",
    "data": "#c9f2c9", "md5": "#f3cfe8", "overlapped": "#eeeeee", "idle": "#fafafa",
}


def _load(runs: Path):
    out = []
    for meta_path in runs.rglob("meta.json"):
        meta = json.loads(meta_path.read_text())
        if meta.get("skipped"):
            continue
        rows = []
        tp = meta_path.parent / "trace.csv"
        if tp.exists():
            with tp.open() as f:
                for r in csv.DictReader(f):
                    rows.append({k: (r[k] if k == "phase" else float(r[k])) for k in r})
        out.append((meta, rows))
    return out


def plot_phase_timeline(meta, rows, dest: Path):
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ts = [r["t"] for r in rows]
    # shade phase bands
    cur = rows[0]["phase"]
    start = rows[0]["t"]
    for r in rows[1:] + [None]:
        if r is None or r["phase"] != cur:
            end = (r["t"] if r else ts[-1])
            ax.axvspan(start, end, color=PHASE_COLORS.get(cur, "#eee"), alpha=0.7,
                       zorder=0)
            if r is not None:
                cur, start = r["phase"], r["t"]
    ax.plot(ts, [r["net_recv_mbps"] for r in rows], "-o", ms=3, color="#1f77b4",
            label="net recv MB/s")
    ax.plot(ts, [r["write_mbps"] for r in rows], "-s", ms=3, color="#2ca02c",
            label="disk write MB/s")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("MB/s")
    ax2 = ax.twinx()
    ax2.plot(ts, [r["cpu_pct"] for r in rows], "--", color="#d62728", label="CPU %")
    ax2.plot(ts, [r["rss_mb"] for r in rows], ":", color="#9467bd", label="RSS MB")
    ax2.set_ylabel("CPU % / RSS MB")
    ax.set_title(f"{meta['tool']} — {meta['accession']} "
                 f"({meta['bytes']/1e6:.0f} MB {','.join(meta.get('formats', []))})")
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], loc="upper right", fontsize=8)
    # phase legend
    handles = [plt.Rectangle((0, 0), 1, 1, color=PHASE_COLORS[p])
               for p in ("request", "metadata", "data", "md5")]
    ax.legend  # keep first legend; add phase legend below
    fig.legend(handles, ["request", "metadata", "data", "md5"],
               loc="lower center", ncol=4, fontsize=8, frameon=False)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(dest, dpi=120)
    plt.close(fig)
    return dest


def plot_summary_bars(data, dest: Path):
    by_tool = defaultdict(list)
    for meta, rows in data:
        by_tool[meta["tool"]].append((meta, rows))
    tools = sorted(by_tool)
    if not tools:
        return None
    import statistics as st

    def agg(metas_rows, fn):
        vals = [fn(m, r) for m, r in metas_rows if r or fn(m, r) is not None]
        vals = [v for v in vals if v is not None]
        return st.mean(vals) if vals else 0

    wall = [agg(by_tool[t], lambda m, r: m["wall_s"]) for t in tools]
    peak_cpu = [agg(by_tool[t], lambda m, r: max((x["cpu_pct"] for x in r), default=0))
                for t in tools]
    peak_rss = [agg(by_tool[t], lambda m, r: max((x["rss_mb"] for x in r), default=0))
                for t in tools]
    data_tp = [agg(by_tool[t], lambda m, r: st.mean(
        [x["net_recv_mbps"] for x in r if x["phase"] == "data"] or [0])) for t in tools]

    fig, axes = plt.subplots(1, 4, figsize=(14, 3.8))
    for ax, vals, title, unit in zip(
            axes, [wall, peak_cpu, peak_rss, data_tp],
            ["wall time", "peak CPU", "peak RSS", "data-phase throughput"],
            ["s", "%", "MB", "MB/s"]):
        ax.bar(tools, vals, color="#4c72b0")
        ax.set_title(title)
        ax.set_ylabel(unit)
        ax.tick_params(axis="x", rotation=45, labelsize=8)
    fig.tight_layout()
    fig.savefig(dest, dpi=120)
    plt.close(fig)
    return dest


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=Path("sysbench/runs"))
    args = ap.parse_args(argv)
    data = _load(args.runs)
    plotsdir = args.runs / "plots"
    plotsdir.mkdir(parents=True, exist_ok=True)
    n = 0
    for meta, rows in data:
        dest = plotsdir / f"phase_timeline_{meta['tool']}_{meta['accession'].replace('/', '_')}.png"
        if plot_phase_timeline(meta, rows, dest):
            n += 1
    plot_summary_bars(data, plotsdir / "summary_bars.png")
    print(f"[plot] wrote {n} timelines + summary_bars.png to {plotsdir}")


if __name__ == "__main__":
    main()
