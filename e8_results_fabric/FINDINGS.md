# E8 — Resource profile (Fig 6): Fabric run findings

Machine: **Fabric** (`Node-FIU`, 8 cores, 62 GB RAM), 2026-07-21. Reps: **3**
(reduced from the plan's 5 because Fabric's egress heavily throttles the EBI FTP
that iSeq/kingfisher use — one iSeq ENA rep is 10–15 min; medians over 3 reps are
stable for the RSS/CPU envelope this figure reports). Tools installed for the run:
adaptiseq 0.1.3, iseq 1.9.8 (BioOmics), kingfisher 0.5.0, sra-tools 3.4.1
(prefetch/fasterq-dump), aria2 1.36, axel 2.17.

- **8-ENA**: one ENA paired run **SRR15852400, 2.65 GB** (`.fastq.gz`),
  manifest-md5-verified. All 9 arm-reps verified byte-exact (md5 = 1).
- **8-SRA**: one SRA-only run **SRR1031066, 544 MB `.sra`** (PRJNA48479, no ENA
  fastq mirror → forces the `.sra` path). Judged by bytes/exit (SRA sizes are not
  in the ENA portal), format segregated.

## Table (median over 3 reps)

| panel | tool | wall_s | peakRSS_MB | mean_cpu% | cpu_core_s | wr_MB/s | setup/data/verify (s) | output |
|---|---|---|---|---|---|---|---|---|
| ENA | **adaptiseq** | 249 | **52** | 12.7 | 34.9 | 10.7 | 2 / 242 / 4.5 | fastq.gz ✓md5 |
| ENA | iseq | 735 | 22 | 3.2 | 23.5 | 3.6 | 4 / 717 / 14 | fastq.gz ✓md5 |
| ENA | kingfisher | **120** | 137 | 62.3 | 76.0 | 22.1 | 2.5 / 56 / 80 | fastq.gz ✓md5 |
| SRA | adaptiseq | 37 | 1134 | 389 | 145.6 | 212 | 2 / 21 / 15 | fastq.gz (rc=1*) |
| SRA | iseq | 36 | 1094 | 396 | 143.8 | 224 | 2 / 26 / 8 | fastq (rc=1*) |
| SRA | kingfisher | 20 | 1178 | 193 | 39.9 | 345 | 12 / 7 / 1.5 | fastq (uncompressed) |
| SRA | prefetch | **14** | **10** | 41.6 | **6.1** | 40 | 12 / 0 / 2.5 | .sra only |

## Findings

**1. Each tool's memory/CPU model is visible and distinct (the point of Fig 1D).**
On ENA the RSS traces are flat and cleanly separated: adaptiseq **52 MB** (single
asyncio process), iseq **22 MB** (one `wget` child at a time), kingfisher **137 MB**
(`aria2c -x8`, 8 connections). No tool is pathological.

**2. Speed ↔ resource tradeoff, and "fastest" ≠ "least work".** On the throttled
Fabric link, kingfisher's 8-connection aria2c is fastest (120 s) but costs the most
CPU (**76 core-s**) and RAM (137 MB); iSeq's single-stream FTP `wget` is slowest
(735 s, 6× kingfisher) yet draws the **least CPU** (23.5 core-s) because it idles
waiting on the throttled link; adaptiseq sits in the middle on every axis
(249 s, 52 MB, 35 core-s). This is exactly why the plan reports **`cpu_core_s` (∫ CPU
d*t*)** as the fair summary rather than wall time or peak — the ranking changes
depending on which you pick.
- adaptiseq is 3× faster than iSeq here but ~2× slower than kingfisher on this
  *single* file. That is consistent with the honest framing (single-file raw
  throughput is not adaptiSeq's claim — E2/E3); adaptiSeq's win is batch + resolve.

**3. The SRA panel is dominated by `fasterq-dump` conversion, not download.** Every
tool that converts `.sra → fastq` balloons to **~1.1–1.2 GB RSS and ~800 % CPU**
(8 cores saturated) during the convert phase — the trace shows a flat, cheap
download phase followed by the conversion spike. This is a property of the `.sra`
format, not of any downloader. **prefetch is the outlier**: it stops at `.sra`, so
it stays at **10 MB RSS / 6 core-s / 14 s** — but produces `.sra`, not fastq
(format segregated per the protocol).

**4. Format segregation matters on SRA.** adaptiseq/iseq emit **fastq.gz**
(they also spend CPU gzip-compressing → ~145 core-s); kingfisher emits
**uncompressed fastq** (3.5 GB on disk, only ~40 core-s — it skips compression);
prefetch emits **.sra** (544 MB). Comparing them on wall time alone would be
apples-to-oranges — the table records what each actually produced.

## Bugs / quirks found and handled during the run

- **kingfisher 0.5.0 × sra-tools 3.4.1 incompatibility** (SRA panel): kingfisher
  calls `prefetch -o FILE`, deprecated in sra-tools ≥ 3.x → exit 3, kingfisher's
  SRA arm failed instantly (0 bytes). **Fixed** by exporting
  `NCBI_VDB_PREFETCH_USES_OUTPUT_TO_FILE=1` (now baked into `run_e8.sh`); the SRA
  panel was re-run and kingfisher then produced a valid profile.
- **adaptiseq (and iSeq) exit `rc=1` on SRA-only runs despite producing valid
  fastq.** adaptiseq downloads the `.sra`, checks for an ENA FASTQ mirror, finds
  none, **logs the run to `fail.log` and sets exit 1 — then still converts the
  `.sra` to `_1/_2.fastq.gz`**. So the exit code reports failure while the output
  is correct and complete. Marked `rc=1*` above; a genuine adaptiSeq quirk worth a
  sentence in the paper (the resource profile itself is valid and captured).

## Addendum — why kingfisher is fast on ENA (it is NOT the "8 hands")

Follow-up probing (fixed 20 s windows on the same 1.23 GB file) settled the cause:

| client | connections | MB/s |
|---|---|---|
| curl | 1 | ~8 |
| wget (FTP) | 1 | ~8 |
| **aria2c** | **1** (`-x1`) | **~73** |
| aria2c | 8 (`-x8`) | ~64 |
| adaptiseq (aiohttp), default 2 seg | ~4 | up to ~61 (see time-drift note) |
| adaptiseq, forced 8 small segments | 8–16 | **~8–10** |

Findings:
1. **It is not parallelism.** `aria2c -x1` (one connection) is as fast as `-x8` —
   ~9× faster than curl/wget on the *same single flow*. So kingfisher's speed comes
   from aria2c's single-flow efficiency (large socket buffers / TCP window on the
   high-latency FIU↔EBI transatlantic path), **not** its 8 connections.
