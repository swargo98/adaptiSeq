#!/usr/bin/env python3
"""Aggregate E10 TSVs -> Fig 8a/8b/8c + a text summary.

Reads e10_resolve.tsv (10a/10b) and e10_etiquette.tsv (10c) from --out, writes
PNGs and prints a summary. Matplotlib only; colourblind-safe palette.
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Okabe-Ito (colourblind-safe).
C = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
     "red": "#D55E00", "purple": "#CC79A7", "grey": "#666666",
     "sky": "#56B4E9", "yellow": "#F0E442"}
TOOL_C = {"adaptiseq": C["blue"], "iseq": C["orange"], "pysradb": C["green"],
          "ffq": C["purple"], "kingfisher": C["red"]}
EP_C = {"ncbi": C["red"], "ena": C["blue"], "gsa": C["green"]}
plt.rcParams.update({"figure.dpi": 130, "font.size": 10,
                     "axes.grid": True, "grid.alpha": 0.3})


def read_tsv(path):
    if not Path(path).exists():
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else 0.0


def fig_8a(resolve_rows, out):
    """acc/s vs meta_jobs (adaptiseq, per N) + competitor serial rates as lines."""
    aseq = [r for r in resolve_rows
            if r["tool"] == "adaptiseq" and r["panel"] == "10a"]
    comps = [r for r in resolve_rows
             if r["tool"] != "adaptiseq" and r["panel"] == "10a"]
    if not aseq:
        return
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    # one line per N
    by_n = defaultdict(lambda: defaultdict(list))
    for r in aseq:
        by_n[int(r["n_acc"])][int(r["meta_jobs"])].append(float(r["acc_per_s"]))
    markers = ["o", "s", "^", "D"]
    for i, n in enumerate(sorted(by_n)):
        mjs = sorted(by_n[n])
        ys = [med(by_n[n][mj]) for mj in mjs]
        ax.plot(mjs, ys, marker=markers[i % 4], color=C["blue"],
                alpha=0.55 + 0.45 * i / max(1, len(by_n) - 1),
                lw=2, label=f"adaptiSeq  N={n}")
    # competitor serial rates (horizontal reference lines)
    comp_rate = defaultdict(list)
    for r in comps:
        comp_rate[r["tool"]].append(float(r["acc_per_s"]))
    for tool, rates in sorted(comp_rate.items()):
        y = med(rates)
        ax.axhline(y, ls="--", lw=1.4, color=TOOL_C.get(tool, C["grey"]),
                   label=f"{tool} (serial) {y:.1f}/s")
    ax.axhline(8.0, ls=":", lw=1.2, color=C["grey"])
    ax.text(ax.get_xlim()[1], 8.0, " ENA cap 8 rps", va="bottom", ha="right",
            fontsize=8, color=C["grey"])
    ax.set_xlabel("--meta-jobs (resolution pool size)")
    ax.set_ylabel("resolution throughput (accessions / s)")
    ax.set_title("Fig 8a — Parallel resolution throughput vs --meta-jobs")
    ax.set_xticks(sorted({int(r["meta_jobs"]) for r in aseq}))
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(Path(out) / "fig8a_resolution_throughput.png")
    plt.close(fig)


def fig_8b(etiq_rows, out):
    """peak req/s per endpoint vs meta_jobs: limiter (flat at cap) vs naive."""
    rows = [r for r in etiq_rows if r["ncbi_key"] == "nokey"]
    if not rows:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, arm, title in [(axes[0], "limiter", "adaptiSeq (per-endpoint limiter)"),
                           (axes[1], "naive", "naive resolver (limiter disabled)")]:
        for ep in ["ncbi", "ena", "gsa"]:
            pts = [(int(r["meta_jobs"]), int(r["peak_rps_1s"]))
                   for r in rows if r["arm"] == arm and r["endpoint"] == ep]
            pts.sort()
            if not pts:
                continue
            xs, ys = zip(*pts)
            ax.plot(xs, ys, marker="o", color=EP_C[ep], lw=2, label=f"{ep} req/s")
            cap = next(float(r["cap_rps"]) for r in rows if r["endpoint"] == ep)
            ax.axhline(cap, ls="--", lw=1.2, color=EP_C[ep], alpha=0.6)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("--meta-jobs")
        ax.set_xticks(sorted({int(r["meta_jobs"]) for r in rows}))
    axes[0].set_ylabel("peak request rate (req / s, 1 s window)")
    axes[0].legend(fontsize=8, loc="upper left")
    axes[0].text(0.5, 0.02, "dashed = documented cap", transform=axes[0].transAxes,
                 fontsize=8, color=C["grey"])
    fig.suptitle("Fig 8b — Request rate is decoupled from pool size "
                 "(NCBI cap 3 rps, no key)", y=1.02)
    fig.tight_layout()
    fig.savefig(Path(out) / "fig8b_etiquette.png", bbox_inches="tight")
    plt.close(fig)


def fig_8c(resolve_rows, out):
    """Table-4-as-figure: median resolution wall by tool at comparable N, plus
    the 10b resolution-fraction bars."""
    a10 = [r for r in resolve_rows if r["panel"] == "10a"]
    if not a10:
        return
    # per-tool acc/s at best setting (adaptiseq = max meta_jobs; comps = serial)
    best = {}
    aseq = [r for r in a10 if r["tool"] == "adaptiseq"]
    if aseq:
        mjmax = max(int(r["meta_jobs"]) for r in aseq)
        best["adaptiseq"] = med([float(r["acc_per_s"]) for r in aseq
                                 if int(r["meta_jobs"]) == mjmax])
    for r in a10:
        if r["tool"] != "adaptiseq":
            best.setdefault(r["tool"], [])
    for tool in list(best):
        if tool != "adaptiseq":
            best[tool] = med([float(r["acc_per_s"]) for r in a10
                              if r["tool"] == tool])
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    tools = sorted(best, key=lambda t: best[t], reverse=True)
    ys = [best[t] for t in tools]
    colors = [TOOL_C.get(t, C["grey"]) for t in tools]
    bars = ax.barh(tools[::-1], ys[::-1], color=colors[::-1])
    for b, v in zip(bars, ys[::-1]):
        ax.text(v, b.get_y() + b.get_height() / 2, f" {v:.1f}/s",
                va="center", fontsize=9)
    ax.set_xlabel("resolution throughput (accessions / s, higher = better)")
    ax.set_title("Fig 8c — Resolution rate by tool "
                 "(adaptiSeq = parallel; others serial)")
    fig.tight_layout()
    fig.savefig(Path(out) / "fig8c_tool_rate.png")
    plt.close(fig)


def summarise(resolve_rows, etiq_rows, out):
    L = []
    a = L.append
    a("E10 SUMMARY")
    a("=" * 60)
    aseq = [r for r in resolve_rows if r["tool"] == "adaptiseq" and r["panel"] == "10a"]
    if aseq:
        a("\n10a resolution throughput (adaptiseq, median acc/s):")
        by = defaultdict(lambda: defaultdict(list))
        for r in aseq:
            by[int(r["n_acc"])][int(r["meta_jobs"])].append(float(r["acc_per_s"]))
        for n in sorted(by):
            parts = [f"mj={mj}:{med(by[n][mj]):.2f}" for mj in sorted(by[n])]
            base = med(by[n][min(by[n])])
            top = med(by[n][max(by[n])])
            a(f"  N={n:5d}  " + "  ".join(parts) +
              f"   speedup(mj{max(by[n])}/mj{min(by[n])})={top/base:.1f}x")
    comps = [r for r in resolve_rows if r["tool"] != "adaptiseq" and r["panel"] == "10a"]
    if comps:
        a("\n10a competitors (serial, median acc/s):")
        by = defaultdict(list)
        for r in comps:
            by[r["tool"]].append(float(r["acc_per_s"]))
        for t in sorted(by, key=lambda x: -med(by[x])):
            a(f"  {t:12s} {med(by[t]):.2f}/s")
    b10 = [r for r in resolve_rows if r["panel"] == "10b"]
    if b10:
        by = defaultdict(list)
        for r in b10:
            by[int(r["meta_jobs"])].append(float(r["wall_s"]))
        a("\n10b overlap (resolution wall, N=150):")
        for mj in sorted(by):
            a(f"  meta_jobs={mj}: {med(by[mj]):.2f}s")
        if 1 in by and 8 in by:
            a(f"  -> parallel resolution cuts the resolve phase "
              f"{med(by[1])/med(by[8]):.1f}x (mj1 {med(by[1]):.1f}s -> mj8 {med(by[8]):.1f}s)")
    if etiq_rows:
        a("\n10c etiquette (peak req/s, 1s window):")
        for key in ("nokey", "key"):
            rows = [r for r in etiq_rows if r["ncbi_key"] == key]
            if not rows:
                continue
            a(f"  [{key}] NCBI cap = "
              f"{next((r['cap_rps'] for r in rows if r['endpoint']=='ncbi'),'?')} rps")
            for arm in ("limiter", "naive"):
                nc = [(int(r["meta_jobs"]), int(r["peak_rps_1s"]), int(r["over_cap"]))
                      for r in rows if r["arm"] == arm and r["endpoint"] == "ncbi"]
                nc.sort()
                desc = ", ".join(f"mj{mj}:{pk}{'!' if ov else ''}" for mj, pk, ov in nc)
                a(f"    {arm:7s} NCBI peak: {desc}   (! = over cap)")
    txt = "\n".join(L)
    (Path(out) / "e10_summary.txt").write_text(txt + "\n")
    print(txt)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    resolve_rows = read_tsv(out / "e10_resolve.tsv")
    etiq_rows = read_tsv(out / "e10_etiquette.tsv")
    if resolve_rows:
        fig_8a(resolve_rows, out)
        fig_8c(resolve_rows, out)
    if etiq_rows:
        fig_8b(etiq_rows, out)
    summarise(resolve_rows, etiq_rows, out)
    print(f"\nfigures + summary -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
