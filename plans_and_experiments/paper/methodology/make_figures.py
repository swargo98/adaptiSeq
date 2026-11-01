#!/usr/bin/env python3
"""Figures, tables and numbers for the methodology/evaluation document.

Reads the benchmark result directories under plans_and_experiments/ and writes
  figs/*.pdf        one file per figure
  data/*.csv        the rows each figure was drawn from
  numbers.tex       \\newcommand macros for every number the text quotes
so the text never carries a number typed by hand.

    python make_figures.py --root .. --portal ../ena_portal_status_20261015.tsv
"""
from __future__ import annotations

import argparse
import glob
import gzip
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, LogNorm

# ----------------------------------------------------------------- style ---
# Reference palette (dataviz skill, palette.md), categorical slots in their
# validated order; marker shapes carry identity as well, so no chart relies on
# hue alone.
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
GOOD, WARN, SERIOUS, CRIT = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
CMAP = LinearSegmentedColormap.from_list("seqblue", SEQ)

ARMS = [  # submission arms: (arm, label, color, marker)
    ("adaptiseq-default", "adaptiSeq (default, adaptive)", SLOT[0], "o"),
    ("adaptiseq-fixed-j20", "adaptiSeq (fixed -j 20)", SLOT[1], "s"),
    ("kingfisher", "Kingfisher 0.5.0", SLOT[2], "D"),
    ("fastq-dl", "fastq-dl 4.0.1", SLOT[3], "^"),
    ("iseq-p8", "iSeq 1.9.9 (-p 8)", SLOT[4], "v"),
    ("iseq", "iSeq 1.9.9", SLOT[5], "P"),
]
ARM_LABEL = {a: l for a, l, _, _ in ARMS}
ARM_COLOR = {a: c for a, _, c, _ in ARMS}
ARM_MARK = {a: m for a, _, _, m in ARMS}

CTRL = [  # controller-round arms
    ("adaptiseq-ctrl-topdown", "topdown (default)", SLOT[0], "o"),
    ("adaptiseq-fixed-j20", "fixed -j 20", SLOT[1], "s"),
    ("adaptiseq-ctrl-budget", "budget", SLOT[2], "D"),
    ("adaptiseq-ctrl-greedy", "greedy", SLOT[3], "^"),
    ("adaptiseq-ctrl-knee", "knee", SLOT[4], "v"),
    ("adaptiseq-ctrl-bottomup", "bottomup", SLOT[5], "P"),
    ("adaptiseq-fixed-j64", "fixed -j 64", SLOT[6], "X"),
]
CTRL_LABEL = {a: l for a, l, _, _ in CTRL}

PANEL_NAME = {
    "3r": "ENA, 241 small runs (7.6 GB)", "3b": "ENA, 8 large runs (25.9 GB)",
    "4r": "ENA small", "4b": "ENA large", "4s": "NCBI SRA", "4g": "GSA",
    "4h": "ENA held-out", "4m": "mixed archives",
}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 9,
    "axes.labelsize": 8.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 1.5, "lines.solid_capstyle": "round", "legend.frameon": False,
    "figure.dpi": 150, "savefig.bbox": "tight", "pdf.fonttype": 42,
    "axes.titleweight": "bold", "axes.titlelocation": "left",
})

NUM: dict[str, str] = {}


def logaxis(ax, axis: str = "y") -> None:
    """Log scale with plain-number ticks at 1-2-5 steps and no minor labels."""
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    a = ax.yaxis if axis == "y" else ax.xaxis
    (ax.set_yscale if axis == "y" else ax.set_xscale)("log")
    a.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
    a.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 1 else f"{v:g}"))
    a.set_minor_formatter(NullFormatter())


def datefmt(ax, every: int = 4) -> None:
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=every))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))


def num(name: str, value, fmt: str = "{}") -> None:
    """Record a number for numbers.tex (macro names must be letters only)."""
    assert re.fullmatch(r"[A-Za-z]+", name), name
    NUM[name] = fmt.format(value) if not isinstance(value, str) else value


def save(fig, name: str) -> None:
    fig.savefig(OUT / "figs" / f"{name}.pdf")
    plt.close(fig)


