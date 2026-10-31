import csv, glob, os, re, statistics
from collections import defaultdict
rows = {}
for f in glob.glob("e3_round2_expanse/e3_*/e3_results.tsv"):
    for r in csv.DictReader(open(f), delimiter="\t"):
        r["_dir"] = os.path.dirname(f)
        rows[(r["panel"], r["rep"], r["arm"].replace("adaptiseq-", ""))] = r
def conc(r):
    hits = glob.glob(os.path.join(r["_dir"], "logs", f"conc_{r['panel']}_*_{r['arm']}_rep{r['rep']}.tsv"))
    out = []
    for ln in open(hits[0]).read().splitlines()[1:]:
        p = ln.split("\t")
        try: out.append((float(p[0]), float(p[3])))
        except: pass
    return out
def deciles(c, wall):
    b = defaultdict(list)
    for t, n in c:
        b[min(9, int(10 * t / max(wall, 1)))].append(n)
    return " ".join(f"{statistics.mean(b[i]):4.0f}" if b[i] else "   -" for i in range(10))
def summary(r):
    hits = glob.glob(os.path.join(r["_dir"], "logs", f"{r['panel']}_*_{r['arm']}_rep{r['rep']}.log"))
    txt = re.sub(r"\x1b\[[0-9;]*m", "", open(hits[0]).read())
    m = re.findall(r"adaptive worker summary: (.*)", txt)
    return m[-1] if m else "(no summary)"
cases = sorted({(p, rep) for p, rep, _ in rows})
for p, rep in cases:
    c = {a: r for (pp, rr, a), r in rows.items() if (pp, rr) == (p, rep)}
    best_a = min(c, key=lambda a: float(c[a]["wall_s"]))
    bw = float(c[best_a]["wall_s"]); td = c["ctrl-topdown"]; tw = float(td["wall_s"])
    if tw <= 1.1 * bw: continue
    print(f"=== {p} rep{rep}: topdown {tw:.0f}s ({tw/bw:.2f}x, {td['runs_complete']}/{td['runs_expected']}) vs {best_a} {bw:.0f}s; order td={td['order_idx']} best={c[best_a]['order_idx']}")
    for a in ("ctrl-topdown", best_a):
        r = c[a]; cc = conc(r)
        print(f"  {a:13s} conns by decile of its run: {deciles(cc, float(r['wall_s']))}  mean {statistics.mean(n for _, n in cc):.1f}")
    print("  topdown:", summary(td)[:400])
