# E3 — Batch download (HEADLINE, Fig 3) — execution plan

Refines §5 of [`EXPERIMENT_PLAN.md`](EXPERIMENT_PLAN.md) into something runnable.
E3 is the C3 (batch) + C1 (adaptive) money figure: the claim is **end-to-end
(resolve → download → verify) over many accessions, safely** — *not* raw
single-file throughput (aria2c wins that; §15 of the parent plan stays honest
about it).

Target: **Fig 3** (3–4 panels) + the runs-completed correctness call-out.
Competitor of record: **iSeq** (Chao *et al.*, *Bioinformatics* 2024, btae641).

---

## 1. What iSeq did, and where E3 must meet or beat it

Read off btae641 directly, because the fairness bar is theirs:

| iSeq's protocol (btae641) | What E3 does |
|---|---|
| "Same computing cluster (48 cores, 128 GB RAM), **at the same time**, identical network (1000/1000 Mbps)" | One **exclusive 128-core Expanse node**, all arms in **one job**, strictly sequential, order reshuffled per rep (§4) |
| Box plots, ~15 reps (Fig 1E/1F) | Box plots, **10 reps** on the headline panel; median + IQR |
| 3000 GSA + 3000 SRA files (~7 Tbp / ~5 Tbp) for success/integrity (Suppl. S1) | That scale belongs to **E7**, not E3. E3 buys reps instead of raw TB (§3) |
| Compared *methods within iSeq* (Aspera vs AXEL vs Wget) | Compares **tools against each other** — the comparison iSeq's Fig 1C asserts but never times |
| Integrity = MD5, retry ≤3 | Integrity is the **judge**, not a footnote: md5 vs the ENA manifest decides success (§5) |

**The gap E3 exploits.** iSeq's Fig 1C is a *feature* table; its Fig 1D/1E only
ever benchmark iSeq against itself or against `edgeturbo`/SRA-Toolkit on **one
accession at a time**. Nobody has published a *many-accession, tool-vs-tool,
integrity-verified* batch comparison. That is exactly the regime adaptiSeq is
built for, and E3 is that experiment.

---

## 2. Datasets — verified live against the ENA portal API, 2026-07-17

The parent plan's tiers were **re-pulled and confirmed accurate** (rebuild any
time with `python bench/e3/make_datasets.py`, which writes both the accession
list and its md5 manifest into `datasets/`):

| Panel | Dataset | Verified today | Role |
|---|---|---|---|
| **3a** headline | `D1_fair_PRJNA916347` | **201 runs, 201 files, 4.42 GB**; **bimodal — median ≈ 0.03 MB, max 404 MB** (see ⚠️ below) | Overhead- *and* byte-mixed. Every tool can complete it → wall time is fair. |
| **3r** robustness | `D1_full_PRJNA916347` | **241 runs, 321 files, 7.59 GB** | Includes the **40 runs that ship 3 fastq files** — the ones stock iSeq drops. |
| **3b** honesty | `D2_subset_PRJNA762469` | **8 runs, 16 files, 25.88 GB**, ~1.6 GB/file | Byte-dominated: per-run overhead shrinks, batching should reach ≥ parity, not 2.8×. |
| **3c** routing | `D4_mixed` | **20 accessions**: 12 ENA + 6 SRA-only + 2 GSA | Forces every resolver branch in one list. |
| **3d** worker sweep | `D0_sweep_PRJNA762469` | **4 runs, 8 files, 11.86 GB**, ~1.5 GB/file | `-j ∈ {4,8,16}` — *one* variable → feeds E9. |
| **3s** segment sweep | `D3_seg_PRJNA540705` | **2 runs, 2 files, 23.07 GB**, ~11.5 GB/file | `--max-segments ∈ {4,8,16}` (connections per worker). |

**Three deviations from the parent plan, and why:**

1. **D1 splits into a fair panel and a robustness panel.** The parent plan runs
   "the full D1 list" and reports runs-completed. But iSeq *drops 40 of those 241
   runs*, so a single wall-time number over the full list would compare iSeq
   downloading 3.2 GB against adaptiSeq downloading 7.6 GB — flattering iSeq on
   speed for failing. Splitting them lets the paper report **speed on 3a** (all
   tools complete, apples-to-apples) and **correctness on 3r** (runs completed),
   with neither contaminating the other. This is the single most important
   design decision in E3.