# --------------------------------------------------------------- loading ---
def read_tsv(path: Path, campaign: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", dtype={"aseq_version": str})
    df["campaign"] = campaign
    df["job"] = path.parent.name
    df["resdir"] = str(path.parent)
    df["stamp"] = pd.to_datetime(df["stamp"], utc=True, errors="coerce")
    return df


def load_campaign(pattern: str, campaign: str) -> pd.DataFrame:
    files = sorted(ROOT.glob(pattern))
    if not files:
        raise SystemExit(f"no TSVs for {pattern}")
    return pd.concat([read_tsv(f, campaign) for f in files], ignore_index=True)


def open_text(path: Path) -> str:
    for p in (path, Path(str(path) + ".gz")):
        if p.exists():
            op = gzip.open if p.suffix == ".gz" else open
            with op(p, "rt", errors="replace") as fh:
                return re.sub(r"\x1b\[[0-9;]*m", "", fh.read())
    return ""


def logname(row, kind="log") -> Path:
    stem = f"{row['panel']}_{row['dataset']}_{row['arm']}_rep{int(row['rep'])}"
    d = Path(row["resdir"]) / "logs"
    return d / (f"conc_{stem}.tsv" if kind == "conc" else f"{stem}.log")


def conc_series(row) -> pd.DataFrame | None:
    p = logname(row, "conc")
    if not p.exists():
        return None
    c = pd.read_csv(p, sep="\t")
    return c if len(c) else None


def add_conn_md5(df: pd.DataFrame) -> pd.DataFrame:
    means, maxes, mm = [], [], []
    for _, r in df.iterrows():
        c = conc_series(r)
        means.append(float(c["conns_archive"].mean()) if c is not None else np.nan)
        maxes.append(float(c["conns_archive"].max()) if c is not None else np.nan)
        text = open_text(logname(r))
        mm.append(len(re.findall(r"MD5 mismatch|MD5 checksums do not match|verification failed", text)))
    df = df.copy()
    df["conn_mean"], df["conn_max"], df["md5_mismatch"] = means, maxes, mm
    return df


def timeout_of(panel: str) -> float:
    return {"3r": 10800, "3b": 30000}.get(panel, 7200)


# -------------------------------------------------------------- figures ---
def fig_portal(path: Path) -> None:
    p = pd.read_csv(path, sep="\t")
    p["t"] = pd.to_datetime(p["time_pdt"])
    p["fail"] = p["http_code"] != 200
    # an empty 200 (header only, 24 bytes) is a failure too: a run that exists came back with no rows
    p["empty"] = (p["http_code"] == 200) & (p["bytes"] < 40)
    p.to_csv(OUT / "data" / "portal.csv", index=False)
    n, nf, ne = len(p), int(p["fail"].sum()), int(p["empty"].sum())
    slow = int(((p["http_code"] == 200) & (p["time_s"] > 10)).sum())
    num("portalProbes", n, "{:,}")
    num("portalDays", (p["t"].max() - p["t"].min()).total_seconds() / 86400, "{:.0f}")
    num("portalFail", nf)
    num("portalFailPct", 100 * nf / n, "{:.1f}")
    num("portalFiveHundred", int((p["http_code"] == 500).sum()))
    num("portalTimeout", int((p["http_code"] == 0).sum()))
    num("portalEmpty", ne)
    num("portalSlow", slow)
    num("portalMedianS", p.loc[~p["fail"], "time_s"].median(), "{:.2f}")
    num("portalMaxS", p.loc[~p["fail"], "time_s"].max(), "{:.0f}")
    num("portalStart", p["t"].min().strftime("%b %-d"))
    num("portalEnd", p["t"].max().strftime("%b %-d"))

    fig, (a, b) = plt.subplots(2, 1, figsize=(7.0, 3.6), sharex=True,
                               gridspec_kw={"height_ratios": [2.2, 1], "hspace": 0.12})
    ok = p[~p["fail"] & ~p["empty"]]
    a.scatter(ok["t"], ok["time_s"], s=4, color=SLOT[0], alpha=0.45, lw=0, label="HTTP 200 with rows")
    em = p[p["empty"]]
    a.scatter(em["t"], em["time_s"], s=22, marker="D", color=WARN, edgecolor="white", lw=0.8,
              label="HTTP 200 with no rows (run exists)")
    f = p[p["fail"]].copy()
    f["y"] = np.where(f["http_code"] == 0, 60, f["time_s"].clip(lower=0.2))
    a.scatter(f["t"], f["y"], s=20, marker="x", color=CRIT, lw=1.2, label="HTTP 500 or no answer in 60 s")
    logaxis(a)
    a.set_ylabel("answer time (s)")
    a.set_title("ENA portal API, one filereport query every 5 min")
    a.legend(loc="upper left", ncol=3, handletextpad=0.3, columnspacing=1.2)
    a.set_ylim(0.2, 200)
    day = p.set_index("t").resample("D").agg({"fail": "sum", "empty": "sum"})
    slowd = p[(p["http_code"] == 200) & (p["time_s"] > 10)].set_index("t").resample("D").size()
    day["slow"] = slowd.reindex(day.index).fillna(0)
    x = day.index + pd.Timedelta(hours=12)
    b.bar(x, day["fail"] + day["empty"], width=0.7, color=CRIT, label="failed or empty")
    b.bar(x, day["slow"], width=0.7, bottom=day["fail"] + day["empty"], color=SERIOUS,
          label="answered, but after > 10 s")
    b.set_ylabel("queries / day")
    b.legend(loc="upper right", ncol=2)
    datefmt(b, 2)
    save(fig, "portal")


def parse_probe(path: Path):
    t = path.read_text(errors="replace")
    m = re.search(r"date: (\S+)", t)
    vals = dict((int(p), float(v)) for p, v in re.findall(r"P=(\d+)\s+total ([\d.]+) MB/s", t))
    if not m or not vals:
        return None
    return {"t": pd.to_datetime(m.group(1), utc=True), "file": str(path.relative_to(ROOT)), **{f"P{k}": v for k, v in vals.items()}}


def fig_probe() -> pd.DataFrame:
    rows = [r for f in sorted(ROOT.glob("**/link_probe.txt")) if (r := parse_probe(f))]
    pr = pd.DataFrame(rows).dropna(subset=["P1", "P8", "P20"]).drop_duplicates(subset=["t"])
    pr = pr[pr["file"].str.contains("expanse")].sort_values("t")
    pr.to_csv(OUT / "data" / "link_probe.csv", index=False)
    pc1 = pr["P1"]
    num("probeN", len(pr))
    num("probeOneMin", pc1.min(), "{:.1f}")
    num("probeOneMax", pc1.max(), "{:.1f}")
    num("probeOneMed", pc1.median(), "{:.1f}")
    num("probeTwentyMin", pr["P20"].min(), "{:.1f}")
    num("probeTwentyMax", pr["P20"].max(), "{:.1f}")
    num("probeTwentyMed", pr["P20"].median(), "{:.1f}")
    num("probeScaleMed", (pr["P20"] / pr["P1"]).median(), "{:.1f}")

    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 2.7), gridspec_kw={"width_ratios": [1.6, 1], "wspace": 0.28})
    a.scatter(pr["t"], pr["P1"], s=22, color=SLOT[0], edgecolor="white", lw=0.8, label="1 connection")
    a.scatter(pr["t"], pr["P20"] / 20, s=22, marker="s", color=SLOT[1], edgecolor="white", lw=0.8,
              label="20 connections, per connection")
    a.set_ylabel("MB/s per connection")
    a.set_title("(a) ENA per-connection rate, one probe per job")
    datefmt(a)
    a.legend(loc="upper right")
    a.set_ylim(0, None)
    for _, r in pr.iterrows():
        b.plot([1, 8, 20], [r["P1"], r["P8"], r["P20"]], color=SLOT[0], alpha=0.18, lw=1)
    med = pr[["P1", "P8", "P20"]].median()
    b.plot([1, 8, 20], med.values, color=SLOT[0], lw=2, marker="o", ms=5, mec="white", label="median of jobs")
    b.plot([1, 20], [med["P1"], 20 * med["P1"]], color=MUTED, lw=1, label="linear in connections")
    b.set_xlabel("parallel range requests")
    b.set_ylabel("aggregate MB/s")
    b.set_title("(b) aggregate rate vs connections")
    b.set_xticks([1, 8, 20])
    b.legend(loc="upper left")
    save(fig, "link_probe")
    return pr


