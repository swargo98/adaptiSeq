# adaptiSeq — Benchmark & Experiment Plan (paper, iSeq-style)

Target venue: *Bioinformatics* Applications Note (like iSeq, btae641) or a slightly
longer methods paper. iSeq's evidence is one figure (1A–G) + one supplementary
table. We will **marginally follow** that structure and **expand** it where our
contributions differ from iSeq's.

All experiments run on **SDSC Expanse**. See §9 for Expanse-specific setup and the
network-shaping caveat (important — read before designing the throttled runs).

---

## 0. What we are claiming (contributions → experiments map)

The user named three headline contributions. After reading the code I recommend
promoting **two more** to first-class status, because they are real, defensible,
and reviewers of a "yet another downloader" paper will ask for them:

| # | Contribution | Why it's defensible | Primary experiment |
|---|--------------|---------------------|--------------------|
| C1 | **Adaptive download engine** (gradient worker-count controller for HTTP; additive-increase + efficiency-hysteresis controller for Aspera) | `engine/optimize.py`, `batch.py:AdaptiveController`, `aspera.py:HysteresisController` — closed-loop control tuned to live throughput; backs off under server throttling | E4, E5 |
| C2 | **Python interface** (importable `fetch`/`resolve`/`get_metadata`, typed exceptions, no `sys.exit`/colour) | `__init__.py`, `core.py` — iSeq is a Bash script with **no** library API | E6 |
| C3 | **Batch download** (parallel multi-accession resolution + adaptive worker pool, overlapping resolve & transfer) | `batch.py:resolve_all` + `BatchDownloader`; iSeq/Kingfisher resolve & download **one run at a time** | E3 (headline), E10 |
| C3b ⟵ *sub of C3* | **Parallel, rate-limited metadata resolution** — `--meta-jobs` concurrent multi-DB resolution whose request rate is **decoupled from pool size** by per-endpoint limiters (ENA/GSA/NCBI; NCBI 3 rps, 10 with key) | `batch.py:resolve_all`, `ratelimits.py:EndpointLimiters`/`set_active`, consulted in `net.py` | E10 |
| **C4** ⟵ *add* | **Segmented, resumable, multi-connection engine** (HTTPS-first range GETs, atomic `.part`/`.part.meta` resume, native segmented FTP, never-truncate single-stream fallback) | `engine/segmented.py` — iSeq shells out to `wget`/`axel`, no in-process resume map | E2, E7 |
| **C5** ⟵ *add* | **Reliability / good-citizen robustness** (per-host circuit breaker on 429/503, ENA RSA-key path, completes 3-file runs iSeq drops, differential-tested byte-parity with iSeq) | `engine/ratelimit.py:HostGuard`, `ratelimits.py`, BENCHMARK.md robustness findings | E7 |

> **Framing advice.** Lead the abstract with C3 (batch) + C1 (adaptive) as the
> novelty, C4 as the mechanism that makes them safe (resumable, never-corrupt),
> C2 as the reusability story (the thing that lets adaptiSeq be a *library* inside
> pipelines, not just a CLI), and C5 as the reliability evidence. Present **C3b
> (parallel rate-limited resolution)** as a named *mechanism inside* C3, not a
> standalone headline — it has no meaning for a single accession; its novelty is
> being *concurrent yet etiquette-compliant* (won't get the user's IP throttled),
> which is what iSeq's serial resolver can't offer at batch scale. Do **not** claim
> raw single-file throughput supremacy — aria2c beats us there and BENCHMARK.md is
> honest about it. Our claim is *end-to-end* (resolve→download→verify→merge) over
> *many* accessions, *safely*, *as a library*.

---

## 1. Experiment catalogue (overview)