2. **D2 is subsetted from 206 GB to 25.9 GB.** Full D2 × ~9 arms × 10 reps is
   **~19 TB of transfer** — days of walltime for a panel whose *purpose* is to
   show the advantage shrinks. 8 seeded runs (seed 20260717, committed) at ~1.6
   GB/file are byte-dominated by any measure. Stated as a limitation (§8).
3. **Two D1 runs excluded**: `SRR22904493` and `SRR22904402` have **no ENA
   mirror** (empty `fastq_ftp`), so 243 → 241. They'd force an SRA fallback and
   confound the panel; they cannot be manifest-described. Noted, not hidden.

> ⚠️ **The "~24 MB/file" average in the parent plan is misleading — D1 is
> strongly bimodal.** The parent plan's D1 numbers (243 runs / 321 files / 7.6 GB /
> avg 24 MB) all re-verify exactly, but the *average* hides the shape. Measured
> distribution of `D1_fair`:
>
> | Bucket | Files | Share of bytes |
> |---|---|---|
> | < 1 MB | 174 (86.6%) | ~0.4% |
> | 1–5 MB | 3 (1.5%) | |
> | 5–100 MB | 6 (3.0%) | ~1.7% |
> | **> 100 MB** | **18 (9.0%)** | **97.9%** |
>
> So 3a pays **201 per-run RTTs** (overhead-dominated *in file count*) while
> **97.9% of its bytes sit in 18 files** (byte-dominated *in transfer*). It is a
> **mixed** workload, not the clean overhead regime §5 of the parent plan assumes,
> and MB/s on 3a will be driven by those 18 files. Two implications: (i) describe
> 3a honestly as mixed; (ii) if a *pure* overhead panel is wanted, use the 177
> sub-5 MB files (~18 MB total, 177 RTTs) as a separate tier — that, not the full
> 201, is "batching's home turf". Also: 88% of D1 files fall below
> `min_file_size = 5 MB`, so they are single-segment by construction.
>
> *Lesson: the parent plan's tiers were verified on totals; totals and averages
> agreed while the distribution did not. Verify shape, not just sums.*

> ⚠️ **Finding that affects E7, not E3.** The parent plan's D5 reliability corpus
> **`PRJEB6403` is unusable as specified**: it reports 3,307 runs but only **50
> files carry `fastq_bytes`** (~0.02 TB), not the multi-TB corpus §2 assumes. E7a
> needs a different project — check `fastq_bytes` coverage before committing.

**D4 composition** (routing correctness, deliberately small — this panel is not
about bandwidth):
- **ENA HTTPS/segmented FTP:** 12 runs from D1.
- **SRA-only:** 6 runs from **PRJNA48479** — verified today that **100% of its
  11,245 runs return empty `fastq_ftp`**, so these *reliably* force the
  `.sra` → `fasterq-dump` branch. This is the parent plan's "verify before use"
  item, now verified.
- **GSA:** `CRX095512`, `CRX917377` — **iSeq's own paper accessions** (btae641
  Data Availability), so 3c is a direct turf comparison on the Huawei-Cloud path.
  Sizes come from NGDC, not ENA, so they are intentionally **absent from the
  manifest** and scored by completion only.

---

## 3. Arms