def fig_jsweep(sw: pd.DataFrame) -> None:
    sw = sw[sw["panel"].isin(["3jr", "3jb"])].copy()
    sw["j"] = sw["arm"].str.extract(r"fixed-j(\d+)").astype(float)
    sw.to_csv(OUT / "data" / "jsweep.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8), sharey=False, gridspec_kw={"wspace": 0.25})
    for ax, panel, title in zip(axes, ["3jr", "3jb"], ["(a) 241 small runs, 7.6 GB", "(b) 8 large runs, 25.9 GB"]):
        d = sw[sw["panel"] == panel]
        fx = d.dropna(subset=["j"])
        ax.scatter(fx["j"], fx["wall_s"], s=14, color=MUTED, alpha=0.7, lw=0, label="one rep")
        med = fx.groupby("j")["wall_s"].median()
        ax.plot(med.index, med.values, color=SLOT[0], lw=2, marker="o", ms=5, mec="white",
                label="fixed -j, median of 3 reps")
        ideal = med.iloc[0] / med.index.values
        ax.plot(med.index, ideal, color=MUTED, lw=1, label="time / j (ideal scaling)")
        dm = d[d["arm"] == "adaptiseq-default"]["wall_s"].median()
        ax.axhline(dm, color=SLOT[1], lw=1.5, label="adaptive default, median")
        ax.set_xscale("log", base=2)
        logaxis(ax)
        ax.set_xticks([1, 2, 4, 8, 16, 32, 64])
        ax.set_xticklabels(["1", "2", "4", "8", "16", "32", "64"])
        ax.set_xlabel("files downloaded at once (-j)")
        ax.set_title(title)
        tag = "R" if panel == "3jr" else "B"
        num(f"sweep{tag}One", med.loc[1], "{:,.0f}")
        num(f"sweep{tag}Best", med.min(), "{:,.0f}")
        num(f"sweep{tag}BestJ", int(med.idxmin()))
        num(f"sweep{tag}Eight", med.loc[8], "{:,.0f}")
        num(f"sweep{tag}Speedup", med.loc[1] / med.min(), "{:.0f}")
        num(f"sweep{tag}Default", dm, "{:,.0f}")
    axes[0].set_ylabel("wall time (s)")
    axes[0].legend(loc="lower left")
    save(fig, "jsweep")


def fig_versions(c014, v15, v16, v17, r2, r3, ch) -> None:
    rows = []

    def pair(df, panel, dflt, label):
        for (job, rep), g in df[df["panel"] == panel].groupby(["job", "rep"]):
            a = g[g["arm"] == dflt]
            b = g[g["arm"] == "adaptiseq-fixed-j20"]
            if len(a) and len(b):
                rows.append({"build": label, "job": job, "rep": rep,
                             "default_s": float(a["wall_s"].iloc[0]), "fixed_s": float(b["wall_s"].iloc[0]),
                             "default_runs": int(a["runs_complete"].iloc[0]),
                             "fixed_runs": int(b["runs_complete"].iloc[0])})

    pair(c014, "3b", "adaptiseq-default", "0.1.4")
    pair(v15, "3b", "adaptiseq-default", "0.1.5")
    pair(v16, "3b", "adaptiseq-default", "0.1.6")
    pair(v17, "3b", "adaptiseq-default", "0.1.7")
    pair(r2, "4b", "adaptiseq-ctrl-topdown", "0.1.11")
    pair(r3, "4b", "adaptiseq-ctrl-topdown", "0.1.12\nrnd 3")
    pair(ch, "3b", "adaptiseq-default", "0.1.12\nchain")
    v = pd.DataFrame(rows)
    v["ratio"] = v["default_s"] / v["fixed_s"]
    v.to_csv(OUT / "data" / "versions.csv", index=False)
    builds = list(dict.fromkeys(v["build"]))
    x = {b: i for i, b in enumerate(builds)}
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 2.9), gridspec_kw={"wspace": 0.3})
    jit = lambda n: np.linspace(-0.12, 0.12, n) if n > 1 else np.zeros(1)
    for bld, g in v.groupby("build", sort=False):
        xs = x[bld] + jit(len(g))
        a.scatter(xs - 0.04, g["default_s"], s=24, color=SLOT[0], edgecolor="white", lw=0.8, zorder=3,
                  label="adaptive default" if bld == builds[0] else None)
        a.scatter(xs + 0.04, g["fixed_s"], s=24, marker="s", color=SLOT[1], edgecolor="white", lw=0.8, zorder=3,
                  label="fixed -j 20 (same job)" if bld == builds[0] else None)
        b.scatter(xs, g["ratio"], s=24, color=SLOT[0], edgecolor="white", lw=0.8, zorder=3)
        b.plot([x[bld] - 0.25, x[bld] + 0.25], [g["ratio"].median()] * 2, color=INK2, lw=1.5)
    for ax in (a, b):
        ax.set_xticks(range(len(builds)))
        ax.set_xticklabels(builds, fontsize=7)
        logaxis(ax)
        ax.set_xlabel("adaptiSeq build")
    a.set_ylabel("wall time (s)")
    a.set_title("(a) ENA large panel, 25.9 GB")
    a.legend(loc="upper right")
    b.axhline(1, color=AXIS, lw=1)
    b.set_ylabel("default / fixed -j 20")
    b.set_title("(b) cost of the adaptive default")
    save(fig, "versions")
    first = v[v["build"] == "0.1.4"]["default_s"]
    last = v[v["build"] == "0.1.12\nchain"]["default_s"]
    num("verFirstMed", first.median(), "{:,.0f}")
    num("verLastMed", last.median(), "{:,.0f}")
    num("verGain", first.median() / last.median(), "{:.1f}")


