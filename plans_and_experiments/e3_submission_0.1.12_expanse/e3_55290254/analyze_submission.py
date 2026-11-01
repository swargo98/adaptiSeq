#!/usr/bin/env python3
"""Every number and the one figure of the Application Note, from the E3 TSVs.

MINIMAL_SUBMISSION_PLAN.md, Step 3. Reads the submission-arm TSVs (panels 3r and
3b, one TSV per machine) and writes:

    summary.tsv      median + IQR of verified MB/s and wall time, per machine x panel x arm
    ratios.tsv       per machine x panel: median of the per-rep ratio
                     adaptiseq-default / other arm, with a bootstrap 95% CI
    completion.tsv   panel 3r: runs completed per arm, split into 1/2-file and
                     3-file runs (median, min, max over reps)
    numbers.json     the same values keyed for the manuscript text
    fig1.pdf / .png  (a) 3r MB/s  (b) 3b MB/s  (c) runs completed on 3r

    python bench/e3/analyze_submission.py \\
        --tsv Expanse=e3_expanse/e3_results.tsv --tsv Fabric=e3_fabric/e3_results.tsv \\
        --outdir paper_numbers

Rules it enforces rather than leaves to the reader:
  * median and IQR, never the mean (download timings are right-skewed);
  * MB/s counts md5-verified bytes only, so a partial run cannot look fast;
  * rows must all carry ONE adaptiSeq version + build hash per machine, and the
    same one on both machines -- a mixed run is refused (--allow-mixed overrides);
  * a ratio pairs rep k of adaptiSeq with rep k of the other arm. Arms within a
    rep ran back to back, so this is the pairing that shares network conditions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REFERENCE_ARM = "adaptiseq-default"

# Display order, label, and tool for every submission arm. Colour follows the
# TOOL (the entity being compared); the two arms of one tool share its hue and
# are told apart by their row label.
ARMS = [
    ("adaptiseq-default", "adaptiSeq (defaults)", "adaptiseq"),
    ("adaptiseq-fixed-j20", "adaptiSeq (fixed -j 20)", "adaptiseq"),
    ("kingfisher", "Kingfisher", "kingfisher"),
    ("fastq-dl", "fastq-dl", "fastq-dl"),
    ("iseq-p8", "iSeq (-p 8)", "iseq"),
    ("iseq", "iSeq", "iseq"),
]
ARM_LABEL = {a: lab for a, lab, _ in ARMS}
ARM_TOOL = {a: tool for a, _, tool in ARMS}

# Categorical palette, fixed slot per tool. Validated with the dataviz skill's
# validate_palette.js (light surface): CVD and normal-vision separation pass.
TOOL_COLOR = {
    "adaptiseq": "#2a78d6",
    "iseq": "#eb6834",
    "kingfisher": "#1baf7a",
    "fastq-dl": "#eda100",
}
INK = "#1f1f1e"
INK_MUTED = "#6b6a65"
GRID = "#e4e3df"

PANEL_TITLE = {
    "3r": "241 runs, 7.6 GB",
    "3b": "8 runs, 25.9 GB",
}


# ------------------------------- loading ---------------------------------------

def load(specs: list[str], panels: list[str], allow_mixed: bool) -> pd.DataFrame:
    frames = []
    for spec in specs:
        if "=" not in spec:
            sys.exit(f"--tsv wants MACHINE=path, got: {spec}")
        machine, path = spec.split("=", 1)
        df = pd.read_csv(path, sep="\t", dtype={"aseq_version": str, "aseq_sha256": str})
        missing = {"aseq_version", "aseq_sha256", "runs_complete_3file"} - set(df.columns)
        if missing:
            sys.exit(f"{path}: no {sorted(missing)} column(s). This TSV predates the "
                     "submission harness and must not feed the paper's numbers.")
        df["machine"] = machine
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df[df["panel"].isin(panels) & df["arm"].isin(ARM_LABEL)].copy()
    if df.empty:
        sys.exit("no submission-arm rows for panels " + ", ".join(panels))

    builds = df.groupby("machine")[["aseq_version", "aseq_sha256"]].agg(lambda s: sorted(set(s)))
    distinct = {(v, h) for v, h in zip(df["aseq_version"], df["aseq_sha256"])}
    if len(distinct) != 1:
        msg = "rows do not all come from one adaptiSeq build:\n" + builds.to_string()
        if not allow_mixed:
            sys.exit(msg + "\n(--allow-mixed to analyse anyway; do not publish that.)")
        print("[WARN] " + msg, file=sys.stderr)
    return df


# ------------------------------- statistics ------------------------------------

def q(s: pd.Series, p: float) -> float:
    return float(s.quantile(p))


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (machine, panel, arm), g in df.groupby(["machine", "panel", "arm"], sort=False):
        rows.append({
            "machine": machine, "panel": panel, "arm": arm, "n_reps": len(g),
            "MBps_median": round(g["MBps_verified"].median(), 2),
            "MBps_q1": round(q(g["MBps_verified"], 0.25), 2),
            "MBps_q3": round(q(g["MBps_verified"], 0.75), 2),
            "wall_s_median": round(g["wall_s"].median(), 1),
            "wall_s_q1": round(q(g["wall_s"], 0.25), 1),
            "wall_s_q3": round(q(g["wall_s"], 0.75), 1),
            "runs_complete_median": int(g["runs_complete"].median()),
            "runs_expected": int(g["runs_expected"].max()),
            "reps_all_runs_complete": int((g["runs_complete"] == g["runs_expected"]).sum()),
            "reps_exit_0": int((g["exit_code"] == 0).sum()),
        })
    return _ordered(pd.DataFrame(rows))


def bootstrap_median_ci(x: np.ndarray, rng: np.random.Generator,
                        n_boot: int = 10000) -> tuple[float, float]:
    """Percentile bootstrap 95% CI of the median. With 5 reps this is coarse --
    the interval can only land on observed values -- and is reported as such."""
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    med = np.median(x[idx], axis=1)
    return float(np.percentile(med, 2.5)), float(np.percentile(med, 97.5))


def ratios(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for (machine, panel), g in df.groupby(["machine", "panel"], sort=False):
        wide = g.pivot_table(index="rep", columns="arm", values="MBps_verified")
        if REFERENCE_ARM not in wide:
            continue
        for arm in wide.columns:
            if arm == REFERENCE_ARM:
                continue
            pair = wide[[REFERENCE_ARM, arm]].dropna()
            pair = pair[pair[arm] > 0]          # a rep that verified 0 bytes has no ratio
            if pair.empty:
                continue
            r = (pair[REFERENCE_ARM] / pair[arm]).to_numpy()
            lo, hi = bootstrap_median_ci(r, rng)
            rows.append({
                "machine": machine, "panel": panel, "reference": REFERENCE_ARM,
                "arm": arm, "n_reps": len(r),
                "ratio_median": round(float(np.median(r)), 2),
                "ratio_ci95_lo": round(lo, 2), "ratio_ci95_hi": round(hi, 2),
                "ratio_min": round(float(r.min()), 2), "ratio_max": round(float(r.max()), 2),
            })
    return _ordered(pd.DataFrame(rows))


def completion(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["panel"] == "3r"].copy()
    d["small_complete"] = d["runs_complete"] - d["runs_complete_3file"]
    d["small_expected"] = d["runs_expected"] - d["runs_expected_3file"]
    rows = []
    for (machine, arm), g in d.groupby(["machine", "arm"], sort=False):
        rows.append({
            "machine": machine, "arm": arm, "n_reps": len(g),
            "runs_complete_median": int(g["runs_complete"].median()),
            "runs_complete_min": int(g["runs_complete"].min()),
            "runs_complete_max": int(g["runs_complete"].max()),
            "runs_expected": int(g["runs_expected"].max()),
            "one_two_file_median": int(g["small_complete"].median()),
            "one_two_file_expected": int(g["small_expected"].max()),
            "three_file_median": int(g["runs_complete_3file"].median()),
            "three_file_min": int(g["runs_complete_3file"].min()),
            "three_file_max": int(g["runs_complete_3file"].max()),
            "three_file_expected": int(g["runs_expected_3file"].max()),
            # Runs with a payload file on disk that is not byte-identical to ENA's
            # (e.g. an .sra fallback recompressed locally). Not counted as complete.
            "present_unverified_median": int(g["runs_present_unverified"].median())
            if "runs_present_unverified" in g else 0,
        })
    return _ordered(pd.DataFrame(rows))


def _ordered(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return d
    order = {a: i for i, (a, _, _) in enumerate(ARMS)}
    keys = [k for k in ("machine", "panel") if k in d.columns]
    return (d.assign(_o=d["arm"].map(order)).sort_values(keys + ["_o"])
             .drop(columns="_o").reset_index(drop=True))


def fastest_competitor(summary: pd.DataFrame, ratio: pd.DataFrame) -> pd.DataFrame:
    """Per machine x panel: the non-adaptiSeq arm with the highest median MB/s, and
    adaptiSeq's ratio against it -- the abstract's headline speed number."""
    rows = []
    comp = summary[summary["arm"].map(ARM_TOOL) != "adaptiseq"]
    for (machine, panel), g in comp.groupby(["machine", "panel"], sort=False):
        best = g.loc[g["MBps_median"].idxmax()]
        r = ratio[(ratio["machine"] == machine) & (ratio["panel"] == panel)
                  & (ratio["arm"] == best["arm"])]
        if r.empty:
            continue
        r = r.iloc[0]
        rows.append({"machine": machine, "panel": panel, "fastest_competitor": best["arm"],
                     "competitor_MBps_median": best["MBps_median"],
                     "ratio_median": r["ratio_median"],
                     "ratio_ci95_lo": r["ratio_ci95_lo"], "ratio_ci95_hi": r["ratio_ci95_hi"]})
    return pd.DataFrame(rows)


# ------------------------------- figure ----------------------------------------

def figure(df: pd.DataFrame, comp: pd.DataFrame, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    plt.rcParams.update({
        "font.family": "sans-serif", "font.size": 8, "axes.edgecolor": GRID,
        "axes.labelcolor": INK, "xtick.color": INK_MUTED, "ytick.color": INK,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "pdf.fonttype": 42, "svg.fonttype": "none",
    })
    machines = list(dict.fromkeys(df["machine"]))
    arms = [a for a, _, _ in ARMS if a in set(df["arm"])]
    ypos = {a: i for i, a in enumerate(arms)}
    # Machines sit side by side inside each arm's row: first machine above the
    # row centre, second below; marker shape repeats the distinction.
    offs = np.linspace(-0.18, 0.18, len(machines)) if len(machines) > 1 else [0.0]
    marker = dict(zip(machines, ["o", "s", "D", "^"]))

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7), sharey=True,
                             gridspec_kw={"width_ratios": [1, 1, 0.95], "wspace": 0.16})

    for ax, panel, tag in zip(axes[:2], ("3r", "3b"), "ab"):
        d = df[df["panel"] == panel]
        for m, off in zip(machines, offs):
            for arm in arms:
                v = d[(d["machine"] == m) & (d["arm"] == arm)]["MBps_verified"]
                v = v[v > 0]
                if v.empty:
                    continue
                y = ypos[arm] + off
                color = TOOL_COLOR[ARM_TOOL[arm]]
                ax.plot([v.quantile(0.25), v.quantile(0.75)], [y, y], color=color,
                        lw=2, solid_capstyle="round", zorder=2)
                # every rep, faint: with 5 reps the points ARE the distribution
                ax.scatter(v, [y] * len(v), s=9, marker=marker[m], color=color,
                           alpha=0.35, linewidths=0, zorder=3)
                ax.scatter([v.median()], [y], s=34, marker=marker[m], color=color,
                           edgecolors="white", linewidths=1.0, zorder=4)
        ax.set_xscale("log")
        ax.set_xlabel("verified MB/s (log scale)")
        ax.set_title(f"({tag}) {PANEL_TITLE[panel]}", fontsize=8, loc="left", color=INK)
        ax.grid(axis="x", color=GRID, lw=0.6, which="major")
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:g}"))

    # (c) runs completed on 3r: 1/2-file runs solid, 3-file runs as a tint, with a
    # white gap between them; the dataset total is a reference line.
    ax = axes[2]
    h = 0.30 if len(machines) > 1 else 0.5
    total = int(comp["runs_expected"].max()) if not comp.empty else 0
    for m, off in zip(machines, offs):
        for arm in arms:
            r = comp[(comp["machine"] == m) & (comp["arm"] == arm)]
            if r.empty:
                continue
            r = r.iloc[0]
            y = ypos[arm] + off
            color = TOOL_COLOR[ARM_TOOL[arm]]
            ax.barh(y, r["one_two_file_median"], height=h, color=color, zorder=2)
            ax.barh(y, r["three_file_median"], left=r["one_two_file_median"], height=h,
                    color=color, alpha=0.45, edgecolor="white", linewidth=1.0, zorder=2)
            ax.text(r["runs_complete_median"] + total * 0.02, y,
                    f'{r["runs_complete_median"]}', va="center", ha="left",
                    fontsize=6.5, color=INK)
    if total:
        # the dataset total is the last tick, so the reference line labels itself
        ax.axvline(total, color=INK_MUTED, lw=0.8, zorder=1)
        ax.set_xticks([0, round(total / 3, -1), round(2 * total / 3, -1), total])
        ax.set_xlim(0, total * 1.17)
    ax.set_xlabel("runs, md5-verified (median)")
    ax.set_title(f"(c) runs completed of {total}", fontsize=8, loc="left", color=INK)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)

    axes[0].set_yticks(range(len(arms)))
    axes[0].set_yticklabels([ARM_LABEL[a] for a in arms])
    axes[0].set_ylim(len(arms) - 0.45, -0.75)

    handles = [Line2D([], [], marker=marker[m], color=INK_MUTED, lw=0, markersize=5,
                      label=f"{m} (upper row)" if i == 0 and len(machines) > 1
                      else (f"{m} (lower row)" if len(machines) > 1 else m))
               for i, m in enumerate(machines)]
    handles += [
        Line2D([], [], color=INK_MUTED, lw=2, label="IQR; large marker = median"),
        Patch(facecolor=INK_MUTED, label="1- and 2-file runs"),
        Patch(facecolor=INK_MUTED, alpha=0.45, label="3-file runs"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False,
               fontsize=6.5, bbox_to_anchor=(0.5, -0.02), handletextpad=0.5, columnspacing=1.4)
    fig.subplots_adjust(left=0.19, right=0.985, top=0.9, bottom=0.27)
    for ext in ("pdf", "png"):
        fig.savefig(out.with_suffix("." + ext), dpi=300)
    plt.close(fig)


# ------------------------------- main ------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tsv", action="append", required=True, metavar="MACHINE=PATH")
    ap.add_argument("--outdir", type=Path, default=Path("paper_numbers"))
    ap.add_argument("--panels", nargs="+", default=["3r", "3b"])
    ap.add_argument("--seed", type=int, default=20261013, help="bootstrap seed")
    ap.add_argument("--allow-mixed", action="store_true",
                    help="analyse rows from more than one adaptiSeq build (not for the paper)")
    args = ap.parse_args()

    df = load(args.tsv, args.panels, args.allow_mixed)
    args.outdir.mkdir(parents=True, exist_ok=True)

    summary = summarize(df)
    ratio = ratios(df, args.seed)
    comp = completion(df)
    headline = fastest_competitor(summary, ratio)

    summary.to_csv(args.outdir / "summary.tsv", sep="\t", index=False)
    ratio.to_csv(args.outdir / "ratios.tsv", sep="\t", index=False)
    comp.to_csv(args.outdir / "completion.tsv", sep="\t", index=False)
    (args.outdir / "numbers.json").write_text(json.dumps({
        "adaptiseq_version": sorted(set(df["aseq_version"])),
        "adaptiseq_sha256": sorted(set(df["aseq_sha256"])),
        "bootstrap": {"n_boot": 10000, "seed": args.seed, "statistic": "median of per-rep ratio"},
        "summary": summary.to_dict("records"),
        "ratios": ratio.to_dict("records"),
        "completion_3r": comp.to_dict("records"),
        "headline_vs_fastest_competitor": headline.to_dict("records"),
    }, indent=2) + "\n")
    figure(df, comp, args.outdir / "fig1")

    pd.set_option("display.width", 200)
    for title, table in (("median + IQR", summary), ("adaptiseq-default / arm", ratio),
                         ("3r completeness", comp), ("vs fastest competitor", headline)):
        print(f"\n=== {title} ===")
        print(table.to_string(index=False) if not table.empty else "(no rows)")
    print(f"\nwrote {args.outdir}/{{summary,ratios,completion}}.tsv, numbers.json, fig1.pdf, fig1.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
