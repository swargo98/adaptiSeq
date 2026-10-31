#!/usr/bin/env python3
"""Fabric (local) vs Expanse E3 comparison: box plots + summary tables.

Reads two e3_results.tsv files, draws one figure per throughput panel with
fabric and Expanse side by side (horizontal box plots, one box per arm, coloured
by arm family), and prints median/IQR tables. Arm name on the y-axis is the
identity channel; colour is a redundant family grouping (CVD-validated blue/
green/red + muted grey for competitors).
"""
from __future__ import annotations
import csv, sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

FABRIC = Path("/home/ubuntu/adaptiSeq/e3_results/e3_results.tsv")
EXPANSE = Path("/home/ubuntu/adaptiSeq/exp3_expanse/e3_results.tsv")
OUT = Path("/home/ubuntu/adaptiSeq/analysis_fabric_vs_expanse")
OUT.mkdir(exist_ok=True)

# CVD-validated categorical palette (dataviz skill).
C_CLIMB, C_FIXED, C_LEG, C_COMP = "#2a78d6", "#008300", "#e34948", "#8a8a86"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e6e2"

def family(arm: str):
    if "climb" in arm: return ("climb", C_CLIMB)
    if "adaptive" in arm: return ("legacy-adaptive", C_LEG)
    if arm.startswith(("iseq", "fastq", "kingfisher")): return ("competitor", C_COMP)
    return ("fixed", C_FIXED)  # adaptiseq-fixed-*, adaptiseq-j*, adaptiseq-seg*

FAM_ORDER = {"climb": 0, "legacy-adaptive": 1, "fixed": 2, "competitor": 3}

def load(path):
    d = defaultdict(lambda: defaultdict(list))  # panel -> arm -> [MBps]
    with open(path) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            try:
                d[r["panel"]][r["arm"]].append(float(r["MBps_verified"]))
            except (ValueError, KeyError):
                pass
    return d

fab, exp = load(FABRIC), load(EXPANSE)

def med(v): return float(np.median(v)) if v else float("nan")

def panel_arms(panel):
    """Union of arms across both machines, ordered by family then median (fabric)."""
    arms = set(fab.get(panel, {})) | set(exp.get(panel, {}))
    def key(a):
        fam = family(a)[0]
        m = med(fab.get(panel, {}).get(a) or exp.get(panel, {}).get(a) or [0])
        return (FAM_ORDER[fam], -m)
    return sorted(arms, key=key)

def draw_panel(panel, title):
    arms = panel_arms(panel)
    if not arms: return None
    fig, axes = plt.subplots(1, 2, figsize=(13, max(3.2, 0.46*len(arms)+1.4)),
                             sharey=True, facecolor=SURFACE)
    for ax, data, name in ((axes[0], fab, "Fabric (this machine, 8-core)"),
                           (axes[1], exp, "Expanse (128-core, 1000/1000)")):
        ax.set_facecolor(SURFACE)
        ys = list(range(len(arms), 0, -1))
        for y, arm in zip(ys, arms):
            vals = data.get(panel, {}).get(arm, [])
            col = family(arm)[1]
            if not vals:
                ax.text(0.01, y, "no data", color=INK2, fontsize=7, va="center",
                        transform=ax.get_yaxis_transform())
                continue
            bp = ax.boxplot([vals], positions=[y], vert=False, widths=0.62,
                            patch_artist=True, showfliers=True, zorder=3,
                            medianprops=dict(color=INK, lw=1.6),
                            flierprops=dict(marker="o", ms=3, mfc=col, mec="none", alpha=.5),
                            whiskerprops=dict(color=col, lw=1.3),
                            capprops=dict(color=col, lw=1.3))
            for b in bp["boxes"]:
                b.set(facecolor=col, alpha=.30, edgecolor=col, lw=1.4)
            m = med(vals)
            ax.text(m, y+0.34, f"{m:.0f}", color=INK, fontsize=7.5, ha="center", va="bottom", zorder=4)
        ax.set_yticks(ys); ax.set_yticklabels([a.replace("adaptiseq-", "") for a in arms], fontsize=8.5)
        ax.set_title(name, fontsize=10, color=INK, pad=6)
        ax.set_xlabel("verified throughput (MB/s)", fontsize=9, color=INK2)
        ax.grid(axis="x", color=GRID, lw=0.8, zorder=0); ax.set_axisbelow(True)
        for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(length=0, colors=INK2)
        ax.set_xlim(left=0)
    handles = [Patch(fc=c, ec=c, alpha=.5, label=l) for l, c in
               (("climb (new)", C_CLIMB), ("legacy adaptive", C_LEG),
                ("fixed", C_FIXED), ("competitor", C_COMP))]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=9, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(title, fontsize=13, color=INK, y=0.995, x=0.5, ha="center", weight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    p = OUT / f"box_{panel}.png"
    fig.savefig(p, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return p

TITLES = {
    "3a": "3a — overhead-dominated (D1_fair, 201 files / 4.4 GB)",
    "3b": "3b — byte-dominated (D2_subset, 16 files / 25.9 GB)",
    "3r": "3r — robustness (D1_full, 321 files / 7.6 GB)",
    "3d": "3d — worker sweep (D0_sweep, 8 files)",
    "3s": "3s — segment sweep (D3_seg, 2 × 11.5 GB)",
}
made = []
for panel, title in TITLES.items():
    p = draw_panel(panel, title)
    if p: made.append(p); print("wrote", p)

# ---- summary table dump (median MB/s, both machines) ----
print("\n=== MEDIAN MB/s: fabric | expanse | Δ% (exp vs fab) ===")
for panel in ("3a", "3b", "3r", "3d", "3s"):
    arms = panel_arms(panel)
    if not arms: continue
    print(f"\n[{panel}] {TITLES[panel]}")
    print(f"  {'arm':26} {'fabric':>8} {'expanse':>8} {'Δ%':>7}")
    for a in arms:
        mf, me = med(fab.get(panel,{}).get(a,[])), med(exp.get(panel,{}).get(a,[]))
        d = (me-mf)/mf*100 if mf and not np.isnan(mf) and not np.isnan(me) else float("nan")
        print(f"  {a.replace('adaptiseq-',''):26} {mf:8.1f} {me:8.1f} {d:7.0f}")
print("\nfigures in", OUT)