def fig_tail(c014, ch) -> None:
    cases = [
        (c014, "3b", 2, "adaptiseq-default", "(a) 0.1.4, rep 2: 6552 s"),
        (c014, "3b", 3, "adaptiseq-fixed-j20", "(b) 0.1.4, fixed -j 20, rep 3: 10586 s"),
        (ch, "3b", 1, "adaptiseq-default", "(c) 0.1.12, rep 1: 850 s"),
        (ch, "3b", 3, "adaptiseq-default", "(d) 0.1.12, rep 3: 1253 s"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 3.9), sharey=True, gridspec_kw={"hspace": 0.55, "wspace": 0.08})
    for ax, (df, panel, rep, arm, title) in zip(axes.flat, cases):
        r = df[(df["panel"] == panel) & (df["rep"] == rep) & (df["arm"] == arm)].iloc[0]
        c = conc_series(r)
        ax.fill_between(c["t_rel_s"] / 60, c["conns_archive"], step="post", color=SLOT[0], alpha=0.12, lw=0)
        ax.step(c["t_rel_s"] / 60, c["conns_archive"], where="post", color=SLOT[0], lw=1)
        ax.set_title(title, fontweight="normal")
        ax.set_xlabel("minutes")
        frac = float((c.loc[c["t_rel_s"] > 60, "conns_archive"] <= 3).mean())
        ax.text(0.97, 0.55, f"≤ 3 connections for {100*frac:.0f}% of the run", transform=ax.transAxes,
                ha="right", va="center", color=INK2, fontsize=7.5,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
    for ax in axes[:, 0]:
        ax.set_ylabel("open archive connections")
    save(fig, "tail")


def fig_ftp(ch) -> None:
    cases = [("3r", 2, "adaptiseq-default", "(a) 3r rep 2, default: segmented FTP"),
             ("3r", 2, "adaptiseq-fixed-j20", "(b) 3r rep 2, fixed -j 20: HTTPS"),
             ("3b", 5, "adaptiseq-default", "(c) 3b rep 5, default: segmented FTP"),
             ("3b", 5, "adaptiseq-fixed-j20", "(d) 3b rep 5, fixed -j 20: HTTPS")]
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 3.9), sharey=True, gridspec_kw={"hspace": 0.55, "wspace": 0.08})
    for ax, (panel, rep, arm, title) in zip(axes.flat, cases):
        r = ch[(ch["panel"] == panel) & (ch["rep"] == rep) & (ch["arm"] == arm)].iloc[0]
        c = conc_series(r)
        col = SLOT[1] if "FTP" in title else SLOT[0]
        ax.fill_between(c["t_rel_s"] / 60, c["conns_archive"], step="post", color=col, alpha=0.12, lw=0)
        ax.step(c["t_rel_s"] / 60, c["conns_archive"], where="post", color=col, lw=1)
        ax.set_title(title, fontweight="normal")
        ax.set_xlabel("minutes")
        ax.text(0.97, 0.55, f"{r['wall_s']:.0f} s, mean {c['conns_archive'].mean():.1f} connections",
                transform=ax.transAxes, ha="right", va="center", color=INK2, fontsize=7.5,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
    for ax in axes[:, 0]:
        ax.set_ylabel("open archive connections")
    save(fig, "ftp_fallback")


def fig_chain(ch: pd.DataFrame) -> pd.DataFrame:
    ch = ch.copy()
    ch["timeout"] = ch["status"].eq("TIMEOUT")
    ref = ch[ch["arm"] == "adaptiseq-fixed-j20"].set_index(["panel", "rep"])["wall_s"]
    ch["ratio"] = ch.apply(lambda r: r["wall_s"] / ref.loc[(r["panel"], r["rep"])], axis=1)
    ch["silent"] = (ch["exit_code"] == 0) & (ch["runs_complete"] < ch["runs_expected"])
    ch["missing"] = ch["runs_expected"] - ch["runs_complete"] - ch["runs_present_unverified"]
    ch.to_csv(OUT / "data" / "chain.csv", index=False)

    # (1) wall time, every rep
    fig, axes = plt.subplots(2, 1, figsize=(6.2, 4.6), gridspec_kw={"hspace": 0.55})
    for ax, panel in zip(axes, ["3r", "3b"]):
        d = ch[ch["panel"] == panel]
        order = d.groupby("arm")["wall_s"].median().sort_values().index.tolist()
        for i, arm in enumerate(order):
            g = d[d["arm"] == arm]
            y = np.full(len(g), i) + np.linspace(-0.15, 0.15, len(g))
            fin = ~g["timeout"]
            ax.scatter(g.loc[fin, "wall_s"], y[fin.values], s=26, marker=ARM_MARK[arm], color=ARM_COLOR[arm],
                       edgecolor="white", lw=0.8, zorder=3)
            ax.scatter(g.loc[~fin, "wall_s"], y[(~fin).values], s=26, marker=ARM_MARK[arm], facecolor="white",
                       edgecolor=ARM_COLOR[arm], lw=1.2, zorder=3)
            m = g["wall_s"].median()
            ax.plot([m, m], [i - 0.32, i + 0.32], color=INK, lw=1.5, zorder=4)
        ax.axvline(timeout_of(panel), color=CRIT, lw=1)
        ax.text(timeout_of(panel), len(order) - 0.45, "time limit", color=CRIT, ha="right", va="bottom", fontsize=7)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([ARM_LABEL[a] for a in order])
        ax.invert_yaxis()
        logaxis(ax, "x")
        ax.set_xlabel("wall time (s)")
        ax.set_title(PANEL_NAME[panel])
        ax.grid(axis="y", visible=False)
    save(fig, "chain_wall")

    # (2) ratio to fixed -j 20 per rep, heat table
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.4), gridspec_kw={"wspace": 0.05})
    for ax, panel in zip(axes, ["3r", "3b"]):
        d = ch[ch["panel"] == panel].pivot(index="arm", columns="rep", values="ratio")
        t = ch[ch["panel"] == panel].pivot(index="arm", columns="rep", values="timeout")
        u = ch[ch["panel"] == panel].pivot(index="arm", columns="rep", values="runs_complete")
        e = ch[ch["panel"] == panel].pivot(index="arm", columns="rep", values="runs_expected")
        order = [a for a, *_ in ARMS if a in d.index]
        d, t, u, e = d.loc[order], t.loc[order], u.loc[order], e.loc[order]
        ax.imshow(d.values, cmap=CMAP, norm=LogNorm(vmin=0.5, vmax=80), aspect="auto")
        for i in range(d.shape[0]):
            for j in range(d.shape[1]):
                val = d.values[i, j]
                s = (">" if t.values[i, j] else "") + (f"{val:.1f}" if val < 10 else f"{val:.0f}")
                if u.values[i, j] < e.values[i, j]:
                    s += "*"
                ax.text(j, i, s, ha="center", va="center", fontsize=7,
                        color="white" if val > 6 else INK)
        ax.set_xticks(range(d.shape[1]))
        ax.set_xticklabels([f"rep {c}" for c in d.columns])
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([ARM_LABEL[a] for a in order] if panel == "3r" else [])
        ax.set_title(PANEL_NAME[panel])
        ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0)
    save(fig, "chain_ratio")

    # (3) completeness: runs verified / present but unverifiable / missing, summed over reps
    fig, axes = plt.subplots(2, 1, figsize=(6.2, 4.4), gridspec_kw={"hspace": 0.6})
    for ax, panel in zip(axes, ["3r", "3b"]):
        d = ch[ch["panel"] == panel].groupby("arm").agg(
            ver=("runs_complete", "sum"), unv=("runs_present_unverified", "sum"),
            exp=("runs_expected", "sum"), silent=("silent", "sum"), nz=("exit_code", lambda s: int((s != 0).sum())))
        d["miss"] = d["exp"] - d["ver"] - d["unv"]
        order = [a for a, *_ in ARMS if a in d.index]
        d = d.loc[order]
        y = np.arange(len(order))
        tot = d["exp"].iloc[0]
        ax.barh(y, d["ver"] / tot * 100, color=GOOD, height=0.55, label="md5-verified against ENA")
        ax.barh(y, d["unv"] / tot * 100, left=d["ver"] / tot * 100, color=WARN, height=0.55,
                label="present, not verifiable (from SRA)")
        ax.barh(y, d["miss"] / tot * 100, left=(d["ver"] + d["unv"]) / tot * 100, color=CRIT, height=0.55,
                label="missing")
        for i, (arm, r) in enumerate(d.iterrows()):
            ax.text(101, i, f"exit 0, runs short: {int(r['silent'])} of 5 reps", va="center", fontsize=7, color=INK2)
        ax.set_yticks(y)
        ax.set_yticklabels([ARM_LABEL[a] for a in order])
        ax.invert_yaxis()
        ax.set_xlim(0 if panel == "3b" else 50, 100)
        ax.set_xlabel(f"% of {tot:,} run downloads (5 reps)")
        ax.set_title(PANEL_NAME[panel])
        ax.grid(axis="y", visible=False)
    axes[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.38), ncol=3)
    save(fig, "chain_complete")

    # numbers
    for panel, tag in (("3r", "R"), ("3b", "B")):
        d = ch[ch["panel"] == panel]
        for arm, at in (("adaptiseq-default", "Def"), ("adaptiseq-fixed-j20", "Fix")):
            g = d[d["arm"] == arm]
            num(f"ch{tag}{at}Med", g["wall_s"].median(), "{:,.0f}")
            num(f"ch{tag}{at}Min", g["wall_s"].min(), "{:,.0f}")
            num(f"ch{tag}{at}Max", g["wall_s"].max(), "{:,.0f}")
            num(f"ch{tag}{at}MBps", g["MBps_verified"].median(), "{:.1f}")
            num(f"ch{tag}{at}Conn", g["conn_mean"].median(), "{:.1f}")
        others = d[~d["arm"].str.startswith("adaptiseq")]
        best = others.groupby("arm")["wall_s"].median().sort_values()
        num(f"ch{tag}BestOther", ARM_LABEL[best.index[0]])
        num(f"ch{tag}BestOtherMed", best.iloc[0], "{:,.0f}")
        num(f"ch{tag}WorstOtherMed", best.iloc[-1], "{:,.0f}")
        dm = d[d["arm"] == "adaptiseq-default"].set_index("rep")["wall_s"]
        fm = d[d["arm"] == "adaptiseq-fixed-j20"].set_index("rep")["wall_s"]
        # fastest other tool that delivered every run verified; an arm that
        # stopped early with runs missing is not "fast". With none complete in a
        # rep, the time limit stands in (a lower bound).
        full = others[others["runs_complete"] == others["runs_expected"]]
        bo = full.groupby("rep")["wall_s"].min().reindex(dm.index).fillna(timeout_of(panel))
        num(f"ch{tag}DefVsBestOther", (bo / dm).median(), "{:.1f}")
        num(f"ch{tag}FixVsBestOther", (bo / fm).median(), "{:.1f}")
        num(f"ch{tag}DefVsBestOtherMin", (bo / dm).min(), "{:.1f}")
        num(f"ch{tag}DefRatioMed", (dm / fm).median(), "{:.2f}")
        num(f"ch{tag}Timeouts", int(d["timeout"].sum()))
        num(f"ch{tag}OtherMBpsMax", others.groupby("arm")["MBps_verified"].median().max(), "{:.1f}")
    a = ch[ch["arm"].str.startswith("adaptiseq")]
    o = ch[~ch["arm"].str.startswith("adaptiseq")]
    num("chAseqSilent", int(a["silent"].sum()))
    num("chOtherSilent", int(o["silent"].sum()))
    num("chOtherRows", len(o))
    num("chAseqRows", len(a))
    num("chAseqShort", int((a["runs_complete"] < a["runs_expected"]).sum()))
    num("chOtherUnverified", int(o["runs_present_unverified"].sum()), "{:,}")
    num("chOtherTimeouts", int(o["timeout"].sum()))
    num("chAseqUnverified", int(a["runs_present_unverified"].sum()))
    return ch