**Competitors** (the *dedicated* tools, per BENCHMARK.md's rationale — raw
aria2c can't resolve accessions and is excluded, mentioned once in text):

| Arm | Command | Why |
|---|---|---|
| `iseq` | `iseq -i LIST -g -o .` | The competitor of record, default (sequential wget). |
| `iseq-p8` | `iseq -i LIST -g -p 8 -o .` | iSeq's own parallel mode (axel). |
| `kingfisher` | `kingfisher get --run-identifiers-list LIST -m ena-ftp --check-md5sums` | Closest dedicated rival. |
| `fastq-dl` | loop, one accession at a time | Has no batch mode — the loop **is** the honest representation. |
| `fetchngs` | `nextflow run nf-core/fetchngs` | Optional (`ENABLE_FETCHNGS=1`); needs Nextflow+Singularity. |

**adaptiSeq arms:** `--no-adaptive -j {8,20,40}` and `--adaptive -j {20,40}`,
all at `--meta-jobs 8`.

> ⚠️ **`-j` is a ceiling, not a target.** The pool is `min(-j, files)`, so on
> panels with fewer files than `-j` these arms collapse into each other — on **3b**
> (16 files) `-j 20` and `-j 40` are the *same* configuration. This has always been
> true behaviourally; it is now explicit. See §7b for the per-panel table. The
> arms remain distinct on the headline panels 3a/3r (201/321 files).

**The sweeps are one-variable, not a grid.** An earlier draft crossed
`--meta-jobs` × `-j` × `--max-conns-per-host` into 17 arms (~600 GB for one
panel) — cost without interpretability, since a grid over knobs that interact
cannot attribute a difference to any single one. Each sweep now moves exactly one
knob and holds the rest at the value the other panels use:

| Panel | Variable | Held fixed | Arms |
|---|---|---|---|
| **3d** | `-j ∈ {4,8,16}` (+ `--adaptive -j 16`) | `--meta-jobs 8`, cap auto | 4 |
| **3s** | `--max-segments ∈ {4,8,16}` | `-j 4`, `--meta-jobs 8`, cap auto | 3 |

`--max-conns-per-host` is left at **auto** (`= jobs × max_segments`) so it scales
with the variable under test and never binds — it cannot silently become the thing
being measured (§7b). `--meta-jobs` is fixed at 8 throughout.

**3d's ceiling is set by the workload, not ambition:** D0 has **8 files**, so
`-j 8` is one worker per file and larger `-j` would only re-measure "there are
only 8 files". Since the pool cap landed this is now literal: **`-j 16` builds 8
workers and is the same configuration as `-j 8`**. Report 3d as `-j ∈ {4,8}` plus
the adaptive arm, and treat the `-j 16` row as a *confirmation that the cap
binds*, not as a third point on a scaling curve.

**3s deliberately runs on D3_seg, not D0** — see §7b: on D0's 1.1–2.0 GB files,
`--max-segments` 4/8/16 all collapse to the same 2–3 segments and the sweep would
be a flat line that looks like a finding. D3_seg's 11.5 GB files offer 22
segments, so 4/8/16 genuinely differ.

**Every arm is asked for gzip FASTQ from ENA (`-g`), and md5 checking is left ON
for every tool that offers it.** We deliberately do **not** pass adaptiSeq's `-k`
(skip-md5) even though BENCHMARK.md did: integrity is part of what these tools
are *for*, and switching it off would buy adaptiSeq an unearned advantage over
`kingfisher --check-md5sums`. Note this makes `sra-tools` mandatory — adaptiSeq's
preflight requires `srapath`/`vdb-validate` whenever md5 checking is on
(`cli.py::_cli_preflight`), which the job script gates on.

---

## 4. Fairness protocol (Methods subsection, extends parent §12)

1. **One node, one job, strictly sequential.** Every arm shares the same NIC, the
   same hour, the same filesystem. **No job arrays.** Concurrent arms would
   contend for the shared external link, making each arm's MB/s depend on what
   was co-scheduled beside it — the one confound that would void Fig 3.
   `--exclusive` keeps neighbours off the NIC.
2. **Order reshuffled every rep**, seeded by rep number and logged (`order_idx`
   column). BENCHMARK.md's cold-vs-warm control was a single reversed run; this
   generalizes it — over 10 reps no arm holds a systematic cold/warm position,
   and `order_idx` lets us *test* for a position effect post hoc rather than
   assert its absence.
3. **Payload deleted after every arm** (cold cache per arm, bounded disk).
4. **Success and bytes judged by md5 against the ENA manifest** — never by the
   tool's exit code, never by `du -sb`. See §5.
5. **≥10 reps on 3a**, median + IQR, box plots.
6. **Versions pinned** (`conda env export` → `bench/e3/env_adaptiseq_e3.yml`);
   accession lists + manifests committed under `datasets/`.
7. **`ascp` stub disclosure:** iSeq's startup `CheckSoftware` gate demands `ascp`
   even for the ENA wget/axel path we benchmark. Where the Aspera SDK is absent,
   a no-op stub clears the gate and is **never invoked** on the `-g` ENA route —
   the same device BENCHMARK.md documents. Real Aspera belongs to E5.

### 5. The manifest is the judge — the instrument that makes E3 defensible

The arms do not agree on names or layout: fastq-dl renames, fetchngs
restructures into `fastq/`, kingfisher can emit `.sra`, iseq writes flat. So
`bench/e3/verify_output.py` **ignores names entirely**: it hashes every data file
in the output tree and matches digests against the manifest's md5 set. A run is
COMPLETE only when *every* expected file is present and byte-identical.

Consequences, all deliberate:
- **MB/s is computed from verified bytes only** — a partial or corrupt transfer
  can never post a flattering throughput number.
- A tool that fetches a **different format** (`.sra`, decompressed fastq) has its
  row **segregated**, not deleted (parent §12.2): *what a tool chose to fetch is
  a finding, not an inconvenience.*
- adaptiSeq gets **no benefit of the doubt** — the identical criterion is applied
  to our own arms.

Validated before deployment against a real ENA file (`SRR22904257`, md5
`bfa437e8…`, matching BENCHMARK.md's independent record): a **renamed** file
still verifies; a **single flipped byte**, a **truncated** file, a **timeout**,
and **logs-without-payload** all correctly score 0 verified bytes.

---

## 6. Budget (why the walltimes are what they are)

Per rep, transfer = Σ arms × dataset size. With ~9 arms:

| Panel | Bytes/rep | Reps | Total transfer | Walltime | Bottleneck |
|---|---|---|---|---|---|
| 3a | ~40 GB | 10 | ~400 GB | 12 h | **iseq/fastq-dl**, not the link: 201 sequential per-run RTTs |
| 3r | ~68 GB | 3 | ~205 GB | 6 h | as 3a |
| 3b | ~233 GB | 5 | ~1.2 TB | 16 h | genuinely byte-bound |
| 3c | ~4 GB | 5 | ~20 GB | 4 h | `fasterq-dump` CPU on the SRA-only runs |
| 3d | ~47 GB (4 arms) | 3 | ~142 GB | 6 h | `-j 4` arm; bounded by 8 files |
| 3s | ~69 GB (3 arms) | 3 | ~208 GB | 6 h | genuinely byte-bound (11.5 GB files) |

Sequential arms are the cost driver, and that *is the result*: iSeq paying 201
resolution RTTs in series is precisely what batching removes. Per-arm timeouts
(`E3_TIMEOUT_*`) bound the damage — a timed-out arm records `status=TIMEOUT` and
scores 0, exactly as `iseq -p 8` did in BENCHMARK.md, rather than hanging the job.

**Payload lives on node-local NVMe (~1 TB), not Lustre.** The parent plan says
"stage to Lustre, never `$HOME`" — correct about `$HOME`, but Lustre OST/metadata
contention is shared and bursty, and would leak into download timings. Since every
payload is deleted right after hashing, we need neither Lustre's capacity nor its
persistence. **Results/logs go to Lustre** and survive the job.

### Disk hygiene — nothing downloaded is ever kept

E3 keeps **measurements, not data**. The ~2.3 TB it pulls across all panels is
transient; the experiment's output is a few MB of TSV. Purging happens at three
levels, so no stage can strand bytes:

| When | What | Why |
|---|---|---|
| After **every arm** | `run_arm` deletes the arm's output dir once it is hashed | Also *is* the cold-cache control (§4.3) — not merely hygiene |
| On **any exit** of `run_e3.sh` / the sbatch — including `scancel`, SIGTERM at the walltime cap, or a crash | `trap` purges `$E3_WORK` | Without this, hitting the 48 h cap mid-transfer strands up to ~26 GB (panel 3b) on NVMe |
| At **start** of a run | stale payload from a hard-killed prior run is removed | Prevents a previous run's bytes being attributed to an arm in this one |

Only `$E3_WORK` is ever touched. Results (`$E3_OUT` on Lustre: TSV, logs,
manifests, versions) are never removed. Peak transient disk is therefore one
arm's worth (~26 GB worst case), not the cumulative total.

---

## 7. Metrics & outputs

One TSV row per (panel × dataset × arm × rep) → `e3_results.tsv`:

`panel, dataset, arm, tool, rep, order_idx, wall_s, exit_code, status,
runs_complete, runs_partial, runs_expected, files_verified, files_expected,
bytes_verified, bytes_expected, bytes_on_disk, files_on_disk, extra_files,
format, MBps_verified, peak_rss_kb, cpu_pct, conc_med, conc_p95, conc_max,
conc_per_host_max, procs_max, conc_samples, host, stamp`

### 7b. Instantaneous concurrency — **connections and workers are different numbers**

`conc_*` is a **TCP connection count, not a worker count.** For adaptiSeq the two
are not interchangeable, and the ratio is **panel-dependent**, because each worker
holds one file and each file is split into
`min(max_segments, max(1, size // segment_size))` connections (`segment_size` =
512 MB default):

| Panel | File size | Connections **per worker** |
|---|---|---|
| 3a / 3r (D1) | ~22 MB | **1** (`22MB // 512MB = 0` → 1) |
| 3b (D2) | ~1.6 GB | **3** |
| E4/E2 (D3) | ~11.5 GB | **8** (hits `max_segments`) |

> ### ✅ FIXED — the worker pool used to claim workers it could never use
>
> **Was:** the pool was sized at `-j` regardless of how many files existed, so on
> a 3-file list `-j 8`, `-j 20` and `-j 40` all reported `workers = 8/20/40`
> while the wire carried **3** connections. `gate.active` was the *permitted pool
> size*, not files in flight, and the surplus workers were idle coroutines.
>
> **Fix** (`batch.py`, `aspera.py`): the pool is now `min(-j, len(tasks))`, the
> gate lowers as the tail drains, and the adaptive controller's probes are capped
> to files still outstanding. `-j` is a ceiling, not a target.
>
> **Verified** on `SMOKE_D1` (3 files) against live ENA, `--no-adaptive -j 20`:
>
> | Build | `workers_max` | `workers_med` |
> |---|---|---|
> | before (23be241) | **20** | 20 |
> | **after** | **3** | 2 |
>
> **Download behaviour is unchanged** — the surplus workers never held a file, so
> wall time, bytes and `conc_*` are unaffected and Fig 3's headline numbers do not
> move. What changes is that `workers_*` is now *true*.
>
> ⚠️ **Consequence for arms on small panels — some are now provably identical.**
> Because the pool is capped by file count, arms differing only in `-j` above the
> file count collapse to the same configuration. They always *behaved* the same
> (the extra workers were idle); now they are the same by construction and should
> be reported as one arm, not two:
>
> | Panel | Files (batch tasks) | Arms that collapse |
> |---|---|---|
> | 3a / 3r | 201 / 321 | none — `-j 8/20/40` all distinct ✅ |
> | **3b** | **16** | `fixed-j20 ≡ fixed-j40` and `adaptive-j20 ≡ adaptive-j40` (both → 16) |
> | **3c** | **≤ 20** (12 ENA + 6 SRA-only; 2 GSA route separately) | `-j 40` certainly collapses; `-j 20` collapses too unless tasks land at exactly 20. Not verified locally — the SRA-only branch needs `sra-tools`, absent on the dev box. **Read `workers_max` off the first 3c rep to pin it.** |
> | **3d** | **8** | `-j 16 ≡ -j 8` (→ 8); the sweep is effectively `-j ∈ {4,8}` |
> | **3s** | **2** | all three arms run 2 workers (`-j 4` → 2); the panel varies only `--max-segments`, which is its point |
>
> For the adaptive arms this also *narrows the search space*: `gradient_opt_fast`
> explores `1..gate.jobs`, so on 3b it now searches `1..16` instead of `1..40`.
> That is a real (and desirable) behaviour change — it no longer spends probe
> windows measuring worker counts that cannot receive a file — but it means **3b's
> adaptive arms are not comparable to a pre-fix run**. Re-run, don't mix.

Reporting either number alone would be misleading, so E3 records **both**:

| Channel | What it measures | Where | Covers |
|---|---|---|---|
| **External** — `sample_concurrency.py` | **Connections on the wire**: ESTABLISHED TCP sockets held by the arm's process tree at 5 Hz (`E3_CONC_HZ`), per remote host | `logs/conc_*.tsv` → `conc_med/p95/max/per_host_max` | **Every arm** |
| **Internal** — `aseq_run.py` | **Workers**: `min(gate.active, files outstanding)` at ~2.5 Hz, continuous, fixed *and* adaptive arms | `logs/workers_*.tsv` → `workers_med/max` | adaptiSeq |
| **Internal** — controller log | Per-probe `(workers, Mbps)` decisions | `logs/trajectories.tsv` | adaptiSeq `--adaptive` |

Cross-tool comparison must use **connections** (`conc_*`) — that is the same
measurement for iseq's `wget`, axel's 8, kingfisher's `aria2c` and adaptiSeq's
sockets, and it is what the *server* experiences. **Workers** (`workers_*`) are
adaptiSeq-internal and are what E4's Fig 4 plots, since workers are what the
controller actually tunes.

> ### ✅ FIXED — the per-host cap used to truncate the intended design
>
> **Intended** (author's spec): each worker owns one file and opens up to
> `max_segments` connections for it, so *N* in-flight files ⇒ `Σ segments(file)`
> connections — 10 × 10 GB ⇒ **80**; 10 × 10 MB ⇒ **10**.
>
> **Was:** `max_conns_per_host` defaulted to a fixed **8**, and `HostGuard`
> (`batch.py:141`) is a **process-wide semaphore per host** shared by every worker.
> All ENA files come from one host, so the cap was global and truncated the
> product. With 8 segments/file, **one file consumed the entire budget** and `-j`
> went inert — which would have silently gutted E4/D3, the long-run workload used
> to argue the controller tunes worker count.
>
> **Fix** (`options.py`): `max_conns_per_host = 0` now means **auto → `jobs *
> max_segments`**, so the cap never sits below what the design asks for. An
> explicit value still wins, and `HostGuard` keeps its real job — the 429/503
> circuit breaker that lowers the cap reactively.
>
> **Verified** (2 × ~380 MB, `--segment-size 64` ⇒ 6 segments/file, `-j 4`; spec
> = 12 connections), measured against live ENA:
>
> | Build | Peak connections |
> |---|---|
> | before (fixed default 8) | **8** — pinned at cap (p95 = 8) |
> | before, `--max-conns-per-host 64` | 11 (≈12) — proving the cap was the binder |
> | **after (auto cap, default)** | **11 (≈12)** ✅ |
>
> Integrity re-checked, not assumed: a 404 MB file over 6 segments md5-verified
> byte-exact against ENA (`404,110,842 B`, `5e6565d3…`). Full suite green; pinned
> by `test_auto_cap_does_not_truncate_intended_concurrency`, which was confirmed
> to **fail** against the old default.
>
> ⚠️ **Etiquette consequence — worth a decision.** At shipped defaults
> (`-j 20`, `max_segments 8`) the auto cap is **160**. On large-file workloads the
> engine may now open up to 160 sockets to a single archive host. The cap no longer
> acts as a standing bound (it equals the theoretical maximum by construction) —
> `HostGuard` only bites *reactively*, once a host returns 429/503. Combined with
> the ungated probe (below), adaptiSeq's politeness toward ENA is now essentially
> reactive, not proactive. That is fine as a design choice but it must not be
> described as a per-host guarantee in the C5 claim. Consider shipping a lower
> explicit default for the CLI, or capping auto at some ceiling.
>
> **Also note `segment_size = 512 MB`:** segmentation needs `size ≥ 2×512 MB` to
> yield >1 segment, so on D1 **every file is single-segment — even the 404 MB
> one**. The segmented engine is effectively inactive on panel 3a; adaptiSeq's win
> there is batching + parallel resolution (as BENCHMARK.md always said), not
> segmentation.
>
> **🔴 Second, independent bug — `probe_range_support()` bypasses the
> per-host cap.** Both download paths wrap their request in
> `async with self.host_guard.connection(self.host)` (segmented.py:257, :537), but
> the range probe (`segmented.py:~207`) calls `self.session.get()` **ungated**. So
> every worker picking up a file fires an unguarded probe: measured **12
> simultaneous connections to one EBI host under `--max-conns-per-host 8`**, and
> raising the cap to 32 changed nothing because the cap never bound on that phase.
>
> **Scope of the overshoot — it is worker-bounded, not segment-bounded.**
> `probe_range_support()` runs **once per file** (segmented.py:338), not once per
> segment, so the burst is `min(-j, files in flight)` — *not* `-j × max_segments`.
> Measured on 12 files: `-j 4 → 4` connections (worker-bound), `-j 20 → 12`
> (file-bound). So a 10 × 10 GB batch probes with **10** ungated connections, not
> 80. It is a modest, transient overshoot of the cap (10 vs 8) — but on 3a with
> `-j 40` over 201 files it reaches **40 ungated connections to one host**, which
> is the number that matters for the C5 good-citizen claim.
> Consequences: (1) it undercuts the **C5 good-citizen claim** — the documented cap
> is not the true bound; (2) a 429/503 **on the probe** is swallowed by its
> `except` and returned as `(None, False)`, i.e. "no range support", silently
> degrading the file to a single-stream download **without** calling
> `note_pushback` — so the circuit breaker never sees it. **Decide before running
> E3:** fix it (changes what E3 measures, and is the honest engineering call), or
> record the current behaviour and report the cap's real scope. Do not publish the
> per-host cap as a guarantee until this is resolved.

**Consequence for panel 3d.** Because HostGuard is process-wide, raising `-j`
alone cannot raise download concurrency past `--max-conns-per-host` (default 8).
On D0/D2 (3 segments/file) the cap binds at ~3 in-flight files, so `-j 16/32/64`
would measure the same thing and the "scaling curve" would be an artefact of our
own default. 3d therefore sweeps `--max-conns-per-host ∈ {2,4,8,16,32}` at fixed
`-j 32` alongside the `-j` sweep; the cap sweep is what actually locates E9's knee.

**Two caveats for Methods:**
- `conc_*` is a **sampled statistic, not an exact count** (5 Hz default, raised
  from 2 Hz because a ~22 MB iseq `wget` lives ~1 s); sub-tick connections are
  invisible.
- Concurrency is bounded by **available work**: on a 3-file list all of
  `-j 8/20/40` correctly read `conc_max=3` — and, since the pool cap landed,
  `workers_max=3` too, so the two channels now agree instead of the internal one
  over-reporting. Only panels with more files than workers (3a: 201) separate the
  arms.

The external channel matters most: it is the *same measurement for every tool*,
so arms are finally comparable on **what they do to the server**, not only on how
fast they finish. `conc_per_host_max` is the good-citizen number (C5/E10) — what a
single archive host saw at peak.

**Verified coverage** (the sampler only sees the arm's process tree, so this was
tested per spawn-model, not assumed):

| Arm | Spawn model | Concurrency recorded? |
|---|---|---|
| `iseq` | sequential `wget` child | ✅ verified — reads `conc≈1` |
| `iseq-p8` | `axel` child, 8 connections | ✅ (same child-process path) |
| `kingfisher` | `aria2c` child | ✅ (same child-process path) |
| `fastq-dl` | in-process, sequential | ✅ |
| `adaptiseq` | one asyncio process, N sockets | ✅ verified |
| `fetchngs` | Nextflow + **Singularity** | ⚠️ **unverified** — container workers may fall outside the tree's PID namespace. Treat its `conc_*` as unreliable until checked. Off by default. |

A 4-child parallel transfer reads `conc_max=4` while a sequential one reads
`conc_max=1`, confirming the instrument measures *offered concurrency* rather than
the `-j` knob.


> **This did not work by default and had to be built.** adaptiSeq computes
> `gate.active` every 0.4 s in `batch._repaint`, but hands it to the progress bar,
> which is silent under `-Q` **and** whenever stderr is not a TTY — i.e. always,
> under Slurm. The instantaneous concurrency was being computed and discarded, and
> the per-probe `adaptive probe:` log lines never fired because nothing configured
> INFO logging. Both are now captured.

`aseq_run.py` only calls `logging.basicConfig` and delegates to `cli.main` — the
identical `core.run` path, no injected flags. Sampling costs ~0.5% of a core and
is applied identically to every arm, so it cannot bias the comparison; it is
disclosed in Methods regardless.

**Reuse:** these traces are what **E4's Fig 4** plots (adaptive trajectory vs a
fixed arm, on a real clock) and what **E9** needs to locate the knee where the
per-host cap — not the client — becomes the limit. E3 collects them; it does not
claim them.

`bench/e3/aggregate.py` → median + IQR per arm, **speedup vs stock iseq**,
success %, format segregation, dropped-run accounting, and `fig3_<panel>.png`.
The adaptive **worker trajectory** is scraped into `logs/trajectories.tsv` for
reuse by E4.

> **Note — the end-of-run controller Note was renamed.** The probe history is now
> bounded (it used to retain every probe for the whole run just to print one
> line), so the Note reports aggregates rather than the full list and is named
> `adaptive worker summary:` — `N probe(s); best X Mbps at W worker(s); last …;
> recent: …`. The per-probe `adaptive probe:` INFO lines that `trajectories.tsv`
> actually plots are **unchanged**. `e3_lib.sh` matches both spellings, so old and
> new logs parse; a scraper matching only `worker trajectory` silently drops the
> summary line while still catching the probe lines — verify greps, don't assume.

**Figure 3 (paper):**
- **3a** box plot, MB/s per arm (headline).
- **3b** same, byte-dominated (the honesty panel).
- **3c** cross-database.
- **runs-completed bar** from 3r — the correctness win *inside* the speed figure.

---

## 8. Pre-registered expectations & honest limitations

Stating these **before** the run is what makes the result credible:

- **3a:** adaptiSeq ≫ iseq. BENCHMARK.md saw ≈2.8× MB/s at 35 runs; at 201 runs
  the per-run RTT advantage should *strengthen*. **If it doesn't, we report that.**
- **3b:** the advantage **shrinks toward parity**. Predicted, and reported as a
  panel — not buried.
- **Adaptive vs fixed:** expected **within noise** on 3a (BENCHMARK.md's honest
  negative: ~3 probe windows on a short run, and the result *flipped* between two
  runs). 3b/3d are multi-minute and are where the controller has room. E3 does
  **not** claim adaptive > fixed; that claim belongs to E4.
- **`iseq -p 8`** may time out (axel vs EBI FTP did in BENCHMARK.md). If it does,
  it is reported as TIMEOUT with 0 verified bytes — what happened, not a verdict
  about axel everywhere.
- Results depend on **live public-DB throughput and time of day** — hence
  interleaving, 10 reps, medians, and one shared time window.
- 3b is a **25.9 GB subset**, not the full 206 GB project.
- E3 says nothing about single-file throughput (aria2c wins; that's E2).

---

## 9. Execution

```bash
# once, on a LOGIN node (installs only — never benchmark on login nodes)
bash bench/e3/setup_env.sh

# rebuild lists + manifests against live ENA (the job does this too)
python bench/e3/make_datasets.py --outdir datasets

# submit: one job, all panels, sequential (recommended)
sbatch bench/e3/e3_expanse.sbatch

# or chained one-job-per-panel (shorter, requeueable; still never concurrent)
bash bench/e3/submit_e3.sh --split

# subset
PANELS="3a 3b" sbatch --export=ALL,PANELS="3a 3b" bench/e3/e3_expanse.sbatch

# aggregate (the job runs this; re-runnable on partial data)
python bench/e3/aggregate.py --tsv e3_results.tsv --outdir figs
```

Set `--account` in `e3_expanse.sbatch` (currently `umr115`). The job **hard-gates
on outbound egress** before spending any walltime (parent §16.1): if the compute
node can't reach EBI/NCBI, every number would be a proxy artefact, so it exits.

## 10. Files

| Path | Role |
|---|---|
| `bench/e3/make_datasets.py` | Builds lists + md5 manifests from the live ENA API |
| `bench/e3/verify_output.py` | The judge: name-independent md5 verification |
| `bench/e3/sample_concurrency.py` | Instantaneous concurrency (established sockets) — every arm |
| `bench/e3/aseq_run.py` | adaptiSeq CLI + controller INFO logging (internal gate trajectory) |
| `bench/e3/e3_lib.sh` | `run_arm` — time, trace, verify, record, purge |
| `bench/e3/run_e3.sh` | Arm table, panels (3a/3r/3b/3c/3d/3s/smoke), per-rep reshuffle |
| `bench/e3/e3_expanse.sbatch` | Slurm job: gates, versions, link probe, run, aggregate |
| `bench/e3/submit_e3.sh` | Submission (single or chained) |
| `bench/e3/setup_env.sh` | Conda env + version pinning |
| `bench/e3/aggregate.py` | Medians/IQR, speedup, segregation, Fig 3 |
| `datasets/*.txt`, `*.manifest` | The exact accessions + expected md5s (Data Availability) |