| ID | Name | Mirrors iSeq | Headline metric | Figure/Table |
|----|------|--------------|-----------------|--------------|
| E1 | Feature/capability matrix | Fig 1C | qualitative ✓/✗ | Table 1 |
| E2 | Single-file engine micro-benchmark | Fig 1E | MB/s vs file size, vs protocol | Fig 2 |
| E3 | **Batch download (headline)** | new | wall time, MB/s, speedup, success% | Fig 3 |
| E4 | Adaptive vs fixed concurrency | new (extends Fig 1G) | throughput, trajectory, robustness | Fig 4 |
| E5 | Adaptive Aspera (efficiency hysteresis) | Fig 1E (aspera) | settle-point, back-off behaviour | Fig 5 |
| E6 | Python interface (programmatic case study) | new | LOC/overhead/composability | Table 2 + listing |
| E7 | Reliability & resumability | Fig 1 + Suppl. S1 | success% over N runs, resume correctness | Table 3 |
| E8 | Resource profile (time/mem/CPU/IO) | Fig 1D | peak RSS, %CPU, avg I/O | Fig 6 |
| E9 | Scalability / strong-scaling on HPC | new | throughput vs `-j`, `--meta-jobs`, N | Fig 7 |
| E10 | Parallel metadata resolution & rate-limit etiquette | extends Fig 1D "fetch metadata" | accessions/s, req/s per endpoint | Fig 8 + Table 4 |

Minimum for a credible Applications Note: **E1, E3, E4, E8, E7**. The rest
strengthen specific contributions and are worth doing given "do not underdo."

---

## 2. Datasets (real accessions, tiered — **verified against the ENA portal API, 2026-06**)

The small lists in `bench/inputs/` are fine for a CI smoke test but **too small to
headline a paper** — iSeq benchmarked at the terabase scale (3000 GSA + 3000 SRA
files, ~7 Tbp + ~5 Tbp). The tiers below scale to match, are **real and size-
verified**, and deliberately **retain the three BioProjects from the FastBioDL/
arXiv:2508.05511 study** (PRJNA762469, PRJNA540705, PRJNA400087) so adaptiSeq can be
compared against your own prior tool for continuity. Commit the exact lists to a
`datasets/` dir (iSeq publishes its accessions in Data Availability — do the same).

> Run counts/sizes below were pulled live from
> `https://www.ebi.ac.uk/ena/portal/api/filereport?accession=<P>&result=read_run&fields=run_accession,fastq_bytes`.
> Re-pull on Expanse before the runs (public DBs grow); the script is one line.

| Tier | BioProject | Verified scale (ENA) | Profile | Used by |
|------|-----------|----------------------|---------|---------|
| **D0 single-file** | pick 1 run each from D1/D2/D3 | ~24 MB / ~1.7 GB / ~11 GB | controls file size | E2 |
| **D1 small / overhead-dominated** | **PRJNA916347** | 243 runs, **321 files, 7.6 GB, avg 24 MB/file** | many tiny files — batching's home turf; ~40 runs ship 3 fastq (iSeq drops these) | E3a, E7e |
| **D2 medium / byte-balanced** | **PRJNA762469** (Breast RNA-seq, *FastBioDL*) | 60 runs, **120 files, 206 GB, avg 1.7 GB/file** | balanced; head-to-head vs your prior tool | E3b, E4, E8 |
| **D3 large per-file** | **PRJNA540705** (HiFi-WGS, *FastBioDL*) | 6 runs, **69 GB, avg 11.6 GB/file** | huge single files → many adaptive probe windows | **E4 (long-run)**, E2-large |
| **D3b large / TB-scale** | **PRJEB1787** (Tara Oceans metagenomes) | 249 runs, **495 files, 4.3 TB, avg 8.7 GB/file** | TB-scale byte-bound; matches iSeq's terabase scale | **E9 scaling**, E7a |
| **D3c large (alt)** | PRJNA251383 | 168 runs, **1.08 TB, avg 3.2 GB/file** | already in `bench/inputs/`; mid-large | E9, E4 |
| **D4 cross-database** | ENA-mirrored + **SRA-only** + **GSA** + **GEO** | see below | exercises every resolver branch | E1, E7, E10 |
| **D5 reliability corpus** | **PRJEB6403** (~iSeq scale) or subset **PRJEB31736** | **3,307 runs** / 1000G high-cov **37,090 runs** (subset to 3k) | success%/integrity at iSeq scale | **E7a** |

