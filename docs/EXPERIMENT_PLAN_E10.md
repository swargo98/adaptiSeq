# E10 — Parallel metadata resolution & rate-limit etiquette (Fig 8 + Table 4)

**Contribution:** C3b — *parallel, rate-limited metadata resolution*: `--meta-jobs`
concurrent multi-DB resolution whose request rate is **decoupled from pool size**
by per-endpoint limiters (ENA / GSA / NCBI). The claim is not "fastest downloader"
— it is **"concurrent *but* well-behaved"**: resolution parallelism hides
per-accession RTT, yet the request rate to every endpoint stays pinned at its
documented cap so adaptiSeq never trips a server throttle or gets the user's IP
blocked. This is the half of batch download (C3) that iSeq's serial resolver
cannot offer at scale.

This plan mirrors the structure of `EXPERIMENT_PLAN_E3/E5/E7/E8.md`: one driver,
strictly-sequential arms, ≤5 reps, a deterministic local panel for the part that
would be non-reproducible or impolite to run against live infrastructure, and a
single aggregator that emits every figure from one tidy TSV.

---

## 0. What E10 measures (three panels)

| Panel | Question | Instrument | Live or local |
|-------|----------|-----------|---------------|
| **10a** | Resolution **throughput** (download stripped out): accessions/sec vs `--meta-jobs`, adaptiSeq vs iSeq/pysradb/ffq/Kingfisher | real `batch.resolve_all()` sweep + competitor CLIs | **live** ENA/GSA |
| **10b** | **Overlap value**: resolution wall-time as a fraction of end-to-end, `--meta-jobs 1` vs `8` | real `resolve_all()` timing + a measured transfer time | **live** ENA |
| **10c** | **Etiquette / decoupling proof** (the key panel): req/s to each endpoint stays **flat at the cap** as `--meta-jobs` rises; a naive resolver blows past NCBI's 3 rps | real `ratelimits.RateLimiter` driven by a faithful per-accession request pattern | **local, deterministic** |

**Why 10c is local.** The behaviour that proves the design — a naive
thread-per-accession resolver **blowing past NCBI's 3 rps** — is exactly the
impolite, IP-ban-risking thing we must not do to live NCBI, and its magnitude is
non-reproducible (depends on live RTT). E7 solved the identical problem for the
download engine with a local origin server. E10c does the same for *resolution*:
it drives the **real** `adaptiseq.ratelimits.EndpointLimiters` /
`RateLimiter.acquire` (the production code, unmodified) with the real
per-accession endpoint-request pattern measured in §2, sweeping `--meta-jobs`,
`limiter` vs `naive`. Only the "network" is a fixed simulated latency, so the
result is byte-identical on Fabric and Expanse.

**Live measurement note (2026-07 recalibration).** The plan's original
"SRA-only → forces NCBI eutils" picks (PRJNA48479 runs, e.g. `SRR1031060`) are
now **mirrored by ENA** — a live probe (§2) shows they resolve in a single ENA
filereport request with no NCBI hop. So the live panels (10a/10b) exercise the
ENA (8 rps) and GSA (5 rps) endpoints; the **NCBI 3-rps cap** — the strictest and
the whole point of the etiquette story — is exercised deterministically in 10c,
where `ncbi_rps()` (a code constant: 3 without a key, 10 with `NCBI_API_KEY`) is
enforced by the real limiter. This split is the honest way to show the cap is
respected without hammering NCBI to prove it.

---

## 1. The mechanism under test (code path)

```
batch.resolve_all(accessions, options, workdir, meta_jobs=N)
  ├─ EndpointLimiters()  →  ratelimits.set_active(limiters)   # install for the batch
  ├─ ThreadPoolExecutor(max_workers=N)                        # <-- --meta-jobs
  │     └─ _resolve_one(acc)  →  metadata.get_sra/gsa_metadata → net.wget_*  
  │            └─ net._throttle(url) → ratelimits.throttle(url) → RateLimiter.acquire()
  │                                    (per-endpoint minimum-interval gate)
  └─ set_active(None)                                          # uninstall
```

Two facts this panel is built around, both **verified in code** (`ratelimits.py`,
`batch.py`, `net.py`):

1. **Concurrency ≠ request rate.** `meta_jobs` sizes the *thread pool*; the
   request rate is governed by a *separate* per-endpoint `RateLimiter`
   (`_min_interval = 1/rps`, a monotonic next-slot gate under a lock). Raising
   `meta_jobs` lets more accessions resolve *in flight* (hiding RTT) but cannot
   raise the per-endpoint issue rate above the cap.
2. **The public `resolve()` / CLI `-m` are serial.** The parallel path only runs
   inside the download batch phase, so E10a isolates resolution by calling
   `batch.resolve_all()` directly — this *is* the C3b mechanism, measured with no
   bytes transferred.

Documented caps (`ratelimits.py`): **ENA 8 rps, GSA 5 rps, NCBI 3 rps (10 with
`NCBI_API_KEY`)**.

---

## 2. Per-accession request pattern (measured live, 2026-07-21)

A one-off instrumented `resolve_all(meta_jobs=1)` with a spy on `net._run`:

