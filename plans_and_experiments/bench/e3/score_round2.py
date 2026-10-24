#!/usr/bin/env python3
"""Score controller tournament round 2 by the user's criterion (fixed before the data).

User, 2026-10-19: "a controller that beat others in most of the cases for every
experiment, maintaining as low connection as possible."

A case is one (panel, rep). An arm wins a case when its wall time is within
TOL (default 10 %) of the fastest arm in that case. Arms are ranked by cases won;
ties by lower mean archive connections over all cases (conc_*.tsv, column 4,
mean over the samples taken while the arm ran). An arm is disqualified if, on any
panel, its median ratio to the fastest arm (over that panel's reps) is above
MAX_RATIO (default 1.5), or any run was not md5-verified complete. (Per panel,
not per case: on GSA every arm of round 1 had one case above 1.5x, so a per-case
floor would only measure GSA's luck.)

--timeout-censored (round 3 amendment, user 2026-10-23, fixed before rep 3's
data): an arm that hit the time limit (status TIMEOUT) is scored at wall = the
limit, a lower bound on its time, instead of being disqualified. Runs missing
when the arm exited by itself still disqualify it.

The output ends with three rankings (user, 2026-10-23: report all three, then
choose the default): as written, with timeouts censored, and by mean connections
(fewest first; ties to more wins).

    python bench/e3/score_round2.py e3_round2_expanse/e3_*/e3_results.tsv
"""
import argparse
import csv
import glob
import os
import statistics
from collections import defaultdict


def mean_conns(results_tsv, panel, arm, rep):
    logs = os.path.join(os.path.dirname(results_tsv), "logs")
    hits = glob.glob(os.path.join(logs, f"conc_{panel}_*_{arm}_rep{rep}.tsv"))
    if not hits:
        return None
    vals = []
    with open(hits[0]) as fh:
        next(fh, None)
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) > 3:
                try:
                    vals.append(float(parts[3]))
                except ValueError:
                    pass
    return statistics.mean(vals) if vals else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="+")
    ap.add_argument("--tol", type=float, default=0.10)
    ap.add_argument("--max-ratio", type=float, default=1.5)
    ap.add_argument("--timeout-censored", action="store_true",
                    help="score a TIMEOUT at the limit instead of disqualifying")
    a = ap.parse_args()
    cases = defaultdict(dict)          # (panel, rep) -> arm -> (wall, ok, conns)
    strict_bad = set()                 # arms with any run not verified, as written
    fail_bad = set()                   # the same, leaving out TIMEOUTs
    for path in a.tsv:
        for r in csv.DictReader(open(path), delimiter="\t"):
            arm = r["arm"]
            ok = r["exit_code"] == "0" and r["runs_complete"] == r["runs_expected"]
            if not ok:
                strict_bad.add(arm)
                if r["status"] != "TIMEOUT":
                    fail_bad.add(arm)
            if a.timeout_censored and r["status"] == "TIMEOUT":
                ok = True
            cases[(r["panel"], r["rep"])][arm] = (
                float(r["wall_s"]), ok, mean_conns(path, r["panel"], arm, r["rep"]))
    arms = sorted({arm for c in cases.values() for arm in c})
    wins, worst, conns, bad = defaultdict(int), defaultdict(float), defaultdict(list), set()
    per_panel = defaultdict(list)      # (arm, panel) -> ratios
    print("panel\trep\tfastest\t" + "\t".join(x.replace("adaptiseq-", "") for x in arms))
    for (panel, rep), c in sorted(cases.items()):
        best = min(w for w, _ok, _c in c.values())
        cells = []
        for arm in arms:
            if arm not in c:
                cells.append("-")
                continue
            w, ok, cn = c[arm]
            ratio = w / best
            worst[arm] = max(worst[arm], ratio)
            per_panel[(arm, panel)].append(ratio)
            if not ok:
                bad.add(arm)
            if ratio <= 1 + a.tol:
                wins[arm] += 1
            if cn is not None:
                conns[arm].append(cn)
            cells.append(f"{ratio:.2f}{'*' if ratio <= 1 + a.tol else ''}"
                         f"{'' if ok else '!'}")
        print(f"{panel}\t{rep}\t{best:.0f}s\t" + "\t".join(cells))
    print(f"\n(* = within {a.tol:.0%} of the fastest: a win; ! = a run not md5-verified"
          + ("; timeouts scored at the limit" if a.timeout_censored else "") + ")")
    panel_med = {}
    for (arm, panel), ratios in per_panel.items():
        panel_med[(arm, panel)] = statistics.median(ratios)
        if panel_med[(arm, panel)] > a.max_ratio:
            bad.add(arm)
    print("\narm\twins\tcases\tworst_case\tworst_panel_median\tmean_conns\tqualifies")
    ranked = []
    for arm in arms:
        n = sum(1 for c in cases.values() if arm in c)
        mc = statistics.mean(conns[arm]) if conns[arm] else float("nan")
        q = arm not in bad
        ranked.append((not q, -wins[arm], mc, arm))
        wpm = max((v for (x, _p), v in panel_med.items() if x == arm), default=float("nan"))
        print(f"{arm}\t{wins[arm]}\t{n}\t{worst[arm]:.2f}\t{wpm:.2f}\t{mc:.1f}\t{q}")
    ranked.sort()
    print("\nranking:", " > ".join(x[-1].replace("adaptiseq-", "") for x in ranked))

    # The three criteria side by side. Ratio-based disqualification (panel
    # median above MAX_RATIO) is the same under both rules; they differ only in
    # whether a TIMEOUT disqualifies.
    ratio_bad = {arm for (arm, _p), v in panel_med.items() if v > a.max_ratio}
    censored_bad = ratio_bad | fail_bad
    def rank(dq):
        r = sorted((arm in dq, -wins[arm],
                    statistics.mean(conns[arm]) if conns[arm] else float("nan"), arm)
                   for arm in arms)
        return " > ".join(x[-1].replace("adaptiseq-", "") + ("" if not x[0] else "(dq)")
                          for x in r)
    by_conns = sorted((statistics.mean(conns[arm]) if conns[arm] else float("inf"),
                       -wins[arm], arm) for arm in arms)
    print("\ncriteria (wins counted with" + (" timeouts at the limit" if a.timeout_censored
                                            else "out censoring") + "):")
    print("  1 as written:      ", rank(ratio_bad | strict_bad))
    print("  2 timeouts censored:", rank(censored_bad))
    print("  3 mean connections:", " < ".join(
        f"{x[-1].replace('adaptiseq-', '')} {x[0]:.1f}" for x in by_conns))


if __name__ == "__main__":
    main()
