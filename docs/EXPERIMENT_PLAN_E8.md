# E8 — Resource profile (Fig 6, mirrors iSeq Fig 1D) — execution plan

Refines §10 of [`EXPERIMENT_PLAN.md`](EXPERIMENT_PLAN.md) into something runnable,
in the same spirit as [`EXPERIMENT_PLAN_E3.md`](EXPERIMENT_PLAN_E3.md) and
[`EXPERIMENT_PLAN_E7.md`](EXPERIMENT_PLAN_E7.md). E8 is the **"applications-note"
figure**: iSeq's Fig 1D (time / memory / CPU / average-I/O traces + a task-breakdown
bar) is the single most reproduced panel in a downloader paper, and E8 reproduces it
for adaptiSeq against the field.

Target: **Fig 6** — per-tool resource traces (peak RSS, %CPU, disk I/O over a real
clock) + a stacked task-time bar (setup / fetch-data / verify), for **one
representative ENA fetch and one representative SRA fetch**, across
**adaptiSeq vs iSeq vs Kingfisher vs prefetch**.

Competitor of record: **iSeq** (Chao *et al.*, *Bioinformatics* 2024, btae641),
whose Fig 1D is the template.

Runs on the **same two machines as E3/E7** (Fabric = this dev box, `Node-FIU`;
Expanse = the SDSC HPC node), so the resource envelope is reported on both a
commodity box and an HPC node — a spread iSeq's single-machine Fig 1D never shows.

---

## 1. What iSeq's Fig 1D did, and what E8 must reproduce

Read off btae641 Fig 1D directly — the bar is theirs:

| iSeq Fig 1D | What E8 does |
|---|---|
| Traces of **elapsed time, memory, CPU, average I/O** for a single download | Same four signals, sampled from the **whole process tree at 2 Hz** with `psutil`, per tool (§7) |
| A **task-breakdown bar** (send-request / fetch-metadata / fetch-data / md5-check) | Same bar, but measured **tool-agnostically** from first-byte / last-byte / exit timestamps (§5) so every tool is broken down by the *same* instrument, not by trusting each tool's self-report |
| iSeq vs `edgeturbo` / SRA-Toolkit, **one machine** | adaptiSeq vs **iSeq, Kingfisher, prefetch**, on **two machines** |
| Reports raw memory/CPU | Reports the same **plus `cpu_core_s`** (∫ CPU d*t*) as the honest cross-model summary (§8) |

**The nuance E8 must be honest about (parent §10).** adaptiSeq is a **single
asyncio process** with up to `-j` in-process workers; iSeq is **subprocess-per-run**
(`wget`/`axel` children); prefetch + `fasterq-dump` spawns a **CPU-heavy converter**.
These are different execution models, so a single "peak RSS" or "%CPU" number
flatters whichever model the metric happens to suit. E8 therefore reports the
**area under the CPU curve** (`cpu_core_s`, core-seconds) as the fair summary:
adaptiSeq may draw *more* CPU while it probes concurrency but finish *sooner*, and
core-seconds captures the actual work done, not the instantaneous peak. This is
stated in the figure caption, not buried.

---

## 2. Panels & datasets

Two panels, each **one representative run** (Fig 1D profiles a single accession —
E8 does the same, and buys reps instead of scale):

| Panel | Fetch | Run | Why |
|---|---|---|---|
| **8-ENA** | ENA `.fastq.gz` (HTTPS/segmented) | 1 run from `D2_subset_PRJNA762469`, **~1.6 GB** | Big enough that RSS/CPU/I/O curves have shape (tens of s); the common ENA path |
| **8-SRA** | SRA `.sra` → `fasterq-dump` | `E8_SRA_ACC` (default a run from **PRJNA48479**, SRA-only) | Forces the `.sra` + convert path — the CPU/I/O profile that differs most from ENA, and prefetch's home turf |

