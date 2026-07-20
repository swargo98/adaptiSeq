#!/usr/bin/env python3
"""Aggregate E8 into Fig 6 (traces + task bar) and the resource table (iSeq Fig 1D).

Reads e8_results.tsv (summary rows) and logs/e8_trace_*.tsv (2 Hz curves) from
--outdir. Robust to partial data; figures skipped (not fatal) without matplotlib.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False


def resource_table(df: pd.DataFrame) -> None:
    g = df.groupby(["panel", "tool"]).agg(
        reps=("rep", "nunique"),
        wall_med=("wall_s", "median"),
        peak_rss_med=("peak_rss_mb", "median"),
        mean_cpu_med=("mean_cpu_pct", "median"),
        cpu_core_s_med=("cpu_core_s", "median"),
        write_mbps_med=("mean_write_mbps", "median"),
        setup=("phase_setup_s", "median"),
        data=("phase_data_s", "median"),
        verify=("phase_verify_s", "median"),
    ).reset_index()
    print("\n=== Table (Fig 6) — resource profile, median over reps ===")
    print(f"{'panel':7} {'tool':11} {'reps':>4} {'wall_s':>7} {'peakRSS_MB':>10} "
          f"{'meanCPU%':>8} {'cpu_core_s':>10} {'wr_MB/s':>8} {'setup':>6} "
          f"{'data':>6} {'verify':>6}")
    for _, r in g.iterrows():
        print(f"{r.panel:7} {r.tool:11} {int(r.reps):>4} {r.wall_med:7.1f} "
              f"{r.peak_rss_med:10.1f} {r.mean_cpu_med:8.1f} {r.cpu_core_s_med:10.2f} "
              f"{r.write_mbps_med:8.1f} {r.setup:6.1f} {r.data:6.1f} {r.verify:6.1f}")


def task_bar(df: pd.DataFrame, outdir: Path) -> None:
    if not HAVE_MPL:
        return
    for panel, sub in df.groupby("panel"):
        g = sub.groupby("tool")[["phase_setup_s", "phase_data_s", "phase_verify_s"]].median()
        try:
            ax = g.plot(kind="bar", stacked=True, figsize=(7, 4),
                        color=["#4C78A8", "#F58518", "#54A24B"])
            ax.set_ylabel("seconds")
            ax.set_xlabel("tool")
            ax.set_title(f"E8 {panel} — task time (setup / fetch-data / verify)")
            ax.legend(["setup", "fetch-data", "verify"])
            plt.tight_layout()
            f = outdir / f"fig6b_taskbar_{panel}.png"
            plt.savefig(f, dpi=130); plt.close()
            print(f"  wrote {f}")
        except Exception as exc:
            print(f"  (task bar {panel} skipped: {exc})")


def trace_fig(df: pd.DataFrame, outdir: Path) -> None:
    if not HAVE_MPL:
        return
    logs = outdir / "logs"
    if not logs.exists():
        return
    for panel, sub in df.groupby("panel"):
        # representative rep per tool = the one whose wall is closest to the median
        fig, axes = plt.subplots(3, 1, figsize=(8, 8), sharex=True)
        plotted = False
        for tool, ts in sub.groupby("tool"):
            med = ts["wall_s"].median()
            rep = int(ts.iloc[(ts["wall_s"] - med).abs().argmin()]["rep"])
            arm = ts.iloc[0]["arm"]
            cand = list(logs.glob(f"e8_trace_{panel}_{arm}_rep{rep}.tsv")) or \
                list(logs.glob(f"e8_trace_{panel}_{tool}*_rep{rep}.tsv"))
            if not cand:
                continue
            try:
                d = pd.read_csv(cand[0], sep="\t")
            except Exception:
                continue
            axes[0].plot(d["t_rel_s"], d["rss_mb"], label=tool)
            axes[1].plot(d["t_rel_s"], d["cpu_pct"], label=tool)
            axes[2].plot(d["t_rel_s"], d["write_mbps"], label=tool)
            plotted = True
        if not plotted:
            plt.close(); continue
        axes[0].set_ylabel("RSS (MB)"); axes[0].legend(fontsize=8)
        axes[1].set_ylabel("CPU (%)")
        axes[2].set_ylabel("disk write (MB/s)"); axes[2].set_xlabel("time (s)")
        axes[0].set_title(f"E8 {panel} — resource traces (representative rep)")
        plt.tight_layout()
        f = outdir / f"fig6a_traces_{panel}.png"
        plt.savefig(f, dpi=130); plt.close()
        print(f"  wrote {f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="e8_results")
    ap.add_argument("--tsv")
    args = ap.parse_args()
    out = Path(args.outdir)
    tsv = Path(args.tsv) if args.tsv else out / "e8_results.tsv"
    if not tsv.exists() or tsv.stat().st_size == 0:
        print(f"[warn] no E8 results at {tsv}"); return 1
    df = pd.read_csv(tsv, sep="\t")
    if not len(df):
        print("[warn] empty E8 results"); return 1
    # only summarise arms that produced data
    df = df[df["wall_s"] > 0]
    resource_table(df)
    task_bar(df, out)
    trace_fig(df, out)
    print(f"\nFigures + table in {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
