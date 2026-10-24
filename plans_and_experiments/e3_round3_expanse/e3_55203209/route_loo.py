import csv, glob, statistics, math
from collections import defaultdict
W = {}; OK = {}
for f in glob.glob("e3_round2_expanse/e3_*/e3_results.tsv"):
    for r in csv.DictReader(open(f), delimiter="\t"):
        k = (r["panel"], r["rep"], r["arm"].replace("adaptiseq-", ""))
        W[k] = float(r["wall_s"]); OK[k] = r["exit_code"] == "0" and r["runs_complete"] == r["runs_expected"]
panels = sorted({k[0] for k in W}); reps = sorted({k[1] for k in W}); arms = sorted({k[2] for k in W})
ratio = {k: W[k] / min(W[(k[0], k[1], a)] for a in arms) for k in W}
gm = lambda xs: math.exp(sum(map(math.log, xs)) / len(xs))
print("Per-panel winner each rep (arm, ratio of runner-up):")
for p in panels:
    print(f"  {p}: " + ", ".join(min(arms, key=lambda a: W[(p, r, a)]) for r in reps))
# Leave-one-rep-out: choose on two reps, score on the third.
res = defaultdict(list)   # policy -> list of held-out ratios
picks = defaultdict(list)
for held in reps:
    train = [r for r in reps if r != held]
    # one arm for everything: best geomean over all panels in the training reps
    single = min(arms, key=lambda a: gm([ratio[(p, r, a)] for p in panels for r in train]))
    picks["single"].append(single)
    for p in panels:
        routed = min(arms, key=lambda a: gm([ratio[(p, r, a)] for r in train]))
        picks[p].append(routed)
        res["routed per panel"].append(ratio[(p, held, routed)])
        res["single best arm"].append(ratio[(p, held, single)])
        for a in arms:
            res["always " + a].append(ratio[(p, held, a)])
        res["oracle (in hindsight)"].append(1.0)
print("\nHeld-out picks: single arm by rep:", picks["single"])
for p in panels: print(f"  routed {p} by held-out rep:", picks[p])
print("\npolicy                      geomean  median  wins(<=1.1)/18  worst")
for k, v in sorted(res.items(), key=lambda kv: gm(kv[1])):
    print(f"  {k:26s} {gm(v):6.2f}  {statistics.median(v):6.2f}  {sum(x <= 1.1 for x in v):5d}           {max(v):5.2f}")