Both single-run lists are derived at run time (`head -1` of the committed dataset
for ENA; a named accession for SRA), so **no new committed dataset is introduced** —
E8 reuses E3's `make_datasets.py` output and its manifest as the md5 judge.

> ⚠️ **The SRA run's size is not in the ENA portal**, so it is not manifest-scored.
> The 8-SRA panel is judged by **bytes-on-disk + successful `.sra`/fastq
> production**, not md5-against-manifest (SRA sizes come from NCBI, not ENA — the
> same reason E3's D4 GSA rows are absent from its manifest). **Verify the chosen
> `E8_SRA_ACC` is ~0.5–2 GB before the run** (`srapath` / `vdb-dump --info`): too
> small and the curves are all startup transient; too large and `fasterq-dump`
> conversion dominates the walltime. The default is a placeholder — pin a sized run
> on the day, exactly as the parent plan says to re-pull sizes before benchmarking.

> ⚠️ **The 8-ENA run IS manifest-scored** (it comes from `D2_subset`, which has
> full `fastq_bytes`/`fastq_md5`), so its resource numbers are only counted when the
> transfer verified byte-exact — a crashed or truncated fetch cannot post a
> flattering (low-RSS, short) profile.

---

## 3. Arms

md5 checking is left **ON** for every tool that offers it — the **md5-check phase is
part of the task bar**, so switching it off would delete a stage E8 exists to
measure. This makes `sra-tools` mandatory (the job gates on it).

| Panel | Arm | Command | Model |
|---|---|---|---|
| both | `adaptiseq` | `adaptiseq -i RUN -g -j 4 -o .` | single asyncio process |
| both | `iseq` | `iseq -i RUN -g -o .` | wget subprocess-per-file |
| both | `kingfisher` | `kingfisher get -r RUN -m ena-ftp --check-md5sums` | aria2c child |
| **8-SRA** | `prefetch` | `prefetch RUN && vdb-validate RUN` | SRA-Toolkit; validate = the md5 stage |

`-j 4` (not the shipped 20) for the ENA arm: a single ~1.6 GB file segments into
~3 connections anyway (`EXPERIMENT_PLAN_E3.md` §7b), so a high `-j` would only add
idle-worker noise to the RSS trace. E8 profiles a *representative* fetch, not peak
concurrency (that is E9). prefetch is ENA-incapable, so it appears only in 8-SRA.

---

## 4. Fairness protocol (extends E3 §4)

1. **One node, one job, strictly sequential** — arms never overlap; a co-scheduled
   arm would pollute the CPU/I/O trace of its neighbour. `--exclusive` on Expanse.
2. **Payload deleted after every arm** (cold cache; bounded disk).
3. **Same sampler, same rate, every arm** — `profile_run.py` at 2 Hz over the whole
   process tree, applied identically to iSeq's children, aria2c, `fasterq-dump` and
   adaptiSeq's sockets. The instrument cannot favour a model because it is external
   to all of them (`psutil` walks the PID tree).
4. **ENA panel judged by the manifest md5** (reused `verify_output.py`); SRA panel
   by bytes-on-disk + exit (see §2).
5. **≥ reps, median + IQR**; the trace *curves* are drawn from the **median-wall
   rep** (a single representative run, as Fig 1D shows one), the *summary stats*
   from all reps.
6. **Versions pinned**, `ascp` stub disclosed — identical to E3.

---

## 5. The task-breakdown bar — measured, not self-reported

iSeq's bar trusts iSeq's own stage prints. E8 cannot do that across four tools with
four different logs, so it derives the three phases from **timestamps the sampler
observes directly**, identically for every tool:

| Phase | Boundary | Captures |
|---|---|---|
| **setup** | `t_start → t_first_byte` | send-request + **metadata/resolve** + connection open (no data on disk yet) |
| **fetch-data** | `t_first_byte → t_last_growth` | the actual transfer (for SRA, includes `fasterq-dump` conversion, which writes new bytes — noted in the caption) |
| **verify** | `t_last_growth → t_exit` | md5 / `vdb-validate` (file present, no new bytes, process still alive) |

`t_first_byte` = first sample where any data file exists; `t_last_growth` = last
sample where on-disk bytes increased. This is the same tool-agnostic
file-watching instrument E7b uses for resume offsets, repurposed. **Caveat for
Methods:** it is a 2 Hz sampled boundary, so sub-500 ms phases (e.g. a tiny run's
verify) are quantised; and for `fasterq-dump` the convert step lands in *fetch-data*,
not *verify*, because it writes bytes — stated, not hidden.

---

## 6. Budget & walltime (≤ 5 reps)

Single-file fetches are cheap, so E8 can afford the full **5 reps** the user's
ceiling allows — reps here build the RSS/CPU distribution Fig 1D-style box needs.

| Panel | Per-arm | Arms | Reps | Panel walltime |
|---|---|---|---|---|
| 8-ENA | ~10–90 s (~1.6 GB) | 3 | 5 | ~15–25 min |
| 8-SRA | ~1–5 min (`.sra` + `fasterq-dump` convert) | 4 | 5 | ~45–90 min |

`fasterq-dump` conversion is the cost driver and *that is part of the finding* —
the SRA path spends real CPU that the ENA path does not.

**Whole-experiment estimate (both panels, 5 reps):**

| Machine | Estimate | Request |
|---|---|---|
| **Expanse** | **~1.5–2.5 h** (128 cores; conversion is fast, transfers RTT-bound) | `--time=04:00:00` (margin) |
| **Fabric** | **~1.5–3 h** (8 cores → `fasterq-dump` conversion slower; throttled link) | no Slurm cap — but pin the box for a couple of hours |

Per-arm timeouts (`E8_TIMEOUT_*`) bound the damage. Disk hygiene is identical to
E3/E7: payload on node-local NVMe (Expanse) / `/tmp` (Fabric), deleted after every
arm and on any exit; only the TSVs + trace files + figures (a few MB) survive.

---

## 7. Metrics & outputs

One summary TSV row per (panel × arm × rep) → `e8_results.tsv`:

`panel, dataset, arm, tool, rep, wall_s, exit_code, status, peak_rss_mb,
mean_rss_mb, mean_cpu_pct, peak_cpu_pct, cpu_core_s, read_total_mb, write_total_mb,
mean_write_mbps, phase_setup_s, phase_data_s, phase_verify_s, bytes_verified,
bytes_on_disk, files_on_disk, format, md5_ok, host, stamp`

Plus, per (arm × rep), a 2 Hz trace file `logs/e8_trace_<panel>_<arm>_rep<r>.tsv`:
`t_rel_s, rss_mb, cpu_pct, read_mbps, write_mbps, nprocs` — the raw material for the
curve figure.

**Sampling honesty (Methods):**
- **CPU** is `Σ (Δcpu_time / Δwall)` over the tree from `cpu_times()` deltas — robust
  to short-lived children between ticks, unlike a single `cpu_percent()` call.
- **I/O** is `psutil` `io_counters().read_bytes/write_bytes` (disk, **not** network —
  network bytes are not "I/O" in Fig 1D's sense; the write curve ≈ data hitting
  disk, the read curve ≈ md5 re-reads). A child that dies between ticks can drop its
  final counter delta, so **totals carry ±1-tick error**; the curve shape is exact.
  `bytes_on_disk` (measured after) is the ground-truth transferred volume.
- **RSS** is `Σ memory_info().rss` over the tree — for adaptiSeq's single process
  this is one number; for iSeq/prefetch it sums the transient children, which is the
  honest envelope of the subprocess-per-run model (parent §10).
- Sampling costs < 1% of a core and is applied identically to every arm, so it
  cannot bias the comparison; disclosed regardless.

`aggregate_e8.py` →
- **Fig 6a** — three stacked trace panels (RSS, %CPU, disk-write MB/s) vs time, one
  representative rep per tool overlaid, per panel.
- **Fig 6b** — stacked task-time bar (setup / fetch-data / verify) per tool.
- **Table** — median peak RSS, mean %CPU, **`cpu_core_s` (energy proxy)**, mean
  write MB/s, wall, per (panel × tool), with IQR.

---

## 8. Pre-registered expectations & honest limitations

Stated **before** the run:

- **RSS:** adaptiSeq's single-process asyncio footprint is **flat and modest**;
  iSeq's peak is the sum of transient `wget` children; prefetch + `fasterq-dump`
  spikes on convert (it rebuilds reads in memory). No tool is expected to be
  pathological; if adaptiSeq's `-j` pool balloons RSS, E8 reports it.
- **CPU:** ENA transfers are I/O-bound → low %CPU for all. **8-SRA is where CPU
  shows up**, dominated by `fasterq-dump` decompression/conversion — expected to be
  the largest `cpu_core_s` in the study, for every tool that uses it (including
  adaptiSeq's SRA fallback and iseq). This is a property of the `.sra` format, not
  of any downloader, and E8 says so.
- **Task bar:** iSeq's **setup phase is larger** (serial per-run resolve); adaptiSeq
  overlaps resolve with transfer so its setup slice is thinner — the same C3 batch
  advantage E3 measures, now visible as a *phase*, on a single run it is modest.
- **`cpu_core_s`:** the fair summary — adaptiSeq may show higher instantaneous CPU
  while probing yet a **competitive or lower core-seconds** because it finishes
  sooner. If it does not, E8 reports that honestly (it is a profile, not a
  contest).
- **Limitations:** (i) **single representative run per panel**, like Fig 1D — not a
  size sweep (that is E2/E9); (ii) I/O totals carry ±1-tick sampler error (§7);
  (iii) the SRA panel is bytes/exit-judged, not md5-against-manifest (§2); (iv)
  `fasterq-dump` convert lands in *fetch-data*, not *verify* (§5).

---

## 9. Execution

```bash
# once, on a LOGIN node (Expanse) — reuses E3's env (iseq, kingfisher, sra-tools…)
bash bench/e3/setup_env.sh
python bench/e3/make_datasets.py --outdir datasets   # provides the D2 run + manifest

# --- Expanse: one job, both panels, sequential ---
sbatch bench/e8/e8_expanse.sbatch
PANELS="8-ENA" sbatch --export=ALL,PANELS="8-ENA" bench/e8/e8_expanse.sbatch
# pin a sized SRA run:
E8_SRA_ACC=SRRxxxxxxx sbatch --export=ALL,E8_SRA_ACC=SRRxxxxxxx bench/e8/e8_expanse.sbatch

# --- Fabric (this box): no Slurm, run directly ---
bash bench/e8/run_fabric.sh
PANELS="8-ENA" bash bench/e8/run_fabric.sh

# aggregate (the job runs this; re-runnable on partial data)
python bench/e8/aggregate_e8.py --outdir e8_results
```

Set `--account` in `e8_expanse.sbatch` (currently `umr115`). Like E3/E7, the job
**hard-gates on outbound egress** before spending walltime.

## 10. Files

| Path | Role |
|---|---|
| `bench/e8/run_e8.sh` | Driver: panels 8-ENA / 8-SRA, arm table, per-rep loop |
| `bench/e8/profile_run.py` | The instrument: 2 Hz psutil tree sampler, phase timing, verify, one TSV row + a trace file |
| `bench/e8/e8_expanse.sbatch` | Slurm job (Expanse): gates, versions, run, aggregate |
| `bench/e8/run_fabric.sh` | Fabric local runner (no Slurm) |
| `bench/e8/aggregate_e8.py` | Fig 6a traces, Fig 6b task bar, resource table (incl. `cpu_core_s`) |
| `bench/e3/make_datasets.py` | **reused** — provides the ENA run + manifest |
| `bench/e3/verify_output.py` | **reused** — md5 judge for the ENA panel |
| `bench/e3/setup_env.sh` | **reused** — the pinned conda env |
