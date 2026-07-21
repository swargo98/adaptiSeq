# E10 — Parallel metadata resolution & rate-limit etiquette (Findings)

**Contribution tested:** C3b — *parallel, rate-limited metadata resolution*
(`--meta-jobs`). Claim: resolution parallelism hides per-accession RTT **while**
the request rate to every endpoint stays pinned at its documented cap — "concurrent
*but* well-behaved." Ran on **Fabric** (Node-FIU), 2026-07-21. Resolution only;
**no sequencing bytes transferred.** Panel 10c is fully local/deterministic.

Raw data: `e10_resolve.tsv` (10a/10b), `e10_etiquette.tsv` (10c),
`e10_summary.txt`. Figures: `fig8a_resolution_throughput.png`,
`fig8b_etiquette.png`, `fig8c_tool_rate.png`.

---

## TL;DR

1. **Parallel resolution scales ~4.5× then saturates at the endpoint rate cap —
   by design.** Resolving 150 ENA run accessions: `--meta-jobs 1` = 1.75 acc/s,
   `--meta-jobs 8` = **7.80 acc/s** (4.4×). Past `meta-jobs 8` it is flat (7.80 at
   mj16) because ENA's cap is 8 rps — the pool stops mattering exactly where
   politeness says it should.
2. **adaptiSeq resolves ~5× faster than the fastest competitor and up to 16×
   faster than the slowest**, purely by overlapping RTT (none of them parallelise
   resolution): iseq 1.51, pysradb 1.06, kingfisher 1.00, ffq 0.48 acc/s vs
   adaptiSeq 7.80 acc/s.
