# E7 — Reliability & resumability (Table 3) — execution plan

Refines §9 of [`EXPERIMENT_PLAN.md`](EXPERIMENT_PLAN.md) into something runnable,
in the same spirit as [`EXPERIMENT_PLAN_E3.md`](EXPERIMENT_PLAN_E3.md). E7 is the
**C5 (reliability / good-citizen) + C4 (segmented, resumable engine)** evidence:
the claim is that adaptiSeq **finishes what it starts, correctly** — it resumes
from a kill without re-downloading, never finalises a truncated file, backs off a
throttling host instead of hammering it, and completes 3-file runs that stock iSeq
drops. This is the *correctness* companion to E3's *speed* figure.

Target: **Table 3** (large-corpus success/integrity + resume correctness) plus one
small circuit-breaker trace figure and the 3-file-run completion bar (shared with
E3's 3r robustness call-out).

Competitor of record: **iSeq** (Chao *et al.*, *Bioinformatics* 2024, btae641),
with **kingfisher** where it has a comparable feature.

Runs on the **same two machines as E3**, and *this is deliberate* — E7 has one
regime (server-side throttling, E7d) that appears **naturally on Fabric and not on
Expanse**, so the pair is the experiment, exactly as it was for E3:

- **Fabric** — this dev box: 8 cores, 62 GB RAM, `Node-FIU`, egress to EBI that
  **throttles high concurrency** (FTP `429`/`550` under many connections). The
  circuit breaker (E7d) fires here *for free*.
- **Expanse** — SDSC HPC node: 128 cores, 1000/1000 Mbps, `--exclusive`, **no
  observed throttling** but **higher RTT to EBI**. The synthetic origin server
  (§7c/§7d) reproduces the throttling regime here deterministically.

---

## 1. What iSeq did, and where E7 must meet or beat it

Read off btae641 directly — the bar is theirs:

| iSeq's Supplementary S1 | What E7 does |
|---|---|
| 3000 GSA + 3000 SRA files, success rate + MD5/`vdb-validate` integrity | Same *design* (success% + md5 integrity, side by side vs iSeq) at a **bounded, byte-verified corpus** — the scale argument is E7a; the point is tool-vs-tool integrity, which S1 never reports |
| Integrity = MD5, retry ≤ 3 rounds | Same policy; the **ENA manifest is the judge**, applied identically to every tool (reused from E3 — `verify_output.py`) |
| **No resume-correctness test at all** | **E7b is the novel contribution**: kill mid-transfer, prove it resumes from the `.part` offset, not from zero, and the final md5 still matches |
| **No never-truncate guarantee tested** | **E7c**: range-incapable host → single-stream path yields a complete, md5-valid file; a short-read never gets finalised |
| **No circuit-breaker / etiquette test** | **E7d**: drive 429/503 and show `HostGuard` trips, backs off exponentially, and recovers — the C5 good-citizen number |
| iSeq drops runs shipping 3 fastq files (`wget` multiline-URL bug) | **E7e**: reproduce `SRR22904269` &c. — adaptiSeq completes a strict superset (shared with E3's 3r panel) |

**The gap E7 exploits.** iSeq's S1 proves iSeq is *reliable against itself* on a
huge corpus. Nobody has published **resume correctness, never-truncate, and
circuit-breaker behaviour, tool-vs-tool, md5-judged**. Those are exactly the
mechanisms C4/C5 claim, and E7 is the experiment that tests them rather than
asserting them in a feature table.

---

## 2. Sub-experiments

| ID | Name | Contribution | Instrument | Environment |
|---|---|---|---|---|
| **E7a** | Large-corpus success / integrity | C5 + integrity | live ENA, manifest judge | both |
| **E7b** | Resume correctness (kill → restart) | **C4 (headline of E7)** | live ENA, `.part` offset probe | both |
| **E7c** | Never-truncate / corruption | C4 | **local origin server** (deterministic) | both |
| **E7d** | Circuit breaker (429/503 back-off) | **C5 (good-citizen)** | local origin server + opportunistic live-throttle on Fabric | both |
| **E7e** | 3-file-run completion | C5 correctness | live ENA, manifest judge | both |

E7c and E7d run against a **self-contained local HTTP origin** (`e7_origin.py`)
rather than a public archive, because the behaviours they test — a range-incapable
server, a truncated response, a server that returns `429` — cannot be *summoned on
demand* from EBI, and testing them against live infrastructure would be both
non-reproducible and impolite. Driving the real engine (`SegmentedDownloader`,
`HostGuard`) against a server we fully control makes E7c/E7d **deterministic and
identical on both machines** — which is the whole point of a reliability claim.

---

## 3. Datasets — reused from E3 (built by `bench/e3/make_datasets.py`)

E7 deliberately reuses E3's dataset builder; no new ENA lists are introduced, so
the same committed manifests judge both experiments.

| Sub-exp | Dataset | Scale | Role |
|---|---|---|---|
| **E7a** | `D1_full_PRJNA916347` | **241 runs, 321 files, 7.59 GB** | Reliability corpus: many runs, byte-verifiable, includes the 3-file runs |
| **E7b** | `D3_seg_PRJNA540705` (1 file) | **~11.5 GB single file** | A file large enough that a kill lands mid-transfer and resume has something to skip |
| **E7c** | — (synthetic, `e7_origin.py`) | 3 × ~64 MB local files | Range-incapable / truncating / corrupting server |
| **E7d** | — (synthetic) + Fabric live | 1 × ~256 MB local file | 429/503 injection at a set probability |
| **E7e** | `D1_threefile_PRJNA916347` | **~40 runs, 3 fastq each** | The runs stock iSeq drops |

> ⚠️ **Why not the parent plan's D5 (`PRJEB6403`).** `EXPERIMENT_PLAN_E3.md` §2
> already flagged it: `PRJEB6403` reports 3,307 runs but **only 50 carry
> `fastq_bytes`** (~0.02 TB), so it cannot be manifest-described at the scale §9 of
> the parent plan assumes. E7a therefore uses **`D1_full` (241 runs, fully
> manifested)** as an honest, byte-verified reliability corpus, and states the
> scale limitation in §8 rather than shipping a corpus the judge can't score. If a
> larger *real* corpus is wanted later, re-pull `fastq_bytes` coverage first
> (`make_datasets.py` prints it) and only then commit it — the parent plan's
> "verify shape, not just sums" lesson applies here too.

> ⚠️ **E7b runs on ONE ~11.5 GB file, not the pair.** `D3_seg` has 2 files; the
> resume harness forces **single-stream** (`--max-segments 1`) so the `.part` file
> grows **contiguously** and its size *is* the number of bytes on disk — the only
> way to measure a resume offset honestly. With segments writing at scattered
> `pwrite` offsets, `.part` size is the highest offset touched, not contiguous
> bytes, and "resumed from 50%" would be unmeasurable. Single-stream is slower but
> it is the configuration under test (C4's resume map), and 11.5 GB is plenty of
> transfer to kill into.

---

## 4. Arms & trials

### E7a — corpus success/integrity (one arm per tool, sequential)

| Arm | Command | md5 |
|---|---|---|
| `iseq` | `iseq -i LIST -g -o .` | wget + md5 |
| `kingfisher` | `kingfisher get --run-identifiers-list LIST -m ena-ftp --check-md5sums` | on |
| `adaptiseq` | `adaptiseq -i LIST -g -j 8 --meta-jobs 8 -o .` | **on** (no `-k`) |

md5 checking is **left ON for every tool**, exactly as E3 argued: integrity is
what these tools are *for*, and E7 is *about* integrity, so switching it off would
be self-defeating. This makes `sra-tools` (`srapath`/`vdb-validate`) mandatory —
the job script gates on it (`cli.py::_cli_preflight`).

### E7b — resume correctness (the C4 headline)

For each **kill fraction** `f ∈ {0.25, 0.50, 0.75}` and each tool that claims
resume, `resume_probe.py`:

1. launches the arm in its own process group, downloading the ~11.5 GB file;
2. polls the largest file in the output dir at 10 Hz; when it reaches `f ×
   file_size`, sends **`SIGKILL`** to the whole group (a hard kill, not a clean
   shutdown — the worst case for resume);
3. records `offset_at_kill` (bytes on disk at the kill);
4. **relaunches the identical command** and records `resume_start_bytes` — the
   bytes already present when the restarted process first touches the file;
5. waits for completion, then judges the final file against the manifest md5.

| Arm | Resume mechanism |
|---|---|
| `adaptiseq` | `.part` + `.part.meta` offset map (`--max-segments 1` → contiguous `.part`) |
| `iseq` | `wget -c` (partial file in place) |
| `kingfisher` | `aria2c` `.aria2` control file |

**Resume verdict** (per trial): **RESUMED** iff `resume_start_bytes ≈
offset_at_kill` (within a tolerance) **and** the final file md5-matches the
manifest. **RESTARTED** iff `resume_start_bytes ≈ 0` (bytes wasted =
`offset_at_kill`). **CORRUPT** iff the file finalises but the md5 fails — the worst
outcome, and the one E7 is built to catch.

### E7c — never-truncate / corruption (deterministic, local)

`engine_probe.py` drives the real `SegmentedDownloader` against `e7_origin.py`:

| Check | Server mode | Assertion |
|---|---|---|
| **never-truncate (single-stream)** | `norange` (200, no `Accept-Ranges`) | file completes, size == full, md5 == expected; the range-incapable path did **not** silently truncate |
| **short-read rejected** | `truncate` (drops the connection at 60%) | the engine does **not** rename a short `.part` to the final name; it fails/retries, leaving no corrupt final file |
| **corruption detected (end-to-end)** | live ENA, small D1 run | after a clean download, flip one byte, drop the id from `success.log`, re-run → adaptiSeq's md5 check (`integrity.py`, ≤3 rounds) detects the mismatch and re-downloads to a passing md5 |

### E7d — circuit breaker (C5 good-citizen)

- **Synthetic (both machines):** `e7_origin.py --mode throttle --status 429
  --prob 0.5` returns `429` on half of segment requests. `engine_probe.py` drives
  the engine at high concurrency and records, from `HostGuard.trips` and the INFO
  log: number of pushbacks seen, the cap trajectory (`cap` halves per trip,
  recovers `+1` per clean response), the exponential backoff delays, and that the
  download **still completes with a valid md5**. The naive contrast — the same
  transfer with the breaker disabled — hammers the server (all requests, no
  back-off).
- **Opportunistic (Fabric only):** rerun E3's `adaptiseq-fixed-j40` against live
  ENA on Fabric, where the link **already** 429/550s under high concurrency
  (documented in E3's Fabric analysis), and capture the same `HostGuard` trace on
  real infrastructure. On Expanse this regime does not occur, so the live panel is
  Fabric-only and the synthetic panel carries the cross-machine claim.

### E7e — 3-file-run completion

`iseq` vs `adaptiseq` on `D1_threefile` (the ≥3-fastq runs). Judged by the
manifest: **runs completed**. Reproduces E3's 3r call-out as a standalone
correctness row for Table 3.

---

## 5. Fairness protocol (extends E3 §4, parent §12)

1. **One node, one job, strictly sequential** — every arm shares the same NIC,
   hour, and filesystem; `--exclusive` on Expanse. No job arrays (concurrent arms
   would contend for the link and, worse for E7d, cross-trip each other's circuit
   breakers).
2. **The ENA manifest is the judge** — success/bytes come from md5 against the
   manifest, never a tool's exit code (`verify_output.py`, reused verbatim from
   E3). adaptiSeq gets no benefit of the doubt.
3. **Payload deleted after every trial** (bounded disk; also the cold-cache
   control). The resume harness deletes between kill fractions so no trial inherits
   a previous trial's `.part`.
4. **Versions pinned** (`conda env export`, reused from `bench/e3/setup_env.sh`);
   accession lists + manifests committed under `datasets/` (Data Availability).
5. **`ascp` stub disclosure** — identical to E3: a no-op stub clears iSeq's
   `CheckSoftware` gate on the `-g` ENA route and is never invoked. Real Aspera
   resume behaviour is out of scope (that is E5).
6. **The synthetic origin is disclosed in Methods** — E7c/E7d state plainly that
   the never-truncate and circuit-breaker regimes are driven by a local server, and
   why (they cannot be summoned from EBI on demand). The live-throttle Fabric panel
   corroborates E7d on real infrastructure.

---

## 6. Budget & walltime (≤ 5 reps everywhere)

Reliability is near-deterministic, so reps guard against transient network state
rather than build a distribution — **3 reps** is the default (5 is the ceiling the
user set; overkill for a success%/md5 verdict). Per-machine, per-rep transfer:

| Sub-exp | Bytes/rep | Reps | Dominant cost | Walltime/rep |
|---|---|---|---|---|
| **E7a** | ~23 GB (iseq+kingfisher+adaptiseq × 7.6 GB) | 3 | **iseq's 241 sequential RTTs** | 60–100 min |
| **E7b** | ~35 GB (3 kills × ~11.5 GB, mostly one file) × tools | 3 | single-stream 11.5 GB transfers | 25–45 min |
| **E7c** | ~0.2 GB (local) | 2 | negligible (loopback) | < 10 min total |
| **E7d** | ~0.5 GB (local) + backoff sleeps | 2 | **exponential back-off waits** (up to 60 s/trip) | 15–30 min total |
| **E7e** | ~2 GB (iseq+adaptiseq) | 3 | iseq per-run RTTs | 10–20 min |

**Whole-experiment estimate (all sub-exps, 3 reps):**

| Machine | Estimate | Request |
|---|---|---|
| **Expanse** | **~6–8 h** (iseq's serial RTTs dominate; higher EBI RTT makes E7a slower than on Fabric) | `--time=16:00:00` (margin for iseq timeouts) |
| **Fabric** | **~5–8 h** (throttled link slows large transfers; E7d live-throttle panel adds ~15 min) | no Slurm cap — but it monopolises the box; run overnight |

Per-arm timeouts (`E7_TIMEOUT_*`) bound the damage: a timed-out arm records
`status=TIMEOUT` and scores 0, exactly as in E3, rather than hanging the job.

**Disk hygiene** — identical to E3: payload lives on node-local NVMe (Expanse) /
`/tmp` (Fabric), is deleted after every trial and on any exit (`trap`), and only
`$E7_OUT` (TSV + logs, a few MB, on Lustre) survives. Peak transient disk ≈ one
11.5 GB file (E7b).

---

## 7. Metrics & outputs

### 7a. Corpus / completion rows (E7a, E7e) — one TSV row per (sub-exp × tool × rep)

Reuses E3's schema so `verify_output.py` and the aggregator drop straight in:
`subexp, dataset, arm, tool, rep, wall_s, exit_code, status, runs_complete,
runs_partial, runs_expected, files_verified, files_expected, bytes_verified,
bytes_expected, md5_pass_rate, retries, fail_log_n, format, host, stamp`.

`retries` and `fail_log_n` are scraped from the arm's log (adaptiSeq/iseq both
write `fail.log`/`success.log`; the aggregator counts re-download rounds).

### 7b. Resume rows (E7b) — one row per (tool × kill_frac × rep)

`subexp, tool, file_bytes, kill_frac, offset_at_kill, resume_start_bytes,
bytes_wasted, resumed(bool), final_md5_ok(bool), wall_resume_s, verdict, host,
stamp`. `bytes_wasted = max(0, offset_at_kill − resume_start_bytes)` is the C4
money number: **≈ 0 means resume works.**

### 7c/7d. Engine-probe rows

`subexp, mode, check, passed(bool), detail` — e.g. `never_truncate,norange,ok,
"size=67108864 md5=match"`; `circuit_breaker,throttle,ok,"trips=7 cap 8→1→8
backoff=[1,2,4,..] completed md5=match"`. The circuit-breaker cap/backoff series is
also written to `logs/hostguard_*.tsv` for the trace figure.

### Aggregation (`aggregate_e7.py`)

- **Table 3** — per tool: corpus success %, md5 pass %, retries, fail.log count
  (E7a); resume verdict matrix (E7b); never-truncate pass (E7c); circuit-breaker
  trips/backoff/completed (E7d); 3-file-run completion (E7e).
- **Fig (E7d)** — `HostGuard` cap vs time overlaid on requests/pushbacks (the
  good-citizen trace), synthetic + Fabric-live.
- **Resume bar (E7b)** — `bytes_wasted / file_size` per tool per kill fraction
  (adaptiSeq ≈ 0; whoever restarts from scratch ≈ `kill_frac`).

---

## 8. Pre-registered expectations & honest limitations

Stated **before** the run:

- **E7a:** adaptiSeq and kingfisher complete ~100% with 100% md5 pass; **iseq
  drops the 3-file runs** (~40/241 → ~200/241 complete), which is the E7e result
  showing up inside the corpus. adaptiSeq's success is a **strict superset**.
- **E7b:** adaptiSeq **RESUMED** at all three kill fractions, `bytes_wasted ≈ 0`,
  final md5 pass. `wget -c` (iseq) should resume too — E7 will confirm or refute
  per tool, not assume. If any tool restarts from zero, that is the finding.
- **E7c:** the range-incapable path completes without truncation (the
  never-truncate guarantee); a short-read is **never** finalised. If it is, that is
  a C4 bug and E7 must report it, not hide it.
- **E7d:** `HostGuard` trips on 429/503, cap halves per trip and recovers, the
  transfer still completes with valid md5. On Fabric the same trace appears on live
  ENA under `-j 40`; on Expanse only the synthetic panel fires (no live
  throttling), and that is stated, not hidden.
- **Limitations:** (i) E7a is a **241-run corpus, not iSeq's 6000-file S1** — the
  scale claim is bounded by an honest, byte-verifiable list (see §3). (ii) E7c/E7d
  use a **synthetic origin**; disclosed, with the Fabric live-throttle panel as
  corroboration. (iii) The `probe_range_support()` ungated-probe caveat from
  `EXPERIMENT_PLAN_E3.md` §7b is **relevant to E7d's C5 claim** — the per-host cap
  is reactive, not a standing guarantee; E7d reports the cap's *real* scope, and
  the paper must not claim more (see the E3 plan's decision box). (iv) Aspera
  resume is out of scope (E5).

---

## 9. Execution

```bash
# once, on a LOGIN node (Expanse) — reuses E3's env (iseq, kingfisher, sra-tools…)
bash bench/e3/setup_env.sh

# rebuild lists + manifests against live ENA (the job does this too)
python bench/e3/make_datasets.py --outdir datasets

# --- Expanse: one job, all sub-experiments, sequential ---
sbatch bench/e7/e7_expanse.sbatch
PANELS="7a 7b" sbatch --export=ALL,PANELS="7a 7b" bench/e7/e7_expanse.sbatch

# --- Fabric (this box): no Slurm, run directly ---
bash bench/e7/run_fabric.sh              # all sub-experiments
PANELS="7c 7d" bash bench/e7/run_fabric.sh

# aggregate (the job runs this; re-runnable on partial data)
python bench/e7/aggregate_e7.py --tsv e7_results/e7_results.tsv --outdir e7_results
```

Set `--account` in `e7_expanse.sbatch` (currently `umr115`). Like E3, the job
**hard-gates on outbound egress** before spending walltime.

## 10. Files

| Path | Role |
|---|---|
| `bench/e7/run_e7.sh` | Driver: sub-experiments 7a/7b/7c/7d/7e/smoke, per-rep loop |
| `bench/e7/e7_lib.sh` | `run_corpus_arm` (time, trace, verify, record, purge) — reuses E3's verifier |
| `bench/e7/resume_probe.py` | E7b: kill → restart harness, `.part` offset instrument |
| `bench/e7/e7_origin.py` | Local HTTP origin: `range`/`norange`/`truncate`/`throttle`/`corrupt` modes |
| `bench/e7/engine_probe.py` | E7c/E7d: drives `SegmentedDownloader` + `HostGuard` against the origin |
| `bench/e7/e7_expanse.sbatch` | Slurm job (Expanse): gates, versions, run, aggregate |
| `bench/e7/run_fabric.sh` | Fabric local runner (no Slurm): gates, run, aggregate |
| `bench/e7/aggregate_e7.py` | Table 3, resume bar, circuit-breaker trace figure |
| `bench/e3/make_datasets.py` | **reused** — builds `D1_full`, `D3_seg`, `D1_threefile` |
| `bench/e3/verify_output.py` | **reused** — the name-independent md5 judge |
| `bench/e3/setup_env.sh` | **reused** — the pinned conda env |
