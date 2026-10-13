#!/usr/bin/env python3
"""Aggregate E7 into Table 3 + the resume bar + the circuit-breaker trace figure.

Reads the three TSVs run_e7.sh writes into --outdir:
  e7_results.tsv   corpus success/integrity (7a) + 3-file completion (7e)
  e7_resume.tsv    resume correctness (7b)
  e7_engine.tsv    never-truncate / corruption (7c) + circuit breaker (7d)

Everything is robust to partial data: a sub-experiment that did not run just
prints nothing. Figures are skipped (not fatal) if matplotlib is unavailable.
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


def corpus_table(df: pd.DataFrame) -> None:
    df = df.copy()
    df["success_pct"] = 100 * df["runs_complete"] / df["runs_expected"].clip(lower=1)
    df["md5_pct"] = 100 * df["md5_pass_rate"]
    g = df.groupby(["subexp", "tool"]).agg(
        reps=("rep", "nunique"),
        runs_complete_med=("runs_complete", "median"),
        runs_expected=("runs_expected", "max"),
        success_pct=("success_pct", "median"),
        md5_pct=("md5_pct", "median"),
        retries_med=("retries", "median"),
        fail_log_med=("fail_log_n", "median"),
        wall_med=("wall_s", "median"),
    ).reset_index()
    print("\n=== Table 3 — corpus success / integrity (7a) & 3-file completion (7e) ===")
    print(f"{'sub':4} {'tool':12} {'reps':>4} {'runs':>10} {'succ%':>6} "
          f"{'md5%':>6} {'retry':>6} {'fail':>5} {'wall_s':>8}")
    for _, r in g.iterrows():
        runs = f"{int(r.runs_complete_med)}/{int(r.runs_expected)}"
        print(f"{r.subexp:4} {r.tool:12} {int(r.reps):>4} {runs:>10} "
              f"{r.success_pct:6.1f} {r.md5_pct:6.1f} {int(r.retries_med):>6} "
              f"{int(r.fail_log_med):>5} {r.wall_med:8.1f}")


def resume_table_and_fig(df: pd.DataFrame, outdir: Path) -> None:
    print("\n=== Table 3 — resume correctness (7b): kill → restart ===")
    df = df.copy()
    df["wasted_frac"] = df["bytes_wasted"] / df["file_bytes"].clip(lower=1)
    print(f"{'tool':12} {'kill':>5} {'verdict':>10} {'wasted%':>8} "
          f"{'md5ok':>6} {'n':>3}")
    for (tool, frac), sub in df.groupby(["tool", "kill_frac"]):
        verdict = sub["verdict"].mode().iloc[0] if len(sub) else "-"
        print(f"{tool:12} {frac:5.2f} {verdict:>10} "
              f"{100*sub['wasted_frac'].median():8.2f} "
              f"{100*sub['final_md5_ok'].mean():6.0f} {len(sub):>3}")

    if not HAVE_MPL:
        return
    try:
        piv = (df.groupby(["tool", "kill_frac"])["wasted_frac"].median()
                 .unstack("kill_frac") * 100)
        ax = piv.plot(kind="bar", figsize=(7, 4))
        ax.set_ylabel("bytes re-downloaded (% of file)")
        ax.set_xlabel("tool")
        ax.set_title("E7b — resume waste per kill fraction (0% = perfect resume)")
        ax.legend(title="kill @")
        plt.tight_layout()
        plt.savefig(outdir / "fig_e7b_resume.png", dpi=130)
        plt.close()
        print(f"  wrote {outdir / 'fig_e7b_resume.png'}")
    except Exception as exc:
        print(f"  (resume figure skipped: {exc})")


def engine_table(df: pd.DataFrame) -> None:
    print("\n=== Table 3 — never-truncate / corruption (7c) & circuit breaker (7d) ===")
    print(f"{'check':16} {'mode':18} {'pass/total':>11}  detail (last)")
    for (check, mode), sub in df.groupby(["check", "mode"]):
        npass = (sub["passed"] == "PASS").sum()
        total = len(sub)
        detail = str(sub["detail"].iloc[-1])[:60]
        print(f"{check:16} {mode:18} {npass:>5}/{total:<5}  {detail}")


def hostguard_fig(outdir: Path) -> None:
    if not HAVE_MPL:
        return
    logs = outdir / "logs"
    traces = sorted(logs.glob("hostguard_synth_rep*.tsv")) if logs.exists() else []
    if not traces:
        return
    try:
        fig, ax = plt.subplots(figsize=(7, 4))
        for t in traces[:5]:
            d = pd.read_csv(t, sep="\t")
            ax.step(d["t_rel_s"], d["cap"], where="post", label=t.stem.split("_")[-1])
        ax.set_xlabel("time (s)")
        ax.set_ylabel("HostGuard per-host cap")
        ax.set_title("E7d — circuit breaker: cap halves on 429, recovers after")
        ax.legend(title="rep")
        plt.tight_layout()
        plt.savefig(outdir / "fig_e7d_circuit_breaker.png", dpi=130)
        plt.close()
        print(f"  wrote {outdir / 'fig_e7d_circuit_breaker.png'}")
    except Exception as exc:
        print(f"  (circuit-breaker figure skipped: {exc})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="e7_results")
    ap.add_argument("--tsv", help="corpus TSV (default <outdir>/e7_results.tsv)")
    args = ap.parse_args()
    out = Path(args.outdir)

    corpus = _read(Path(args.tsv) if args.tsv else out / "e7_results.tsv")
    resume = _read(out / "e7_resume.tsv")
    engine = _read(out / "e7_engine.tsv")

    if corpus is not None:
        corpus_table(corpus)
    if resume is not None:
        resume_table_and_fig(resume, out)
    if engine is not None:
        engine_table(engine)
    hostguard_fig(out)

    if corpus is None and resume is None and engine is None:
        print(f"[warn] no E7 TSVs found in {out.resolve()}")
        return 1
    print(f"\nFigures + tables in {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