3. **The etiquette guarantee holds exactly.** With the per-endpoint limiter, peak
   NCBI request rate is **3 rps at every `--meta-jobs` from 1 to 16** (flat at the
   cap, never over). A naive resolver with the same pool blows past it linearly:
   **8 → 22 → 56 → 96 rps** (up to **32× over** NCBI's 3-rps cap). This is the
   IP-ban failure mode the design prevents.
4. **The cap is respected, not hard-coded low.** Set `NCBI_API_KEY` and the
   limiter tracks the raised 10-rps allowance (peak rises to 8, still under 10);
   the naive resolver is over even the 10-rps cap from `meta-jobs 3` up.

---

## 10a — Resolution throughput (Fig 8a, Fig 8c)

`batch.resolve_all(accessions, meta_jobs=N)` called directly (the public
`resolve()` / CLI `-m` are serial; the parallel path only runs inside the download
batch phase, so this is the honest isolation of C3b). ENA run list (D1_full),
N ∈ {50, 150}, `meta-jobs ∈ {1,3,8,16}`, 3 reps. Each accession = **1 ENA
filereport request** (verified via a `net._run` spy — see `ena_reqs` column).

| N | mj=1 | mj=3 | mj=8 | mj=16 | speedup (mj16/mj1) |
|---|------|------|------|-------|--------------------|
| 50 | 1.76 | 5.05 | 7.46 | 7.46 | **4.2×** |
| 150 | 1.75 | 5.19 | 7.80 | 7.80 | **4.4×** |

Throughput climbs with the pool, then **flattens at ≈7.8 acc/s = ENA's 8-rps
cap**. The flattening is the *point* (Fig 8a): more workers cannot — and must not —
raise the per-endpoint request rate.

**Competitors (serial CLIs, one process per accession, N=20):**

| tool | acc/s | invocation |
|------|-------|------------|
| **adaptiSeq (mj8)** | **7.80** | `resolve_all(..., meta_jobs=8)` |
| iseq | 1.51 | `iseq -i ACC -m` |
| pysradb | 1.06 | `pysradb metadata ACC` |
| kingfisher | 1.00 | `kingfisher annotate -r ACC` |
| ffq | 0.48 | `ffq ACC` |

None of the competitors parallelise resolution, so each is bounded by ~`1/RTT`.
adaptiSeq's advantage is *overlapping* that RTT up to the polite cap — a **5.2×**
edge over the fastest (iseq) and **16×** over the slowest (ffq). We do **not**
claim adaptiSeq resolves an individual accession faster; it resolves *many* at
once, safely.

**Mixed multi-DB list (D4_mixed: 12 ENA + 6 SRA-only + 2 GSA).** Exercises the
ENA→SRA→GSA preference chain (18 ENA + 8 GSA requests measured). GSA runs cost 4
requests each through a slow browse-page scrape, so absolute throughput is lower
(mj1 0.61 → mj16 2.43 acc/s, **4.0×**) and saturates against GSA's 5-rps cap. Same
qualitative story on a harder, real, cross-database workload.

---

## 10b — Overlap value (Fig 8c inset)

Resolution wall-time for the same 150-accession ENA batch, `--meta-jobs 1` vs `8`
(3 reps):

| meta-jobs | resolution wall |
|-----------|-----------------|
| 1 | 85.4 s |
| 8 | 19.2 s |

Parallel resolution cuts the resolve phase **4.4×** (85.4 s → 19.2 s). This is the
per-run RTT that iSeq's serial resolver pays in full and that batching *hides*
behind transfer — a 66-second saving on a list this small, before a single byte is
downloaded. On a real download the resolve phase overlaps transfer entirely, so
the marginal cost of resolution collapses toward zero.

---

## 10c — Etiquette / decoupling proof (Fig 8b) — the key panel

**Local & deterministic**, driving the **production** `ratelimits.EndpointLimiters`
/ `RateLimiter.acquire` (unmodified) with the real per-accession endpoint-request
pattern through a `ThreadPoolExecutor(meta-jobs)` that mirrors `resolve_all`. Only
the "network" is a fixed 50 ms simulated latency — so this is reproducible on any
machine and never floods a live endpoint. 120 synthetic accessions
(40% true-SRA-only → NCBI-stressing, 40% ENA, 20% GSA). Metric: **peak request
rate in any 1-second window**, per endpoint.

**Peak NCBI request rate (rps) vs `--meta-jobs`:**

| arm | key mode | NCBI cap | mj=1 | mj=3 | mj=8 | mj=16 |
|-----|----------|----------|------|------|------|-------|
| **limiter (adaptiSeq)** | no key | 3 | 3 | 3 | 3 | **3** |
| naive | no key | 3 | 8 ✗ | 22 ✗ | 56 ✗ | **96 ✗** |
| **limiter (adaptiSeq)** | `NCBI_API_KEY` | 10 | 4 | 8 | 8 | **8** |
| naive | `NCBI_API_KEY` | 10 | 8 | 22 ✗ | 56 ✗ | **96 ✗** |

(✗ = exceeds the documented cap.)

- **Concurrency is decoupled from request rate.** As the pool grows 1→16, the
  limiter arm's NCBI rate is **flat at 3 rps** — every over-cap flag is 0. ENA
  rises to its own 8-rps cap and pins; GSA pins at 5. (Fig 8b, left.)
- **The naive resolver blows past linearly** — 8 → 22 → 56 → 96 rps, i.e. up to
  **32× NCBI's cap** — exactly the behaviour that gets a user's IP throttled or
  banned. (Fig 8b, right.)
- **The cap is honoured, not hard-wired low.** With an API key the limiter tracks
  the higher 10-rps allowance (`ncbi_rps()` returns 10) instead of leaving
  throughput on the table.

This is the concrete evidence for C3b: adaptiSeq is the only tool here that
resolves a batch **concurrently** yet provably stays **within every server's
published rate limit**.

---

## Consistency with the master plan & honesty notes

- **Saturation is not a scaling failure.** Fig 8a flattening past `meta-jobs 8`
  (ENA) / lower for GSA is the etiquette cap doing its job (plan §7). Reported as a
  feature, not hidden.
- **NCBI panel is simulated latency, deliberately.** Live ENA now mirrors the
  plan's old "SRA-only → NCBI" picks (`SRR1031060` resolves in 1 ENA request, 0
  NCBI — verified 2026-07-21), so forcing the NCBI path live is fragile, and
  flooding NCBI to show the naive blow-out would be the very impoliteness we test
  against. 10c therefore drives the **real limiter code** with the real request
  pattern locally — the same choice E7 made with its local origin server. The
  magnitudes (3 vs 96 rps) are exact because the limiter is deterministic; only the
  RTT is stand-in.
- **Competitors resolve serially** — their ~1/RTT rate is inherent, not a
  configuration we penalised. Invocations are metadata-only and listed above.
- **What we do not claim:** faster single-accession resolution, or raw throughput
  supremacy. The claim is *batch* resolution that is *both* fast *and* polite.

## Reproduce

```bash
bash bench/e10/run_fabric.sh full          # smoke + 10a/10b/10c + figures
# panels:  bash bench/e10/run_e10.sh {10a|10b|10c}
# Expanse: sbatch bench/e10/e10_expanse.sbatch   (N up to 2000; 10c needs no egress)
python3 bench/e10/aggregate_e10.py --out e10_results_fabric
```