def fig_md5(c014: pd.DataFrame, ch: pd.DataFrame) -> None:
    rows = []
    for df, build in ((c014, "0.1.4"), (ch, "0.1.12")):
        for _, r in df.iterrows():
            rows.append({"build": build, "panel": r["panel"], "rep": int(r["rep"]), "arm": r["arm"],
                         "md5": int(r["md5_mismatch"])})
    m = pd.DataFrame(rows)
    m.to_csv(OUT / "data" / "md5.csv", index=False)
    num("mdTotal", int(m["md5"].sum()))
    num("mdCases", int((m["md5"] > 0).sum()))
    num("mdRows", len(m))
    num("mdBRows", int((m["panel"] == "3b").sum()))
    num("mdBCases", int(((m["panel"] == "3b") & (m["md5"] > 0)).sum()))
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6), gridspec_kw={"wspace": 0.05})
    for ax, panel in zip(axes, ["3r", "3b"]):
        d = m[m["panel"] == panel].copy()
        d["col"] = list(zip(d["build"].map({"0.1.4": 0, "0.1.12": 1}), d["rep"]))
        p = d.pivot_table(index="arm", columns="col", values="md5", aggfunc="sum")
        p = p[sorted(p.columns)]
        order = [a for a, *_ in ARMS if a in p.index]
        p = p.loc[order]
        ax.imshow(p.values, cmap=CMAP, vmin=0, vmax=max(8, np.nanmax(p.values)), aspect="auto")
        for i in range(p.shape[0]):
            for j in range(p.shape[1]):
                v = p.values[i, j]
                if np.isnan(v):
                    continue
                ax.text(j, i, f"{int(v)}", ha="center", va="center", fontsize=7,
                        color="white" if v > 4 else (MUTED if v == 0 else INK))
        ax.set_xticks(range(p.shape[1]))
        ax.set_xticklabels([f"r{r}" for _, r in p.columns], fontsize=7)
        n014 = sum(1 for b, _ in p.columns if b == 0)
        ax.axvline(n014 - 0.5, color="white", lw=3)
        ax.text((n014 - 1) / 2, p.shape[0] - 0.1, "0.1.4", ha="center", va="top", fontsize=7, color=INK2)
        ax.text(n014 + (p.shape[1] - n014 - 1) / 2, p.shape[0] - 0.1, "0.1.12", ha="center", va="top",
                fontsize=7, color=INK2)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([ARM_LABEL[a] for a in order] if panel == "3r" else [])
        ax.set_title(PANEL_NAME[panel])
        ax.grid(False)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
    save(fig, "md5")


