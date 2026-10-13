#!/usr/bin/env python3
"""Is this E3 results TSV complete and fit to analyse?

Run it after the gate (one rep of 3r + 3b) and again after the full run. It
checks what analyze_submission.py assumes, and says which assumption failed:

  * every submission arm wrote exactly one row for every panel x rep;
  * all rows carry one adaptiSeq version and one build hash;
  * the build hash is a wheel sha256, not a `tree:` fallback (i.e. the run was
    pinned to a release wheel with E3_ASEQ_WHEEL);
  * the arm order differs between reps (the shuffle is doing something);
  * no arm timed out, and which arms exited non-zero or left runs incomplete.

The last item is reported, not failed: a competitor dropping runs is a result.

    python bench/e3/check_run.py --tsv e3_results.tsv --panels 3r 3b --reps 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ARMS = ["adaptiseq-default", "adaptiseq-fixed-j20", "iseq-p8", "iseq", "kingfisher", "fastq-dl"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True, type=Path)
    ap.add_argument("--panels", nargs="+", default=["3r", "3b"])
    ap.add_argument("--reps", type=int, default=5)
    args = ap.parse_args()

    df = pd.read_csv(args.tsv, sep="\t", dtype={"aseq_version": str, "aseq_sha256": str})
    df = df[df["panel"].isin(args.panels)]
    problems: list[str] = []
    notes: list[str] = []

    for panel in args.panels:
        for arm in ARMS:
            for rep in range(1, args.reps + 1):
                n = len(df[(df["panel"] == panel) & (df["arm"] == arm) & (df["rep"] == rep)])
                if n != 1:
                    problems.append(f"{panel} {arm} rep{rep}: {n} rows (want 1)")

    builds = sorted({(v, h) for v, h in zip(df["aseq_version"], df["aseq_sha256"])})
    if len(builds) != 1:
        problems.append(f"{len(builds)} adaptiSeq builds in one TSV: {builds}")
    elif builds[0][1].startswith("tree:") or builds[0][1] in ("-", "nan"):
        problems.append(f"build not pinned to a release wheel (aseq_sha256={builds[0][1]}); "
                        "set E3_ASEQ_WHEEL")
    else:
        notes.append(f"adaptiSeq {builds[0][0]}  wheel sha256 {builds[0][1]}")

    if args.reps > 1:
        for panel in args.panels:
            d = df[df["panel"] == panel].sort_values(["rep", "order_idx"])
            orders = {tuple(g["arm"]) for _, g in d.groupby("rep")}
            if len(orders) < 2:
                problems.append(f"{panel}: arm order is identical in every rep")
            first = d[d["order_idx"] == 1]["arm"].value_counts()
            notes.append(f"{panel}: {len(orders)} distinct arm orders; ran first: "
                         + ", ".join(f"{a} x{n}" for a, n in first.items()))

    for _, r in df[df["status"] == "TIMEOUT"].iterrows():
        problems.append(f"{r['panel']} {r['arm']} rep{r['rep']}: TIMEOUT after {r['wall_s']}s")

    for _, r in df.iterrows():
        if r["exit_code"] != 0 or r["runs_complete"] != r["runs_expected"]:
            extra = ""
            if r.get("runs_present_unverified", 0):
                extra = f", {int(r['runs_present_unverified'])} present but not byte-identical to ENA"
            notes.append(f"{r['panel']} {r['arm']} rep{r['rep']}: exit {r['exit_code']}, "
                         f"{r['runs_complete']}/{r['runs_expected']} runs verified{extra}")

    for line in notes:
        print("note    " + line)
    for line in problems:
        print("PROBLEM " + line)
    print("CHECK FAIL" if problems else "CHECK PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