**Amplicon micro-tier (FastBioDL continuity / cheap CI):** PRJNA400087 (43 libraries,
1.9 GB, 13–66 MB/file) — useful as a fast overhead-dominated check alongside D1.

**D4 cross-database picks (exercise each resolver branch — verify before use):**
- **ENA HTTPS + segmented FTP:** any D1–D3 run (all have `fastq_ftp`).
- **SRA-only (no ENA mirror → forces `.sra` + fasterq-dump):** choose a project where
  the ENA `filereport` returns **empty `fastq_ftp`** (older NCBI submissions, e.g.
  many runs under **PRJNA48479**, 11,245 runs). Confirm per-run with `resolve()`.
- **GSA (CRA/CRR, Huawei-Cloud path):** reuse iSeq's own **CRX917377 / CRX095512**
  for a direct head-to-head, and add one **large CRA project** (query the GSA API
  `getRunInfo`/`getRunInfoByCra` for size — not on the ENA portal). Flag: GSA sizes
  must be verified via NGDC, not ENA.
- **GEO (GSE → SRX):** one **GSE** that maps to SRA (e.g. iSeq used SRX-level
  accessions) to exercise the GEO→SRA resolution branch.
- **iSeq's own runs for a turf comparison:** SRX3662754 (SE), SRX1663467 (PE),
  SRX917377, CRX095512 — run adaptiSeq vs iSeq on the exact accessions iSeq reported.

**Coverage rule:** ensure the chosen set forces every download path at least once —
ENA HTTPS mirror, segmented FTP, SRA `.sra`→fasterq-dump, GSA/Huawei-Cloud, Aspera.
Log `adaptiseq resolve <acc>` (library `resolve()`, no download) for each so the
paper can state which channel every tool actually used (fairness, §8).

**Storage budget (plan Lustre scratch accordingly):** a single full pass of
D1+D2+D3+D3b is ~4.6 TB; the D5 reliability corpus at 3k runs is multi-TB. Stage per
tier, md5-verify, then purge before the next tier — don't try to hold all tiers at
once. For E9 on D3b (4.3 TB) reserve scratch quota in advance.

---

## 3. E1 — Feature / capability matrix (Table 1, mirrors iSeq Fig 1C)

Reproduce iSeq's comparison table with adaptiSeq added and **new columns** for our
contributions. Tools: **adaptiSeq, iSeq, Kingfisher, fastq-dl, fetchngs, pysradb,
ffq, enaBrowserTools, SRA-Toolkit (prefetch)**.