2. **It is not CDN caching** — a cold, never-fetched file behaves identically
   (curl 8.2 vs aria2c 74.9 MB/s cold).
3. **adaptiseq did NOT use "8 hands."** With the default `--segment-size 512 MB`, a
   1.23 GB file splits into `min(8, 1.23 GiB // 512 MiB) = 2` segments; with `-j 4`
   over 2 files that is ~4 connections, not 8. A file must be ≥ 4 GB to reach 8
   segments at the default.
4. **More hands would HURT, not help.** Forcing 8 small segments dropped adaptiseq
   to ~8–10 MB/s — EBI throttles high connection counts from this IP (the same
   429/550 behaviour E3 documented on Fabric). adaptiseq's default (few large
   segments) is the correct choice for this link; adaptiseq's aiohttp engine can
   itself reach ~61 MB/s with the default 2 segments when the link is uncongested.

## ⚠️ Two caveats that qualify the ENA wall-time comparison (resource profile is unaffected)

- **The link is strongly time-varying.** During the E8 run all single-flow tools
  were in a slow window (adaptiseq ~10, iseq ~3, kingfisher ~20 MB/s); a later probe
  saw the *same* adaptiseq default config hit ~61 MB/s and aria2c ~73. Absolute
  wall-times are therefore time-of-day artefacts (plan §8 pre-registered this). The
  *ordering* kingfisher > adaptiseq > iseq was stable across all 3 reps, but the
  *magnitude* of the gap is not a fixed property.
- **E8's arm order is fixed, not reshuffled** (adaptiseq always 1st, kingfisher
  always 3rd within a rep), unlike E3. On a link that drifts within a rep this is a
  confound for *throughput* comparison. It does **not** affect E8's actual
  deliverable — the per-tool RSS/CPU/I-O envelope and task-time breakdown, which are
  intrinsic to each tool's execution model, not to link speed.

**Bottom line for the paper:** E8 should report the *resource envelope* (RSS/CPU
model, the SRA conversion balloon, cpu_core_s) — which is robust — and must NOT use
these single-file ENA wall-times as a throughput claim. Single-file throughput is
E2's job, and aria2c winning single-file is already the pre-registered honest
result (parent plan §15).

## Instrument caveats confirmed (as pre-registered, plan §7)

- The **disk-write total carries ±1-tick error**: the SRA iseq trace shows a single
  ~13 000 MB/s spike where buffered writes flushed inside one 2 Hz tick. RSS and CPU
  curves are exact; `bytes_on_disk` is the ground-truth volume.
- Phases are 2 Hz-quantised; for `fasterq-dump` the convert step lands in
  *fetch-data* (it writes bytes), not *verify* — as stated.

## Figures

- `fig6a_traces_8-ENA.png`, `fig6a_traces_8-SRA.png` — RSS / CPU / disk-write vs
  time, one representative rep per tool (Fig 6a).
- `fig6b_taskbar_8-ENA.png`, `fig6b_taskbar_8-SRA.png` — stacked setup/fetch/verify
  task time (Fig 6b).
- `e8_results.tsv` — all 21 rows; `logs/e8_trace_*.tsv` — raw 2 Hz traces.
