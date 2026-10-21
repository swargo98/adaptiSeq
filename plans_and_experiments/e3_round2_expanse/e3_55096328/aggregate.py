#!/usr/bin/env python3
"""Aggregate the E3 tidy TSV into the paper's numbers and Fig 3.

Reports MEDIAN + IQR (never the mean): download timings are right-skewed by
transient archive slowness, and one bad draw would otherwise move a bar.
EXPERIMENT_PLAN §12.3.

Segregation rule (§12.2): rows whose `format` is not pure `gz` fetched something
else (.sra, decompressed fastq) and are NOT comparable on wall time. They are
reported in a separate block rather than dropped -- what a tool chose to fetch is
a finding, not an inconvenience.

    python bench/e3/aggregate.py --tsv e3_results.tsv --outdir .
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas required: conda install pandas")

PANEL_TITLES = {
    "3a": "3a  Overhead-dominated (D1_fair: 201 runs, 4.4 GB, ~22 MB/file)",
    "3r": "3r  Robustness (D1_full: 241 runs incl. 40 three-file runs)",
    "3b": "3b  Byte-dominated (D2_subset: 8 runs, 25.9 GB, ~1.6 GB/file)",
    "3c": "3c  Cross-database (D4_mixed: ENA + SRA-only + GSA)",
    "3d": "3d  Worker sweep -j {4,8,16} (D0_sweep: 8 files, 11.9 GB)",
    "3s": "3s  Connections-per-worker --max-segments {4,8,16} (D3_seg: 2 x 11.5 GB)",
}


def iqr(s: pd.Series) -> float:
    return float(s.quantile(0.75) - s.quantile(0.25))


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("arm", sort=False)
    out = pd.DataFrame({
        "n": g.size(),
        "wall_med": g["wall_s"].median().round(1),
        "wall_iqr": g["wall_s"].apply(iqr).round(1),
        "MBps_med": g["MBps_verified"].median().round(2),
        "MBps_iqr": g["MBps_verified"].apply(iqr).round(2),
        "runs_ok_med": g["runs_complete"].median(),
        "runs_exp": g["runs_expected"].max(),
        "peak_rss_MB": (g["peak_rss_kb"].median() / 1024).round(0),
        "cpu_pct_med": g["cpu_pct"].median().round(0),
        # Instantaneous concurrency actually offered to the archive (established
        # sockets), sampled identically for every arm. `conc_host_max` is the
        # good-citizen number: what a single host saw at peak.
        "conc_med": g["conc_med"].median() if "conc_med" in df else 0,
        "conc_max": g["conc_max"].max() if "conc_max" in df else 0,
        "conc_host_max": g["conc_per_host_max"].max() if "conc_per_host_max" in df else 0,
        # Workers != connections (see EXPERIMENT_PLAN_E3 §7b): gate.active is the
        # permitted pool size; conc_* is sockets on the wire. adaptiSeq only.
        "workers_max": g["workers_max"].max() if "workers_max" in df else 0,
        "timeouts": g["status"].apply(lambda s: (s == "TIMEOUT").sum()),
        "nonzero_rc": g["status"].apply(lambda s: ((s != "ok") & (s != "TIMEOUT")).sum()),
        "formats": g["format"].apply(lambda s: ",".join(sorted(set(s)))),
    })
    out["success_pct"] = (100 * out["runs_ok_med"] / out["runs_exp"].where(out["runs_exp"] > 0)).round(1)
    return out.sort_values("MBps_med", ascending=False)


def add_speedup(summ: pd.DataFrame) -> pd.DataFrame:
    """Speedup vs stock iseq -- the headline claim's denominator."""
    if "iseq" not in summ.index:
        return summ
    base_wall = summ.loc["iseq", "wall_med"]
    base_mbps = summ.loc["iseq", "MBps_med"]
    if base_wall and base_wall > 0:
        summ["speedup_vs_iseq"] = (base_wall / summ["wall_med"]).round(2)
    if base_mbps and base_mbps > 0:
        summ["MBps_x_iseq"] = (summ["MBps_med"] / base_mbps).round(2)
    return summ


