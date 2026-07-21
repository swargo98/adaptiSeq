#!/usr/bin/env python3
"""Aggregate E5 into Fig 5: adaptive Aspera trajectory + fixed-vs-adaptive + sweep.

Reads e5_results.tsv (one row per arm x rep) and logs/trajectories.tsv (per-probe
workers/throughput/efficiency) from --outdir. Robust to partial data; figures
skipped (not fatal) without matplotlib.
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


def _read(p: Path):
    if p.exists() and p.stat().st_size > 0:
        try:
            df = pd.read_csv(p, sep="\t")
            return df if len(df) else None
        except Exception:
            return None
    return None


def results_table(df: pd.DataFrame) -> None:
    g = df.groupby(["panel", "arm"]).agg(
        reps=("rep", "nunique"),
        wall_med=("wall_s", "median"),
        mbps_med=("MBps_verified", "median"),
        runs=("runs_complete", "median"),
        runs_exp=("runs_expected", "max"),
        settle=("settle_workers", lambda s: s.dropna().astype(str).mode().iloc[0]
                if len(s.dropna()) else "NA"),
    ).reset_index()
    print("\n=== Table (Fig 5) — adaptive Aspera, median over reps ===")
    print(f"{'panel':6} {'arm':10} {'reps':>4} {'wall_s':>8} {'MB/s':>7} "
          f"{'runs':>8} {'settle_w':>8}")
    for _, r in g.iterrows():
        runs = f"{int(r.runs)}/{int(r.runs_exp)}"
        print(f"{r.panel:6} {r.arm:10} {int(r.reps):>4} {r.wall_med:8.1f} "
              f"{r.mbps_med:7.2f} {runs:>8} {str(r.settle):>8}")


def fig_trajectory(traj: pd.DataFrame, outdir: Path) -> None:
    """Fig 5a: efficiency vs worker count along the additive-increase path."""
    if not HAVE_MPL or traj is None:
        return
    try:
        # one representative adaptive rep (first that has >1 probe)
        sub = traj[traj["arm"].str.contains("adaptive|eff-0.7", case=False, regex=True)]
        if not len(sub):
            sub = traj
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
        for (arm, rep), g in sub.groupby(["arm", "rep"]):
            g = g.sort_values("workers")
            ax1.plot(g["workers"], g["efficiency"], "o-", label=f"{arm}/{rep}")
            ax2.plot(g["workers"], g["throughput"], "o-", label=f"{arm}/{rep}")
        ax1.axhline(0.70, ls="--", color="gray", lw=1, label="0.70 threshold")
        ax1.set_xlabel("workers (concurrent ascp sessions)")
        ax1.set_ylabel("efficiency = tput / (w × baseline)")
        ax1.set_title("E5a — efficiency per worker count (0.70 = keep/stop line)")
        ax1.legend(fontsize=7)
        ax2.set_xlabel("workers")
        ax2.set_ylabel("aggregate throughput (meter units)")
        ax2.set_title("E5a — aggregate throughput vs concurrent ascp sessions")
        ax2.legend(fontsize=7)
        plt.tight_layout()
        f = outdir / "fig5a_trajectory.png"
        plt.savefig(f, dpi=130); plt.close()
        print(f"  wrote {f}")
    except Exception as exc:
        print(f"  (trajectory figure skipped: {exc})")


def fig_fixed_vs_adaptive(df: pd.DataFrame, outdir: Path) -> None:
    """Fig 5b: aggregate MB/s per fixed -j and the adaptive settle point."""
    if not HAVE_MPL:
        return
    sub = df[df["panel"] == "5b"]
    if not len(sub):
        return
    try:
        g = sub.groupby("arm")["MBps_verified"].median().reindex(
            ["fixed-j1", "fixed-j2", "fixed-j4", "fixed-j8", "adaptive"]).dropna()
        colors = ["#4C78A8"] * (len(g) - 1) + ["#54A24B"]
        ax = g.plot(kind="bar", figsize=(7, 4), color=colors)
        ax.set_ylabel("verified MB/s (aggregate)")
        ax.set_xlabel("arm")
        ax.set_title("E5b — aggregate MB/s: fixed -j sweep vs adaptive (link state varies)")
        plt.tight_layout()
        f = outdir / "fig5b_fixed_vs_adaptive.png"
        plt.savefig(f, dpi=130); plt.close()
        print(f"  wrote {f}")
    except Exception as exc:
        print(f"  (5b figure skipped: {exc})")


def fig_sensitivity(df: pd.DataFrame, outdir: Path) -> None:
    """Fig 5c: settle worker count / MB/s vs efficiency threshold."""
    if not HAVE_MPL:
        return
    sub = df[df["panel"] == "5c"]
    if not len(sub):
        return
    try:
        g = sub.groupby("arm").agg(mbps=("MBps_verified", "median"),
                                   settle=("settle_workers", "median")).reindex(
            ["eff-0.5", "eff-0.7", "eff-0.9"]).dropna(how="all")
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(g.index, g["mbps"], color="#4C78A8")
        ax.set_ylabel("verified MB/s")
        for i, (idx, row) in enumerate(g.iterrows()):
            ax.text(i, row["mbps"], f"settle={row['settle']:.0f}w",
                    ha="center", va="bottom", fontsize=9)
        ax.set_title("E5c — sensitivity to --aspera-efficiency")
        plt.tight_layout()
        f = outdir / "fig5c_sensitivity.png"
        plt.savefig(f, dpi=130); plt.close()
        print(f"  wrote {f}")
    except Exception as exc:
        print(f"  (5c figure skipped: {exc})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="e5_results")
    ap.add_argument("--tsv")
    args = ap.parse_args()
    out = Path(args.outdir)
    df = _read(Path(args.tsv) if args.tsv else out / "e5_results.tsv")
    traj = _read(out / "logs" / "trajectories.tsv")
    if df is None:
        print(f"[warn] no E5 results in {out.resolve()}"); return 1
    results_table(df)
    fig_trajectory(traj, out)
    fig_fixed_vs_adaptive(df, out)
    fig_sensitivity(df, out)
    print(f"\nFigures + table in {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