Columns (extend iSeq's): databases · accession formats · output formats · methods ·
fetch metadata · MD5/`vdb-validate` check · **resumable (in-process)** · parallel
download · **adaptive concurrency** · **batch many accessions in one pool** ·
merge FASTQ · skip-downloaded · conda/pip · **importable Python API (returns
values, typed exceptions)** · **never-truncate guarantee**.

Verify each ✓/✗ **empirically** (run a one-liner per cell), don't copy iSeq's
table — versions have changed. Footnote the adaptiSeq-only columns; those four new
columns are the visual statement of novelty.

---

## 4. E2 — Single-file engine micro-benchmark (Fig 2, mirrors iSeq Fig 1E)

**Goal:** characterise the segmented engine per file; show it is competitive and
*never corrupts*, while being honest that aria2c wins raw single-file throughput.

**Factors**
- File size: ~50 MB, ~2 GB, ~20 GB (D0).
- Transport: `segmented-https`, `segmented-ftp` (`-r ftp`), `single-stream`
  (range-incapable host), `classic wget` (`--engine classic`), `classic axel -p 8`.
- External baselines: `aria2c -x8 -s8`, `iseq`, `prefetch`.
- Engine knobs (ablation): `--max-segments ∈ {1,2,4,8,16}`,
  `--segment-size ∈ {64,256,512,1024} MB`, `--max-conns-per-host ∈ {2,4,8,16}`.

**Metrics:** effective MB/s (bytes/wall), time-to-first-byte, # segments used,
peak RSS. **Always record bytes + md5 pass** so size differences can't flatter a
tool (§8).

**Output:** box plots of MB/s per (size × transport), ≥15 reps, files deleted
between reps, randomized order. One small ablation panel for `--max-segments`
(diminishing returns curve → justify default 8).

---

## 5. E3 — Batch download — **HEADLINE** (Fig 3)

This is the C3 + C1 money figure. Extend the honest `BENCHMARK.md` protocol to
HPC scale and multiple regimes.

**Competitors (the *dedicated* tools, per BENCHMARK.md rationale):** `iseq`,
`iseq -p 8`, `Kingfisher`, `fastq-dl`, `fetchngs`. (Skip raw aria2c — it can't
resolve accessions; mention once in text.)

**adaptiSeq arms:** `--no-adaptive -j {8,20,40}`, `--adaptive -j {20,40}`, and
`--meta-jobs ∈ {1,3,8,16}` to isolate the parallel-resolution contribution.

**Workloads (3 panels):**
- **3a Overhead-dominated** (D1, many small runs): the regime batching is *built*
  for. Expect the BENCHMARK.md result (≈2.8× iSeq MB/s) to hold/strengthen.
- **3b Byte-dominated** (D2/D3, fewer large runs): honesty panel — per-run overhead
  shrinks; show segmentation still helps per file and batching ≥ parity.
- **3c Mixed / cross-database** (D4): real-world list spanning ENA+SRA+GSA.

**Metrics:** wall time, **bytes downloaded**, **MB/s (fair metric)**, files,
format, **success rate** (completed runs / total), and **wall-time speedup vs
iSeq**. Dumbbell or grouped-box plots, ≥10 reps, files deleted between every
method, order randomized, cold-vs-warm cache control run (BENCHMARK.md already
shows the ranking survives reversed order — reproduce on Expanse).

**Scaling sub-experiment (→ feeds E9):** fix workload D2, sweep `-j` and
`--meta-jobs`, plot throughput vs concurrency to show where batching saturates the
link and where per-host etiquette caps it.

**Robustness call-out (from BENCHMARK.md, reproduce + quantify):** on the *full*
D1 list, ~40/241 runs ship 3 fastq files (orphan/`_1`/`_2`) that **stock iseq
drops** (`wget` multiline-URL bug, e.g. `SRR22904269`). Report **runs completed**
per tool — adaptiSeq completes a strict superset. This is a correctness win inside
the speed figure.

---

## 6. E4 — Adaptive vs fixed concurrency (Fig 4) — core of C1

BENCHMARK.md is admirably honest that on a ~17 s run adaptive vs fixed is **within
noise** (only ~3 probe windows). The fix is to test in the regime the controller
was *designed* for and to measure *robustness*, not just peak speed.

**E4a — Long-run convergence (the controller's home turf).** Use D3 (tens of GB,
multi-minute). Plot the **worker trajectory** (`AdaptiveController.trajectory`:
workers vs Mbps over time) overlaid on instantaneous throughput. Compare
`--adaptive` vs the best fixed `-j` found by sweep, and vs a deliberately-too-high
fixed `-j`. Claim: adaptive matches the *oracle* fixed setting **without tuning**.

**E4b — Robustness under throttling/contention (the real win).** Adaptive's value
is backing off when more workers *don't* help. Create that regime:
- **Server-side throttling:** a host that 429/503s under parallelism (ENA FTP
  under `iseq -p 8` already does this — BENCHMARK.md shows axel stalling). Show
  fixed-high `-j` collapses/errors while adaptive converges down (HostGuard circuit
  breaker + controller).
- **Shared-link contention:** run 2–4 adaptiSeq instances on one Expanse node
  sharing the NIC; show adaptive de-escalates to a fair operating point while
  fixed oversubscribes.

**E4c — Controller sensitivity / ablation.** Sweep `--probe-window ∈ {3,5,10}`
and `--cc-penalty ∈ {1.0,1.01,1.05}`; show stability and justify defaults. Include
the **honest negative result** from BENCHMARK.md (small batches: adaptive ≈ fixed)
as a labelled panel — reviewers trust papers that show where the method *doesn't*
help.

**Metrics:** sustained MB/s, time-to-converge (windows), final worker count vs
oracle, error/retry count under throttling, fairness (Jain's index) in the
contention test.

---

## 7. E5 — Adaptive Aspera, efficiency hysteresis (Fig 5)

Separate controller (`aspera.py`), separate figure. Reuse the validated Part 6
result and scale it.

- Real IBM `ascp` 4.4.4 against ENA `fasp.sra.ebi.ac.uk:33001` (RSA token key —
  note the DSA→RSA migration finding; tools hardcoding the DSA key now fail ENA,
  a C5 reliability point worth a sentence).
- Workload: D2/D3 over Aspera. Plot the additive-increase trajectory and the
  **efficiency collapse → back-off** (Part 6: `1w@206MB/s eff1.00, 2w@21MB/s
  eff0.05 → settle at 1 worker`). Compare against a naive fixed `-j 8` (8 sessions
  EBI penalises).
- Sweep `--aspera-efficiency ∈ {0.5,0.7,0.9}`.
- **Caveat to state:** `DirGrowthMeter` sampling noise affects the *magnitudes*;
  the *qualitative* back-off is robust. Keep BENCHMARK.md's honesty.
- GSA Aspera (Huawei-wins rule) — note it is best-effort/sequential by design;
  don't over-test.

---

## 8. E6 — Python interface (Table 2 + code listing) — C2

iSeq has *no* importable API; this is a clean, uncontested contribution. Make it a
**programmatic case study**, not a microbenchmark.

- **Listing:** 5–8 line snippet doing `get_metadata` → filter rows in pandas →
  `resolve` → `fetch(..., outdir=)` → assert `FetchResult.failed is False`. Show
  typed-exception handling (`except IntegrityError`). Contrast with the
  shell-out + parse-stdout you'd need to script iSeq.
- **Table 2:** for 3 realistic tasks (filter runs by library strategy then fetch;
  fetch + verify in a loop with retry; embed in a Snakemake/Nextflow step), report
  **LOC**, whether it needs subprocess/stdout-scraping, and whether errors are
  catchable (typed) vs exit-code-only.
- **Overhead micro-measurement:** API `fetch()` vs CLI for the same accession —
  show the library path adds negligible wall time (it's the same `core.run`), i.e.
  the API is free.
- Optional: a one-paragraph **real pipeline integration** (e.g., a Snakemake rule
  importing `adaptiseq.fetch`) as a qualitative case study.

---

## 9. E7 — Reliability & resumability (Table 3) — C5 + integrity

Mirror iSeq's Supplementary S1 (3000+3000 success/integrity) and **add what iSeq
didn't test: in-process resume correctness.**

- **E7a Large-corpus success/integrity (like S1):** D5 (1–3k runs). Report success
  rate, md5/`vdb-validate` pass rate, # retried (≤3 rounds), # in `fail.log`. Run
  for iSeq and adaptiSeq side by side on the same list.
- **E7b Resume correctness (new, C4):** kill `adaptiseq` mid-download (`SIGKILL` at
  ~50%), restart, assert (i) it resumes from `.part`/`.part.meta` offsets, not from
  zero, (ii) final md5 matches, (iii) bytes re-downloaded ≪ file size. Repeat with
  3 kill points. iSeq's `wget -c` only partially covers this and axel/aspera differ
  — tabulate who actually resumes correctly. This is the strongest C4 evidence.
- **E7c Never-truncate / corruption:** point the engine at a range-incapable host;
  assert single-stream path produces a complete, md5-valid file (no silent
  truncation). Inject a corrupt byte (simulate) → assert md5 retry fires.
- **E7d Circuit breaker:** drive 429/503 (or the ENA-FTP-throttling regime from
  E4b); show HostGuard backs off and recovers rather than hammering — log the
  cap/backoff trace.
- **E7e 3-file-run completion (from BENCHMARK.md):** `SRR22904269` etc. — adaptiSeq
  completes, iSeq exits 1. Already verified; reproduce on Expanse for the record.

---

## 10. E8 — Resource profile (Fig 6, mirrors iSeq Fig 1D)

iSeq's Fig 1D (time/mem/CPU/avg-I/O traces + task-breakdown bar) is the single most
"applications-note" figure. Reproduce it.

- For one representative SRA fetch and one ENA fetch, trace **peak RSS, %CPU,
  average I/O (MB/s), and a stacked time bar** (send-request / fetch-metadata /
  fetch-data / md5-check) for adaptiSeq vs iSeq vs Kingfisher vs prefetch.
- Tooling: `psutil` (already a test dep — see commit `1ea1f10`) sampling the
  process tree at ~2 Hz; or `/usr/bin/time -v` for peak RSS + a `psutil` sampler
  thread for the curves. `bench/_run_one.py` is a starting point.
- **Important nuance vs iSeq:** adaptiSeq is single-process asyncio with up to `-j`
  workers; its memory/CPU envelope differs from iSeq's subprocess-per-run model.
  Report this honestly — adaptive concurrency may use more CPU during probing but
  finishes sooner (area-under-curve / energy proxy is the fair summary).

---

## 11. E9 — Scalability / strong-scaling on HPC (Fig 7) — new, plays to Expanse

This is where Expanse's fat network + 128 cores let us show something iSeq (tested
on a 48-core node) didn't.

- **Strong scaling:** fix D3 workload, sweep `-j ∈ {1,2,4,8,16,32,64}` and
  `--meta-jobs ∈ {1,3,8,16}`; plot aggregate throughput and parallel efficiency.
  Identify the knee where the **server-side per-host cap / circuit breaker**, not
  the client, becomes the limit (an honest, interesting systems result).
- **Link saturation:** how close to the node's available external bandwidth can the
  batch pool drive ENA HTTPS? Report % of measured ceiling (use `iperf3` to a
  reachable host or a known fat mirror to estimate the ceiling).
- **Throughput vs file-size distribution:** overhead-dominated vs byte-dominated
  curves on the same hardware → explains *when* batching/adaptivity pays.

---

## 11b. E10 — Parallel metadata resolution & rate-limit etiquette (Fig 8 + Table 4) — C3b

Isolates the resolution half of batch download from byte transfer, and proves the
"concurrent **but** well-behaved" design. This is also the experiment where the
*metadata* tools (**pysradb, ffq**) are legitimate head-to-head rivals (comparing
them on byte transfer would be apples-to-oranges).

**E10a — Resolution throughput (download stripped out).** Resolve N ∈ {100, 500,
2000} accessions with *no* download (`-m` / library `resolve()`), measure
accessions/sec and total resolution wall time. Sweep `--meta-jobs ∈ {1,3,8,16}`.
Competitors: iSeq (serial), pysradb, ffq, Kingfisher. Use a mixed ENA/SRA/GSA list
(D4-style) so the multi-DB preference chain (ENA→SRA fallback→GSA→GEO) is exercised.

**E10b — Overlap value.** For a real batch (D2), report resolution-phase wall time
as a **fraction of total** with `--meta-jobs 1` vs `8`, and end-to-end time with
resolution overlapping transfer vs forced-serial. Quantifies exactly what batching
hides — the per-run RTT iSeq pays serially.

**E10c — Etiquette / decoupling proof (the key panel).** Instrument
`ratelimits.RateLimiter.acquire` (or count requests in `net.py`) to record
**requests/sec to each endpoint** (ENA/GSA/NCBI) while sweeping `--meta-jobs`.
Show the rate stays **flat at the per-endpoint cap** (NCBI ≤ 3 rps without key,
≤ 10 with `NCBI_API_KEY`) even as `--meta-jobs` rises — i.e. concurrency is
decoupled from request rate, so adaptiSeq won't trip server throttles or get the
user's IP blocked. Contrast: a naive thread-per-accession resolver (or
`--meta-jobs` with the limiter disabled) blows past 3 rps → the failure mode this
design prevents. Run both the NCBI-key and no-key cases.

**Metrics:** accessions/sec, resolution wall time, resolution-fraction-of-total,
peak req/s per endpoint vs the documented cap, # throttle/429 responses received.

**Plots:** Fig 8a accessions/sec vs `--meta-jobs` (lines per tool); Fig 8b
req/s-to-NCBI vs `--meta-jobs` (adaptiSeq flat at cap vs naive linear); Table 4
resolution wall time for N=2000 across tools.

---

## 12. Methodology & fairness (write this as a Methods subsection)

Borrow iSeq's controlled-conditions discipline and the existing BENCHMARK.md rigor:

1. **Same node, same time window, same filesystem.** One Expanse compute node per
   comparison set; interleave tools within a window so transient network state is
   shared. Write to **Lustre scratch** (`/expanse/lustre/scratch/$USER/...`), never
   `$HOME` (NFS) — filesystem I/O otherwise confounds the data-fetch traces.
2. **Bytes + format + md5, not just wall time.** Every run logs bytes downloaded,
   MB/s, file format, and md5/validate pass (BENCHMARK.md §"Fairness check"). A
   tool that fetched `.sra` lite vs `.fastq.gz` is not comparable on wall time —
   record and segregate.
3. **Delete files between every method; randomize method order; ≥10–15 reps;**
   report **median + IQR** (box/dumbbell plots like iSeq). Do an explicit
   **cold-vs-warm** control (reverse order) per BENCHMARK.md to rule out CDN-cache
   ordering artifacts.
4. **Pin versions** (conda env export) and the exact accession lists in the repo
   (`docs/benchmark/` like iSeq).
5. **Stub vs real Aspera:** be explicit which runs used the real IBM `ascp` vs a
   stub. The headline figures must use real `ascp` (Part 6 method).
6. **Report negatives** (small-batch adaptive ≈ fixed; aria2c wins single-file).
   This is a credibility multiplier for an Applications Note.

---

## 13. SDSC Expanse specifics (set up before any run)

- **Never benchmark on login nodes.** Use `compute` or `shared` partition via
  Slurm (`salloc`/`sbatch`); request whole-node for E8/E9 to avoid noisy
  neighbours (`#SBATCH --partition=compute -N1 --exclusive`). For cheaper batch
  runs the `shared` partition is fine but note CPU contention in the writeup.
- **Verify outbound internet from compute nodes first.** Some HPC compute nodes
  restrict egress / require a proxy. Test `curl -sI https://ftp.sra.ebi.ac.uk` and
  an `ascp` handshake from inside a job **before** designing runs. If egress is
  proxied, set `https_proxy`/`ftp_proxy` consistently for *all* tools (fairness)
  and document it. If Aspera UDP (port 33001) is blocked outbound, E5 must move to
  a node/DTN that allows it (Expanse has data-transfer nodes — check) or be run on
  a cloud VM and reported separately.
- **Filesystem:** stage to `/expanse/lustre/scratch`; it has the IOPS/bandwidth for
  multi-GB parallel writes. Purge between reps. Don't fill `$HOME` quota.
- **Software install:** a conda/mamba env on Expanse with `iseq`, `kingfisher`,
  `fastq-dl`, `sra-tools` (`prefetch`/`fasterq-dump`), `pysradb`, `ffq`,
  `enaBrowserTools`, `aria2`, `pigz`; `nf-core/fetchngs` via Nextflow+Singularity
  (Expanse provides Singularity). Install IBM Aspera SDK for `ascp`
  (`bench/setup_real_ascp.sh`). adaptiSeq itself: `pip install -e .` (Py ≥3.10).
- **Network shaping caveat (critical).** iSeq emulated 540 Mbps / 2 Gbps caps. That
  needs `tc netem`/`HTB` = **root**, which you won't have on Expanse compute nodes.
  Three options, in order of preference:
  1. **Use each tool's own rate cap** where comparable (adaptiSeq `-s/--speed`,
     aria2c `--max-overall-download-limit`, wget `--limit-rate`). Cleanest, but
     not all competitors honor an identical cap — document per tool.
  2. **`trickle`** (userspace `LD_PRELOAD` shaping, no root) for dynamically-linked
     tools; **won't** wrap static Go/Rust binaries (Kingfisher is Python→ok; check
     each) — document where it fails.
  3. **Run the throttled-network panels on a cloud VM you control** (root → real
     `tc netem` at 540 Mbps/2 Gbps, exactly reproducing iSeq's setup) and run the
     **high-bandwidth scaling** panels (E9) on Expanse. State both environments.
  Recommended: native-bandwidth + contention experiments (E4b shared-link) on
  Expanse; the explicit-rate-cap sweeps on Expanse via `--speed`; the
  apples-to-apples netem comparison vs iSeq on a root VM. This split is honest and
  covers both "matches iSeq's protocol" and "scales beyond iSeq's hardware."
- **Slurm harness:** wrap `bench/_run_all.sh` so each (tool × dataset × rep) is a
  job array task writing a TSV row (`tool, dataset, rep, wall_s, bytes, MBps,
  format, success, peak_rss, cpu_pct`); aggregate with pandas → all plots from one
  tidy table.

---

## 14. Figures/tables checklist (paper-ready)

- **Table 1** — feature matrix (E1).
- **Fig 2** — single-file MB/s by size×transport + `--max-segments` ablation (E2).
- **Fig 3** — batch: 3 panels (overhead/byte/mixed) MB/s + speedup + runs-completed
  (E3). **← main figure.**
- **Fig 4** — adaptive: convergence trajectory, throttling back-off, contention
  fairness, sensitivity (E4).
- **Fig 5** — Aspera hysteresis trajectory & back-off (E5).
- **Fig 6** — resource profile traces + task-time bar (E8, the iSeq-1D analogue).
- **Fig 7** — strong-scaling vs `-j`/`--meta-jobs`, link saturation (E9).
- **Fig 8 + Table 4** — resolution accessions/s vs `--meta-jobs`; req/s-per-endpoint
  etiquette (flat at cap vs naive); N=2000 resolution time across tools (E10).
- **Table 2** — Python API LOC/composability vs scripting iSeq (E6).
- **Table 3** — reliability: large-corpus success/integrity + resume correctness
  (E7).
- **Suppl.** — full accession lists, conda env export, per-rep raw TSV, controller
  sensitivity grids, negative results.

---

## 15. Honest limitations to pre-empt (keep BENCHMARK.md's tone)

- Single-file raw throughput < aria2c (by design; we resolve+verify+batch).
- Adaptive ≈ fixed on short/small batches (few probe windows) — only wins on long
  multi-minute runs and under throttling/contention.
- `DirGrowthMeter` magnitudes carry sampling noise (Aspera); qualitative back-off
  is robust.
- Throttled-network parity vs iSeq requires a root environment (not Expanse
  compute); reported on a separate VM.
- Results depend on live public-DB throughput and time of day — hence interleaving
  + reps + median reporting.

---

## 16. Suggested execution order (lowest-risk → highest-payoff)

1. **Set up Expanse** (§13): env, egress check, scratch, Slurm harness. *Gate
   everything on the egress/Aspera-port check.*
2. **E1** (cheap, sets the narrative).
3. **E3 headline** on D1 (reproduce BENCHMARK.md at HPC scale) → confirms the
   thesis early.
4. **E2 + E8** (engine + resource profile; short runs).
5. **E7** reliability corpus (long but unattended — launch as job array, collect
   later).
6. **E4** adaptive long-run + throttling/contention (needs D3; the scientific core
   of C1).
7. **E9** scaling (Expanse's differentiator).
8. **E5** Aspera (gated on UDP egress).
9. **E6** Python case study + **netem VM** parity panels.
10. Aggregate TSVs → figures → writeup.
</content>
</invoke>