def plot_panel(df: pd.DataFrame, panel: str, outdir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    clean = df[df["format"] == "gz"]
    if clean.empty:
        return
    order = (clean.groupby("arm")["MBps_verified"].median()
                  .sort_values(ascending=True).index.tolist())
    data = [clean.loc[clean["arm"] == a, "MBps_verified"].values for a in order]

    fig, ax = plt.subplots(figsize=(8, 0.45 * len(order) + 2))
    # 'labels' was renamed 'tick_labels' in mpl 3.9; support both so the figure
    # renders on whatever the Expanse conda env resolves.
    lab_kw = ("tick_labels" if tuple(int(x) for x in matplotlib.__version__.split(".")[:2]) >= (3, 9)
              else "labels")
    bp = ax.boxplot(data, vert=False, patch_artist=True, widths=0.6, **{lab_kw: order})
    for patch, arm in zip(bp["boxes"], order):
        patch.set_facecolor("#2b7bba" if arm.startswith("adaptiseq") else "#bbbbbb")
        patch.set_alpha(0.85)
    ax.set_xlabel("Verified throughput (MB/s)  — md5-checked bytes ÷ wall time")
    ax.set_title(PANEL_TITLES.get(panel, panel), fontsize=10)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(outdir / f"fig3_{panel}.png", dpi=200)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True, type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("."))
    args = ap.parse_args()

    if not args.tsv.exists():
        sys.exit(f"no such file: {args.tsv}")
    df = pd.read_csv(args.tsv, sep="\t")
    if df.empty:
        sys.exit("no rows yet")
    args.outdir.mkdir(parents=True, exist_ok=True)

    for panel, pdf in df.groupby("panel"):
        print("\n" + "=" * 78)
        print(PANEL_TITLES.get(panel, panel))
        print("=" * 78)

        # Three distinct outcomes that must never share a bucket:
        #   gz   -> comparable on wall time
        #   "-"  -> delivered NOTHING verifiable (crash/timeout/missing tool);
        #           that is a failure, not a format choice
        #   else -> fetched a real but different format (.sra, plain fastq)
        clean = pdf[pdf["format"] == "gz"]
        failed = pdf[pdf["format"] == "-"]
        other = pdf[(pdf["format"] != "gz") & (pdf["format"] != "-")]

        if not clean.empty:
            summ = add_speedup(summarize(clean))
            print("\n-- comparable arms (fetched .fastq.gz; MB/s is apples-to-apples) --")
            print(summ.to_string())
        if not other.empty:
            print("\n-- SEGREGATED: fetched a different format/size; NOT wall-time "
                  "comparable (§12.2) --")
            print(summarize(other)[["n", "wall_med", "MBps_med", "formats",
                                    "runs_ok_med", "runs_exp"]].to_string())
        if not failed.empty:
            print("\n-- FAILED: produced no verifiable bytes (crash / timeout / "
                  "tool missing) --")
            f = summarize(failed)[["n", "wall_med", "timeouts", "nonzero_rc"]]
            f["reasons"] = failed.groupby("arm")["status"].apply(
                lambda s: ",".join(sorted(set(s))))
            print(f.to_string())

        # The correctness result that lives inside the speed figure.
        comp = pdf.groupby("arm")["runs_complete"].median()
        exp = pdf["runs_expected"].max()
        dropped = comp[comp < exp]
        if len(dropped) and exp > 0:
            print(f"\n-- runs NOT completed (of {int(exp)} expected) --")
            for arm, n in dropped.items():
                print(f"   {arm:26s} completed {int(n):4d}  (dropped {int(exp - n)})")

        plot_panel(pdf, panel, args.outdir)

        summarize(pdf).to_csv(args.outdir / f"e3_summary_{panel}.csv")

    print(f"\nWrote summaries + fig3_*.png to {args.outdir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