def ctrl_cases(r3: pd.DataFrame) -> pd.DataFrame:
    r3 = r3.copy()
    r3["wall_c"] = np.where(r3["status"].eq("TIMEOUT"), 7200.0, r3["wall_s"])
    r3["ratio"] = r3["wall_c"] / r3.groupby(["panel", "rep"])["wall_c"].transform("min")
    return r3


def fig_rounds(r2: pd.DataFrame, r3: pd.DataFrame) -> None:
    r3 = ctrl_cases(r3)
    r3.to_csv(OUT / "data" / "round3.csv", index=False)
    panels = ["4r", "4b", "4h", "4s", "4g", "4m"]
    cols = [(p, r) for p in panels for r in (1, 2, 3)]
    order = [a for a, *_ in CTRL]
    mat = np.array([[float(r3[(r3["arm"] == a) & (r3["panel"] == p) & (r3["rep"] == r)]["ratio"].iloc[0])
                     for p, r in cols] for a in order])
    tmo = np.array([[bool(r3[(r3["arm"] == a) & (r3["panel"] == p) & (r3["rep"] == r)]["status"].eq("TIMEOUT").iloc[0])
                     for p, r in cols] for a in order])
    fig, ax = plt.subplots(figsize=(7.0, 2.7))
    ax.imshow(mat, cmap=CMAP, norm=LogNorm(vmin=1, vmax=6), aspect="auto")
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat[i, j]
            s = (">" if tmo[i, j] else "") + (f"{v:.2f}" if v < 10 else f"{v:.0f}")
            ax.text(j, i, s, ha="center", va="center", fontsize=6.3,
                    color="white" if v > 2.2 else (INK if v > 1.0001 else INK), fontweight="bold" if v == 1 else "normal")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([f"r{r}" for p, r in cols], fontsize=6.5)
    for k, p in enumerate(panels):
        ax.text(3 * k + 1, -0.9, PANEL_NAME[p], ha="center", va="bottom", fontsize=7.5, color=INK2)
        if k:
            ax.axvline(3 * k - 0.5, color="white", lw=2)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([CTRL_LABEL[a] for a in order])
    ax.grid(False)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "round3_heat")

    # mean connections vs mean ratio
    agg = r3.groupby("arm").agg(ratio=("ratio", "mean"), conn=("conn_mean", "mean"),
                                worst=("ratio", "max"), wins=("ratio", lambda s: int((s <= 1.10).sum())))
    agg = agg.loc[order]
    agg.to_csv(OUT / "data" / "round3_summary.csv")
    fig, ax = plt.subplots(figsize=(4.2, 2.9))
    for a, r in agg.iterrows():
        fixed = "fixed" in a
        ax.scatter(r["conn"], r["ratio"], s=40, marker="s" if fixed else "o", color=SLOT[1] if fixed else SLOT[0],
                   edgecolor="white", lw=1, zorder=3)
        off = {"adaptiseq-ctrl-greedy": (4, 6), "adaptiseq-fixed-j64": (6, -9),
               "adaptiseq-ctrl-topdown": (-6, 7)}.get(a, (5, 3))
        ax.annotate(CTRL_LABEL[a], (r["conn"], r["ratio"]), xytext=off, textcoords="offset points",
                    fontsize=7.5, color=INK2, ha="right" if off[0] < 0 else "left")
    ax.scatter([], [], marker="o", color=SLOT[0], label="adaptive controller")
    ax.scatter([], [], marker="s", color=SLOT[1], label="fixed worker count")
    ax.legend(loc="upper right")
    ax.set_xlabel("mean open connections, 18 cases")
    ax.set_ylabel("mean ratio to the fastest arm")
    save(fig, "round3_conn")
    for a, tag in (("adaptiseq-ctrl-topdown", "Td"), ("adaptiseq-fixed-j64", "Jsf"), ("adaptiseq-fixed-j20", "Jtw"),
                   ("adaptiseq-ctrl-knee", "Kn"), ("adaptiseq-ctrl-budget", "Bu"), ("adaptiseq-ctrl-greedy", "Gr"),
                   ("adaptiseq-ctrl-bottomup", "Bo")):
        num(f"rt{tag}Ratio", agg.loc[a, "ratio"], "{:.2f}")
        num(f"rt{tag}Conn", agg.loc[a, "conn"], "{:.1f}")
        num(f"rt{tag}Worst", agg.loc[a, "worst"], "{:.2f}")
        num(f"rt{tag}Wins", int(agg.loc[a, "wins"]))

    # noise: spread of one arm across reps vs spread across arms within one rep
    across_reps, across_arms = [], []
    for (p, a), g in r3.groupby(["panel", "arm"]):
        across_reps.append(g["wall_c"].max() / g["wall_c"].min())
    for (p, r), g in r3.groupby(["panel", "rep"]):
        across_arms.append(g["wall_c"].max() / g["wall_c"].min())
    num("noiseReps", np.median(across_reps), "{:.2f}")
    num("noiseArms", np.median(across_arms), "{:.2f}")
    num("noiseRepsMax", np.max(across_reps), "{:.1f}")
    # which arm wins each case
    winners = r3.loc[r3.groupby(["panel", "rep"])["ratio"].idxmin(), "arm"]
    num("distinctWinners", winners.nunique())
    pw = r3.loc[r3.groupby(["panel", "rep"])["ratio"].idxmin()].groupby("panel")["arm"].nunique()
    num("panelsChangingWinner", int((pw > 1).sum()))

    # spread figure: per panel, wall time by rep for each arm (lines connect reps)
    fig, axes = plt.subplots(2, 3, figsize=(7.0, 4.2), gridspec_kw={"wspace": 0.35, "hspace": 0.5})
    for ax, p in zip(axes.flat, panels):
        d = r3[r3["panel"] == p]
        for a, lab, col, mk in CTRL:
            g = d[d["arm"] == a].sort_values("rep")
            ax.plot(g["rep"], g["wall_c"], color=col, lw=1, marker=mk, ms=3.5, mec="white", mew=0.5,
                    label=lab if p == panels[0] else None)
        logaxis(ax)
        ax.set_xticks([1, 2, 3])
        ax.set_xlim(0.7, 3.3)
        ax.set_title(PANEL_NAME[p], fontsize=8, fontweight="normal")
        ax.set_xlabel("rep", fontsize=7.5)
    for ax in axes[:, 0]:
        ax.set_ylabel("wall time (s)")
    fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.02), ncol=4, fontsize=7.5)
    save(fig, "round3_reps")


