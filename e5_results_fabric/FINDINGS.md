# E5 — Adaptive Aspera, efficiency hysteresis (Fig 5): Fabric run findings

Machine: **Fabric** (`Node-FIU`, 8 cores), 2026-07-21, ~1.5 h wall. Reps: **2** (≤5
ceiling; the settle point is condition-dependent, so 2 reps sample the variance).
Transport: **real IBM `ascp` 4.4.4** (`bench/setup_real_ascp.sh`) over UDP 33001 to
`fasp.sra.ebi.ac.uk`, authenticated with the **ENA RSA** token key. Workload:
`E5_aspera_PRJNA916347` (8 single-file runs, 2.64 GB). Judged by md5 vs the ENA
manifest.

## Table (Fig 5) — median over 2 reps

| panel | arm | wall_s | MB/s | runs | settle_w |
|---|---|---|---|---|---|
| 5a | adaptive | 182 | 15.0 | **8/8** | 1 |
| 5b | fixed-j1 | 298 | 9.0 | 8/8 | — |
| 5b | fixed-j2 | 183 | 14.6 | 8/8 | — |
| 5b | fixed-j4 | 80 | **33.4** | 8/8 | — |
| 5b | fixed-j8 | 79 | **33.9** | 8/8 | — |
| 5b | adaptive | 211 | 13.8 | 8/8 | 1 |
| 5c | eff-0.5 | 191 | 18.3 | 8/8 | 2 |
| 5c | eff-0.7 | 168 | 18.2 | 8/8 | 1 |
| 5c | eff-0.9 | 225 | 12.2 | 8/8 | 1 |

**Every one of the 18 arm-runs completed 8/8 files with a valid md5.**

## Findings

**1. The adaptive Aspera path is fully reliable (C5 + integrity).** All 18 arm-runs
finished the whole workload byte-exact, using real `ascp` and the ENA **RSA** key.
This directly corroborates the plan's **DSA→RSA migration finding**: the RSA
token-auth key authenticates where the legacy DSA key (still shipped by Kingfisher
and old iSeq docs) is now rejected by `fasp.sra.ebi.ac.uk` — a concrete good-citizen
/ reliability point. adaptiSeq's key search prefers RSA, so it keeps working.

**2. The controller measures live per-worker efficiency and backs off (C1
mechanism).** The 5a trajectories show real additive-increase probing and the
hysteresis rule (keep a worker while `throughput/(w×baseline) ≥ 0.70`, else settle):

| rep | 1 worker | 2 workers | 3 workers | settle |
|---|---|---|---|---|
| 5a-rep1 | 135.5 Mbps (eff 1.00) | **41.5 (eff 0.15)** | — | **1** (collapse at 2) |
| 5a-rep2 | 65.9 (eff 1.00) | 257.3 (eff 1.95) | 69.7 (eff 0.35) | **2** (scales to 2, collapses at 3) |

Rep 1 **reproduces the Part 6 throttle-collapse** (a 2nd session *lowers* aggregate
throughput → efficiency 0.15 → back to 1 worker). Rep 2 shows the opposite in the
same run.

**3. The headline empirical result — EBI's Aspera session policy is strongly
time-variable.** Within one ~1.5 h run we observed **both** regimes:
- **Throttle-collapse** (5a-rep1: 2 sessions → efficiency 0.15), the Part 6 finding.
- **Scaling** (5b: fixed-j4/j8 were *fastest* at ~34 MB/s vs j1's 9 MB/s; 5a-rep2:
  2 sessions → efficiency 1.95).

EBI's per-IP Aspera throttle is **intermittent, not constant** — a materially
different picture than a single-shot benchmark would suggest, and exactly the
`DirGrowthMeter`/policy variance the plan §15 pre-registered.

**4. Honest consequence — adaptive is *safe*, not always *fastest*, on a variable
link.** Because the regime shifts:
- the controller's **settle point is non-deterministic** (settled at 1, 2, or 3
  across reps), tracking whatever its short probe window happened to measure;
