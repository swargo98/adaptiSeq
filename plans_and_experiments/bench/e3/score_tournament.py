#!/usr/bin/env python3
"""Score the controller tournament by the rule fixed before it ran (progress_log.md, section 4: "Selection rule").

For every panel: median wall_s over reps per arm; score = median / the best arm's
median in that panel (fixed references included). An arm that missed a run (not
md5-verified complete) or exited non-zero in any rep is out. Ranking: lowest
worst-case score over panels, then the geometric mean.

    python bench/e3/score_tournament.py e3_tournament_expanse/e3_*/e3_results.tsv
"""
import csv
import math
import statistics
import sys
from collections import defaultdict


def main(paths):
    walls, ok = defaultdict(list), defaultdict(lambda: True)
    for path in paths:
        for r in csv.DictReader(open(path), delimiter="\t"):
            arm = r["arm"].replace("adaptiseq-ctrl-", "").replace("adaptiseq-", "")
            k = (r["panel"], arm)
            walls[k].append(float(r["wall_s"]))
            if r["exit_code"] != "0" or r["runs_complete"] != r["runs_expected"]:
                ok[k] = False
    panels = sorted({p for p, _ in walls})
    arms = sorted({a for _, a in walls})
    med = {k: statistics.median(v) for k, v in walls.items()}
    score = defaultdict(dict)
    print("panel\tarm\treps\tmedian_s\twalls_s\tcomplete\tscore")
    for p in panels:
        best = min(med[(p, a)] for a in arms if (p, a) in med)
        for a in arms:
            if (p, a) in med:
                score[a][p] = med[(p, a)] / best
                print(f"{p}\t{a}\t{len(walls[(p, a)])}\t{med[(p, a)]:.1f}\t"
                      f"{','.join(f'{x:.1f}' for x in walls[(p, a)])}\t{ok[(p, a)]}\t"
                      f"{score[a][p]:.3f}")
    print("\narm\tpanels\tworst\tgeomean\tqualifies")
    ranked = []
    for a in arms:
        sc = score[a]
        worst = max(sc.values())
        gm = math.exp(sum(math.log(x) for x in sc.values()) / len(sc))
        qual = all(ok[(p, a)] for p in sc)
        ranked.append((not qual, worst, gm, a))
        print(f"{a}\t{len(sc)}\t{worst:.3f}\t{gm:.3f}\t{qual}")
    ranked.sort()
    print("\norder (qualifying first, by worst case, then geometric mean):",
          " > ".join(a for *_, a in ranked))


if __name__ == "__main__":
    main(sys.argv[1:])