def fig_variability(frames) -> None:
    """The same configuration (fixed -j 20) on the same lists, run after run."""
    rows = []
    for df, build in frames:
        g = df[(df["arm"] == "adaptiseq-fixed-j20") & df["dataset"].isin(["D1_full_PRJNA916347", "D2_subset_PRJNA762469"])]
        for _, r in g.iterrows():
            rows.append({"t": r["stamp"], "dataset": r["dataset"], "wall_s": r["wall_s"],
                         "MBps": r["MBps_verified"], "build": build, "runs_ok": r["runs_complete"] == r["runs_expected"]})
    v = pd.DataFrame(rows).dropna(subset=["t"])
    v.to_csv(OUT / "data" / "variability.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6), gridspec_kw={"wspace": 0.25})
    builds = list(dict.fromkeys(v["build"]))
    marks = ["o", "s", "D", "^", "v"]
    for ax, ds, title in zip(axes, ["D1_full_PRJNA916347", "D2_subset_PRJNA762469"],
                             ["(a) 241 small runs, 7.6 GB", "(b) 8 large runs, 25.9 GB"]):
        d = v[v["dataset"] == ds]
        for k, b in enumerate(builds):
            g = d[d["build"] == b]
            ax.scatter(g["t"], g["MBps"], s=22, marker=marks[k], color=SLOT[k], edgecolor="white", lw=0.8,
                       label=b if ds.startswith("D1") else None)
        logaxis(ax)
        ax.set_title(title)
        datefmt(ax)
        tag = "R" if ds.startswith("D1") else "B"
        num(f"var{tag}Min", d["MBps"].min(), "{:.1f}")
        num(f"var{tag}Max", d["MBps"].max(), "{:.1f}")
        num(f"var{tag}Fold", d["MBps"].max() / d["MBps"].min(), "{:.0f}")
        num(f"var{tag}N", len(d))
    axes[0].set_ylabel("verified MB/s, fixed -j 20")
    axes[0].legend(loc="lower left", title="build", title_fontsize=7)
    save(fig, "variability")


def table_chain(ch: pd.DataFrame) -> None:
    """LaTeX longtable body: every chain row."""
    lines = []
    for panel in ("3r", "3b"):
        for rep in range(1, 6):
            d = ch[(ch["panel"] == panel) & (ch["rep"] == rep)].sort_values("wall_s")
            for _, r in d.iterrows():
                lab = {"adaptiseq-default": "adaptiSeq default", "adaptiseq-fixed-j20": "adaptiSeq \\code{-j} 20",
                       "iseq-p8": "iSeq \\code{-p} 8", "iseq": "iSeq", "kingfisher": "Kingfisher",
                       "fastq-dl": "fastq-dl"}[r["arm"]]
                runs = f"{int(r['runs_complete'])}/{int(r['runs_expected'])}"
                if r["runs_present_unverified"]:
                    runs += f" (+{int(r['runs_present_unverified'])})"
                st = {"ok": "0", "TIMEOUT": "limit"}.get(r["status"], str(int(r["exit_code"])))
                ratio = (">" if r["timeout"] else "") + f"{r['ratio']:.2f}"
                lines.append(f"{panel} & {rep} & {lab} & {r['wall_s']:,.0f} & {ratio} & {runs} & {st} & "
                             f"{r['MBps_verified']:.2f} & {r['conn_mean']:.1f}/{int(r['conn_max'])} & {int(r['md5_mismatch'])} \\\\")
            lines.append("\\midrule")
    head = ("\\begin{longtable}{@{}lllrrlrrrr@{}}\n"
            "\\caption{Every row of the 0.1.12 chain. Ratio: wall time over fixed \\code{-j}~20 in the same repetition. "
            "Runs: md5-verified of expected, (+N) present but unverified. Exit: 0, non-zero code, or ``limit''. "
            "MB/s: md5-verified bytes over wall time. Conn.: mean/max archive connections. md5: mismatch reports in the log.}\n"
            "\\label{tab:chain}\\\\\n\\toprule\n"
            "Panel & Rep & Arm & Wall (s) & Ratio & Runs & Exit & MB/s & Conn. & md5 \\\\\n\\midrule\n\\endfirsthead\n"
            "\\toprule\nPanel & Rep & Arm & Wall (s) & Ratio & Runs & Exit & MB/s & Conn. & md5 \\\\\n\\midrule\n\\endhead\n")
    (OUT / "data" / "chain_table.tex").write_text(head + "\n".join(lines[:-1]) + "\n\\bottomrule\n\\end{longtable}\n")


def table_round3(r3: pd.DataFrame) -> None:
    agg = pd.read_csv(OUT / "data" / "round3_summary.csv", index_col=0)
    lines = []
    for a, r in agg.iterrows():
        lines.append(f"{CTRL_LABEL[a]} & {int(r['wins'])} & {r['worst']:.2f} & {r['ratio']:.2f} & {r['conn']:.1f} \\\\")
    (OUT / "data" / "round3_table.tex").write_text(
        "\\begin{tabular}{@{}lrrrr@{}}\n\\toprule\nArm & Wins & Worst & Mean & Conn. \\\\\n\\midrule\n"
        + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")


def main() -> None:
    global ROOT, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--portal", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()
    ROOT, OUT = args.root.resolve(), args.out.resolve()
    (OUT / "figs").mkdir(exist_ok=True)
    (OUT / "data").mkdir(exist_ok=True)

    c014 = load_campaign("e3_submission_expanse/e3_549270*/e3_results.tsv", "0.1.4")
    c014 = c014[c014["job"].isin(["e3_54927001", "e3_54927008", "e3_54927009"])]
    v15 = load_campaign("e3_v015_expanse/e3_*/e3_results.tsv", "0.1.5")
    v16 = load_campaign("e3_v016_expanse/e3_*/e3_results.tsv", "0.1.6")
    v17 = load_campaign("e3_v017_expanse/e3_*/e3_results.tsv", "0.1.7")
    sw = load_campaign("e3_jsweep_expanse/e3_*/e3_results.tsv", "0.1.7 sweep")
    r2 = load_campaign("e3_round2_expanse/e3_*/e3_results.tsv", "0.1.11")
    r3 = add_conn_md5(load_campaign("e3_round3_expanse/e3_*/e3_results.tsv", "0.1.12 round 3"))
    ch = add_conn_md5(load_campaign("e3_submission_0.1.12_expanse/e3_*/e3_results.tsv", "0.1.12 chain"))
    c014 = add_conn_md5(c014)

    fig_portal(args.portal)
    fig_probe()
    fig_jsweep(sw)
    fig_versions(c014, v15, v16, v17, r2, r3, ch)
    fig_tail(c014, ch)
    fig_ftp(ch)
    ch = fig_chain(ch)
    fig_md5(c014, ch)
    fig_rounds(r2, r3)
    fig_variability([(c014, "0.1.4"), (r2, "0.1.11"), (r3, "0.1.12 (round 3)"), (ch, "0.1.12 (chain)")])
    table_chain(ch)
    table_round3(r3)

    # chain dates and per-rep probe
    num("chainStart", ch["stamp"].min().tz_convert("US/Pacific").strftime("%b %-d"))
    num("chainEnd", ch["stamp"].max().tz_convert("US/Pacific").strftime("%b %-d"))
    with open(OUT / "numbers.tex", "w") as fh:
        fh.write("% generated by make_figures.py; do not edit\n")
        for k in sorted(NUM):
            fh.write(f"\\newcommand{{\\{k}}}{{{NUM[k]}}}\n")
    print(f"{len(NUM)} numbers, figures in {OUT/'figs'}")


if __name__ == "__main__":
    main()