- in the **scaling window that dominated 5b**, the fixed high-session arms
  (j4/j8 ≈ 34 MB/s) **beat adaptive** (≈ 14 MB/s) — adaptive under-shot by catching
  a transient throttle in its probe and settling low.

So on this link adaptive **never gets catastrophically throttled and always
completes**, but pays a probing cost and can under-shoot when sessions happen to
scale. This is the **same "no single fixed choice wins everywhere; adaptivity trades
peak for safety"** story as E8's HTTP controller — and the plan pre-registered it
("if 2 workers scale, we report that"). It does **not** claim adaptive > fixed here.

**5. The efficiency threshold behaves as designed (5c).** A lower threshold accepts
more workers (`eff-0.5` → settle 2, 18.3 MB/s), a higher one is conservative
(`eff-0.9` → settle 1, 12.2 MB/s) — monotonic in the expected direction, justifying
the 0.70 default as a middle ground. Magnitudes are noisy (see caveats).

## Bugs found and fixed during bring-up

- **Aspera arms need `-a -g` together.** With `-a` alone, `resolve()` returns the SRA
  **S3** path (not an Aspera host) → `ascp: no remote host specified` and nothing
  transfers. `-g` targets the ENA fastq Aspera mirror. Fixed in `run_e5.sh`.
- **Default probe window (5 s) < `ascp` per-session startup (~5–10 s).** The controller
  measured **throughput = 0** at every probe and settled at 1 by the zero-baseline
  fallback (not by measuring efficiency). Raised to **`--probe-window 15`**, after
  which probes read real throughput. *This is a genuine tuning finding for the Aspera
  controller: unlike HTTP, `ascp` has a multi-second handshake, so the probe window
  must exceed it or the meter sees only startup.* Worth surfacing in the docs.

## Caveats (as pre-registered, plan §7)

- **`DirGrowthMeter` magnitudes are noisy** — a few probes read exactly 0 (e.g.
  `eff-0.9` rep2 at 2 workers, `eff-0.5` rep2 at 1 worker), an `ascp`-startup
  sampling artifact. The **qualitative** back-off (efficiency drops → stop adding
  workers) is robust; exact MB/s per probe is not.
- **Single ENA endpoint, one node, one ~1.5 h window** — Aspera throughput and EBI's
  session policy are time-of-day sensitive (the whole point of finding #3).
- **GSA Aspera** (Huawei-wins, sequential by design) is **out of scope** (plan §7).
- **reps = 2** — enough to *expose* the regime variance, not to average it out.

## Figures & files

- `fig5a_trajectory.png` — efficiency & throughput vs worker count per probe (shows
  both collapse and scaling reps, with the 0.70 keep/stop line).
- `fig5b_fixed_vs_adaptive.png` — aggregate MB/s across fixed `-j` and adaptive
  (this run: sessions scaled, so fixed-j4/j8 lead).
- `fig5c_sensitivity.png` — MB/s + settle point vs `--aspera-efficiency`.
- `e5_results.tsv`, `logs/trajectories.tsv`, per-arm logs under `logs/`.

## Bottom line

E5 runs end-to-end on Fabric with real Aspera: **the adaptive controller reliably
completes every workload (18/18 arms, 8/8 files, md5-verified) and demonstrably
measures per-worker efficiency and backs off.** Its *purpose* — never oversubscribe a
host that punishes concurrency — is validated (5a-rep1 reproduces the Part 6
collapse). But the honest, dominant finding this run is that **EBI's Aspera throttle
is intermittent**: sometimes sessions scale, sometimes they collapse, and no single
worker count (fixed or adaptively chosen) is optimal across the variance. Adaptive
buys **safety and completeness**, not guaranteed peak throughput — the same trade-off
E8 found for the HTTP controller.