| Accession class | Example | Requests issued | Endpoints hit |
|-----------------|---------|-----------------|---------------|
| ENA-mirrored run | `SRR22904259` | 1 | ENA×1 |
| "SRA-only" (now ENA-mirrored) | `SRR1031060` | 1 | ENA×1 |
| GSA run | `CRX917377` | 4 | GSA×4 |
| **True SRA-only (no ENA mirror)** | *model* | 3 | ENA×1 + NCBI×2 (esearch + sra-db-be) |

The last row is the pattern `metadata.get_sra_metadata` takes when the ENA
filereport is empty (esearch → WebEnv/QueryKey → sra-db-be runinfo). It is the
**NCBI-cap-stressing** pattern 10c models, because live ENA mirroring makes it
rare to trigger on demand.

---

## 3. Datasets

| Name | File | Composition | Used by |
|------|------|-------------|---------|
| **E10_ena** | `datasets/E10_ena_PRJNA916347.txt` | 150 ENA runs (from D1_full) — 1 ENA req each, clean scaling signal | 10a, 10b |
| **D4_mixed** | `datasets/D4_mixed.txt` | 12 ENA + 6 "SRA-only" + 2 GSA (`CRX*`) — multi-DB preference chain | 10a (mixed arm) |
| *synthetic* | built in `etiquette_probe.py` | 120 accessions, mix {ENA, true-SRA-only, GSA} with the §2 request patterns | 10c |

N for 10a is sub-sampled from E10_ena: `N ∈ {50, 150}` on Fabric (live, polite),
`N ∈ {100, 500, 2000}` on Expanse (spec target; more time budget). Competitors run
at a smaller `N_COMP` (serial CLIs, one process per accession) and are reported as
accessions/sec so N is comparable.

---

## 4. Metrics & TSV schemas

**10a/10b** (`e10_resolve.tsv`):
`panel, dataset, tool, meta_jobs, n_acc, rep, wall_s, acc_per_s, n_tasks,
n_unresolved, ena_reqs, gsa_reqs, ncbi_reqs, host, stamp`

**10c** (`e10_etiquette.tsv`):
`arm, ncbi_key, meta_jobs, endpoint, cap_rps, n_requests, wall_s, mean_rps,
peak_rps_1s, over_cap, host, stamp`

Headline numbers: accessions/sec vs `--meta-jobs` (10a), resolution-fraction-of-
total (10b), **peak req/s per endpoint vs cap** and the over-cap flag (10c).

---

## 5. Figures (aggregate_e10.py)

- **Fig 8a** — accessions/sec vs `--meta-jobs` (adaptiSeq line) with competitor
  serial rates as horizontal reference lines.
- **Fig 8b** — peak req/s to each endpoint vs `--meta-jobs`: adaptiSeq **flat at
  the cap** (dashed cap lines) vs the **naive** resolver rising linearly and
  crossing the NCBI 3-rps line (the failure mode the design prevents).
- **Fig 8c / Table 4** — resolution wall-time by tool at fixed N (dumbbell), plus
  the 10b resolution-fraction-of-total bars.

---

## 6. Execution

```bash
# Fabric (this box) — run directly, no Slurm:
bash bench/e10/run_fabric.sh              # smoke (N=20, mj∈{1,8}, 1 rep) then full
PANELS="10a 10b 10c" bash bench/e10/run_e10.sh all

# individual panels
bash bench/e10/run_e10.sh 10a             # resolution throughput sweep + competitors
bash bench/e10/run_e10.sh 10b             # overlap value
bash bench/e10/run_e10.sh 10c             # etiquette / decoupling proof (local)

# aggregate → figures + summary
python3 bench/e10/aggregate_e10.py --out e10_results_fabric

# Expanse:
sbatch bench/e10/e10_expanse.sbatch
```

**Time approximation (Fabric).**

| Panel | Work | ~wall |
|-------|------|-------|
| 10a adaptiSeq sweep | N∈{50,150} × mj∈{1,3,8,16} × 3 reps | ~9 min |
| 10a competitors | 4 tools × N_COMP=20 × 2 reps (serial) | ~4 min |
| 10b overlap | N=150, mj∈{1,8} × 3 reps + one small transfer | ~3 min |
| 10c etiquette | local, 2 arms × 2 key-modes × mj∈{1,3,8,16} | ~2 min |
| **Total** | | **~18 min** |

Expanse (N up to 2000, `--exclusive`): ~35–45 min; gated on compute-node egress
to ENA/GSA (§13 of the master plan). 10c needs no network and always runs.

---

## 7. Honesty / limitations (pre-empt reviewers)

- Resolution throughput saturates at the **endpoint rate cap**, not at
  `meta_jobs` — that is the *point* (etiquette), not a scaling failure. Fig 8a
  flattens past `meta_jobs≈8` for ENA (8 rps) by design.
- The NCBI blow-past-cap contrast (10c naive arm) is **simulated latency**, not a
  live NCBI flood — deliberately, so we neither misbehave nor report an
  unreproducible magnitude. The limiter code exercised is the production code.
- Competitor tools resolve **serially** (one CLI process per accession); their
  accessions/sec is inherently ~`1/RTT`. adaptiSeq's win is overlapping RTT up to
  the polite cap — we do **not** claim adaptiSeq resolves an individual accession
  faster.
- Live ENA mirroring means the "SRA-only→NCBI" branch rarely fires on demand;
  §2's true-SRA-only pattern is modelled from the code, not forced live.
