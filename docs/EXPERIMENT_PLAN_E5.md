# E5 — Adaptive Aspera, efficiency hysteresis (Fig 5) — execution plan

Refines §7 of [`EXPERIMENT_PLAN.md`](EXPERIMENT_PLAN.md) into something runnable,
in the same spirit as the E3/E7/E8 plans. E5 is the **C1 (adaptive control) story for
the Aspera transport**: a *separate* controller from the HTTP one
(`aspera.py:HysteresisController`), a *separate* figure, and a genuinely different
regime — `ascp` sessions cannot be paused/resumed mid-file, so the controller acts
only at **file-pickup boundaries** (start / don't-start a new `ascp`) and is tuned by
an **efficiency hysteresis** rather than a gradient.

Target: **Fig 5** — the additive-increase trajectory, the efficiency collapse →
back-off, adaptive-vs-fixed aggregate throughput, and the `--aspera-efficiency`
sensitivity sweep. Competitor of record for the *transport*: iSeq's own Aspera path
(btae641 Fig 1E, where Aspera is iSeq's fastest method).

> ✅ **Gate check passed on Fabric (2026-07-21).** Real IBM `ascp` 4.4.4 installed
> (`bench/setup_real_ascp.sh`), UDP 33001 to `fasp.sra.ebi.ac.uk` is **open**, and the
> **RSA** token-auth key authenticates (a 404 MB file pulled at 15.6 MB/s single
> session). So E5 runs on Fabric — it does **not** require the cloud-VM fallback the
> parent plan §13 anticipated for a UDP-blocked node.

---

## 1. What the controller does, and the finding it must reproduce

`ascp` is a blocking subprocess and one session transfers one file; there is no
mid-file pause. So the controller (`hysteresis_search`) works like this:

1. measure aggregate throughput at **1** worker (one `ascp` session) → baseline;
2. add a worker (a 2nd concurrent `ascp`), measure aggregate throughput;
3. **efficiency = throughput / (workers × baseline)**; if `efficiency ≥
   --aspera-efficiency` (default 0.70) keep the worker and try one more, else **drop
   it and settle** (hysteresis);
4. hold the settled worker count until the queue drains.

**The Part 6 finding this must reproduce:** EBI penalises multiple concurrent Aspera
sessions from one IP, so adding a 2nd session does **not** roughly double throughput
— efficiency collapses and the controller **settles at 1 worker**, while a naive
fixed `-j 8` opens 8 sessions EBI throttles.

> ✅ **Premise re-confirmed live on Fabric before designing the run** (12 s
> mid-transfer windows, real `ascp` to ENA):
>
> | concurrent sessions | aggregate MB/s | efficiency vs 1w |
> |---|---|---|
> | 1 | 10.7 | 1.00 |
> | 2 | **3.3** | **0.15** |
> | 3 | 10.7 | 0.33 |
>
> Adding a 2nd session *lowers* aggregate throughput; efficiency at 2 workers
> (~0.15) is far below 0.70, so the controller drops back to 1. The magnitudes are
> noisy (the 3-worker bounce to 10.7 is `DirGrowthMeter` sampling noise — the parent
> plan §15 pre-registers this); the **qualitative back-off is robust**.

---

## 2. Dataset — verified against the ENA portal, 2026-07-21

| Panel | Dataset | Scale | Role |
|---|---|---|---|
| all | `E5_aspera_PRJNA916347` | **8 single-file runs, 2.64 GB** (214–404 MB each) | One `ascp` session per run → clean worker↔file mapping; big enough that a 400 MB file lasts ~25 s at 15.6 MB/s, spanning several 5 s probes |

Built by selecting the 8 largest **single-file** runs from `D1_full` (so each run is
exactly one `ascp` transfer — no orphan/`_1`/`_2` ambiguity), committed with its md5
manifest. Aspera paths are resolved by adaptiSeq itself from the accession (`-a`),
using the ENA `fastq_aspera` field.

> **Why not D2/D3 (the parent plan's suggestion).** D2 files are ~1.6 GB; 8 × 1.6 GB
> × several arms × reps is >30 GB of Aspera transfer at ~15 MB/s single-session —
> many hours, and *slower still* on the throttled multi-session arms. 214–404 MB
> files keep each transfer long enough to probe (~25 s) while bounding the run. The
> controller's behaviour is size-independent; the settle point is set by EBI's
> session policy, not file size.

---

## 3. Arms & panels

All arms use **real `ascp`** (`-a`), the RSA key, and md5 checking left ON (the
manifest is the judge, reused `verify_output.py`).

| Panel | Arm | Command | Purpose |
|---|---|---|---|
| **5a** trajectory | `adaptive` | `adaptiseq -a -i LIST --adaptive -j 8 --aspera-efficiency 0.7 --probe-window 5` | The additive-increase → collapse → back-off trajectory + settle point |
| **5b** vs fixed | `fixed-j1` | `-a --no-adaptive -j 1` | The efficient operating point (baseline) |
| | `fixed-j2` | `-a --no-adaptive -j 2` | Where EBI's penalty first bites |
| | `fixed-j4` | `-a --no-adaptive -j 4` | Naive mid |
| | `fixed-j8` | `-a --no-adaptive -j 8` | Naive high — 8 sessions EBI throttles |
| | `adaptive` | (as 5a) | Should match/beat the best fixed **without tuning** |
| **5c** sensitivity | `eff-0.5 / 0.7 / 0.9` | `--adaptive -j 8 --aspera-efficiency {0.5,0.7,0.9}` | Settle point vs threshold |

`--probe-window 5` (the default) — a 400 MB file at ~15 MB/s lasts ~25 s, so a 5 s
probe sees a stable transfer. `-j 8` is the ceiling (= workload file count), so the
controller *can* explore up to 8 but is expected to settle at 1.

**Reps: 2** (≤5 ceiling). Aspera is slow and the throttled multi-session arms are
slower still; the settle point is near-deterministic, so 2 reps confirm stability.

---

## 4. Instrumentation — capturing the trajectory (Fig 5a's data)

The controller stores `(workers, throughput, efficiency)` per probe in
`HysteresisController.trajectory`, but only logs a single "settled at N" line. So E5
uses **`aspera_run.py`** — the analogue of E3's `aseq_run.py` — which monkey-patches
`adaptiseq.aspera.hysteresis_search` to emit one INFO line **per probe**
(`aspera probe: workers=W throughput=T efficiency=E`) and a final
`aspera settled: workers=N`. The driver scrapes these into `logs/trajectories.tsv`.
This changes verbosity, not behaviour — the identical `core.run` path executes.

**Metrics per (arm × rep) →** `e5_results.tsv`: `panel, arm, rep, wall_s, exit_code,
status, runs_complete, runs_expected, bytes_verified, bytes_expected, MBps_verified,
settle_workers, settle_efficiency, host, stamp`. Throughput is computed from
**verified** bytes only (a session throttled to a stall can't post a flattering
number). `settle_workers` is scraped from the trajectory (adaptive arms only).

---

## 5. Fairness & method (extends parent §12)

1. **One node, arms strictly sequential** — every arm shares the same NIC and the
   same EBI Aspera endpoint in the same window; a co-scheduled arm would contend for
   the very session budget under test. `pkill ascp` between arms so no stray session
   leaks into the next arm's meter.
2. **The manifest is the judge** (md5), never `ascp`'s exit code.
3. **Payload deleted after every arm** (bounded disk, cold cache).
4. **Real `ascp` disclosed**, with version pinned; the RSA-vs-DSA key finding (§7) is
   reported as a C5 reliability point, not hidden.
5. **Per-arm timeout** (`E5_TIMEOUT`, default 1800 s): the throttled `fixed-j8` arm
   may crawl; a timeout records `status=TIMEOUT` and scores its verified bytes,
   rather than hanging the run.

### The DSA→RSA key finding (C5 reliability, worth a sentence)

ENA migrated its Aspera key from the legacy **DSA** key
(`asperaweb_id_dsa.openssh`, still shipped by Kingfisher and old iSeq docs) to an
**RSA** token-auth key. `fasp.sra.ebi.ac.uk` now returns *"Permission denied
(publickey)"* for the DSA key. adaptiSeq's key search already prefers the RSA path,
so it keeps working where DSA-hardcoding tools fail — a concrete good-citizen /
reliability point. E5 can corroborate it directly (attempt one transfer with the old
DSA key → expect auth failure) as an optional check.

---

## 6. Budget & walltime

Single-session ≈ 15.6 MB/s; the workload is 2.64 GB.

| Panel | Transfer/rep | Reps | Dominant cost | Walltime |
|---|---|---|---|---|
| 5a | 2.64 GB (settles ~1w ≈ 170 s) + probe overhead | 2 | probe windows at 2+ workers crawl | ~15 min |
| 5b | 5 arms × 2.64 GB; **fixed-j2/4/8 throttled → slow** | 2 | `fixed-j8` (8 throttled sessions) | ~60–90 min |
| 5c | 3 arms × 2.64 GB (all settle low) | 2 | probing | ~30 min |

**Whole experiment ≈ 2–2.5 h on Fabric** (the throttled multi-session fixed arms are
the cost driver — and that *is* the result). Payload on `/tmp`, deleted per arm; only
the TSV + trajectory logs (a few MB) persist.

---

## 7. Pre-registered expectations & honest limitations

- **5a:** the trajectory shows 1w efficient → 2w efficiency collapse (<0.70) → settle
  at **1 worker**. If EBI's policy has changed and 2 workers scale, E5 reports that.
- **5b:** aggregate MB/s is **flat or decreasing** in fixed `-j` (1 ≥ 2, 4, 8);
  `fixed-j8` is slowest (most throttled). **adaptive ≈ fixed-j1** without being told
  the answer — the C1 claim: it finds the efficient point by itself.
- **5c:** a *lower* efficiency threshold (0.5) may accept a 2nd worker that a higher
  one (0.9) rejects; all are expected to settle low given the steep collapse. Shows
  the knob behaves monotonically and justifies the 0.70 default.
- **Limitations:** (i) `DirGrowthMeter` magnitudes are noisy (§1) — the **qualitative**
  back-off is the claim, not the exact MB/s; (ii) single ENA endpoint, one node, one
  time window (Aspera throughput is time-of-day sensitive); (iii) GSA Aspera
  (Huawei-wins, sequential by design) is **out of scope** — the parent plan says not
  to over-test it; (iv) reps=2 (settle point is near-deterministic).

---

## 8. Execution

```bash
# once: install the REAL ascp + ENA RSA key (NOT the benchmark stub)
bash bench/setup_real_ascp.sh
python bench/e3/make_datasets.py --outdir datasets   # (E5 list is committed; this refreshes md5s)

# Fabric (this box): no Slurm
bash bench/e5/run_fabric.sh
PANELS="5a" bash bench/e5/run_fabric.sh

# Expanse: one job (gates on UDP-33001 egress before spending walltime)
sbatch bench/e5/e5_expanse.sbatch

# aggregate → Fig 5
python bench/e5/aggregate_e5.py --outdir e5_results
```

## 9. Files

| Path | Role |
|---|---|
| `bench/e5/run_e5.sh` | Driver: panels 5a/5b/5c, arm table, per-rep loop, `pkill ascp` between arms |
| `bench/e5/aspera_run.py` | adaptiSeq CLI + per-probe trajectory logging (patches `hysteresis_search`) |
| `bench/e5/e5_lib.sh` | `run_aspera_arm` — time, verify (md5), scrape settle/trajectory, record, purge |
| `bench/e5/aggregate_e5.py` | Fig 5a trajectory, 5b adaptive-vs-fixed bars, 5c sensitivity |
| `bench/e5/e5_expanse.sbatch` | Slurm job: UDP-33001 gate, versions, run, aggregate |
| `bench/e5/run_fabric.sh` | Fabric local runner |
| `bench/setup_real_ascp.sh` | **reused** — real IBM `ascp` + ENA RSA key |
| `bench/e3/verify_output.py` | **reused** — md5 judge |
| `datasets/E5_aspera_PRJNA916347.*` | the 8-run workload + manifest |
