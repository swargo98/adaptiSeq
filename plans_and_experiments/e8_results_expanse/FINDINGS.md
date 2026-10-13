# E8 — Resource profile (Fig 6): Expanse run findings (independent analysis)

Machine: **SDSC Expanse** compute node `exp-9-52` (128-core class, requested via
Slurm; job `52340455`), 2026-07-21. Python 3.11.15, psutil 7.2.2. Tools:
adaptiseq 0.1.3, iseq 1.9.8, kingfisher 0.5.0, sra-tools (prefetch/fasterq-dump).
Reps: **5** (full plan). Output on Lustre scratch.

- **8-ENA**: one ENA paired run, **2.65 GB** `.fastq.gz` (`bytes = 2 652 616 379`),
  manifest-md5-verified. adaptiseq vs iseq vs kingfisher.
- **8-SRA**: **SRR1031060** (PRJNA48479, no ENA fastq mirror → forces `.sra`),
  200 MB `.sra` → 452 MB fastq. adaptiseq vs iseq vs kingfisher vs prefetch.
  Judged by bytes/exit (SRA sizes not in ENA), format-segregated.

> **Egress note (important).** The job's pre-flight egress check **passed** —
> `200 OK` to `ftp.sra.ebi.ac.uk`, `www.ebi.ac.uk`, `ftp.ncbi.nlm.nih.gov`. The
> ENA problems below are **slow bulk throughput**, not a blocked link.

---

## Table (median over 5 reps)

| panel | tool | wall_s | success | eff MB/s | peakRSS_MB | mean_cpu% | cpu_core_s | setup/data/verify (s) | output |
|---|---|---|---|---|---|---|---|---|---|
| ENA | adaptiseq | 1800 (TO) | **2/5** | ~1.5–1.9 | **63** | 2.6 | 47.2 | 3 / 1797 / 0 | fastq.gz ✓md5 (on completions) |
| ENA | iseq | 1800 (TO) | **0/5** | <1.5 | **21** | 0.1 | 2.4 | 6 / 1794 / 0 | fastq.gz (never finished) |
| ENA | kingfisher | 1289 | **5/5** | ~2.1 | 153 | 5.4 | 69.5 | 4 / 687 / 385 | fastq.gz ✓md5 |
| SRA | adaptiseq | 24.6 | (rc=1*) | — | 1146 | 308 | 78.0 | 3 / 18 / 3.6 | fastq.gz (rc=1*) |
| SRA | iseq | 23.5 | (rc=1*) | — | 1099 | 274 | 65.0 | 3 / 17 / 3.7 | fastq (rc=1*) |
| SRA | kingfisher | 13.1 | ok | — | 1196 | 254 | 34.6 | 8.9 / 3.7 / 0.5 | fastq (uncompressed) |
| SRA | prefetch | **9.4** | ok | — | **57** | 19 | **1.8** | 8.3 / 0 / 1.0 | .sra only |

`eff MB/s = 2652.6 MB / wall`. TO = 1800 s timeout. rc=1* = valid output despite
exit 1 (see finding 5).

---

## Findings

**1. The ENA panel is bottlenecked by this compute node's egress to EBI, not by
any tool.** Bulk EBI throughput from `exp-9-52` was **~1.5–2 MB/s** — an order of
magnitude below what the same 2.65 GB file achieves elsewhere. The disk-write
trace (`fig6a_traces_8-ENA`) sits flat at ~1–2 MB/s for the entire run; sustained
CPU is ~0 (every tool idles waiting on the link). This is the master plan §13
caveat made concrete: **an HPC "fat network" does not imply fast egress to a
specific external archive** — the SDSC↔EBI path (or EBI's throttling of the SDSC
range) is the limiter here.

**2. Completion ranking on a slow link: kingfisher > adaptiseq > iseq.** With a
30-minute wall cap the outcome is a *success-rate* result, not a speed result:
- **kingfisher 5/5** — aria2c's single-flow efficiency is the most latency/throttle-
  robust and finishes 2.65 GB in ~1289 s (~2.1 MB/s).
- **adaptiseq 2/5** — the segmented aiohttp engine completed twice (1394 s, 1786 s)
  and hit the cap three times; it sits between the other two.
- **iseq 0/5** — single-stream FTP `wget` never moved 2.65 GB inside 1800 s on this
  link (~1.5 MB/s floor). iSeq is the least robust to a slow high-latency path.

**3. The resource *fingerprint* is clean and tool-intrinsic (the actual point of
Fig 6).** Despite the slow link, the RSS traces are flat and cleanly separated —
adaptiseq **63 MB** (one asyncio process), iseq **21 MB** (one `wget` child),
kingfisher **153 MB** (`aria2c -x8`). mean_cpu tracks the delivered byte-rate:
kingfisher 5.4 % (most bytes/s → most work), adaptiseq 2.6 %, iseq 0.1 % (idlest,
slowest). These are execution-model signatures, independent of link speed.

**4. The SRA panel is fast and reproduces the `.sra`-conversion balloon.** SRA/NCBI
egress is *not* slow (SRR1031060 downloads in seconds), so 8-SRA is dominated by
`fasterq-dump`. Every tool that converts `.sra → fastq` balloons to **~1.1–1.2 GB
RSS** and multi-core CPU during conversion (adaptiseq 308 %, iseq 274 %,
kingfisher 254 % mean). **prefetch is the outlier**: it stops at `.sra`, so it
stays at **57 MB RSS / 1.8 core-s / 9.4 s** — but emits `.sra`, not fastq. This is
a property of the format, not the downloader.

**5. adaptiseq/iseq `rc=1`-with-valid-output quirk reproduces on Expanse.** On the
SRA-only run both tools download the `.sra`, find no ENA FASTQ mirror, log the run
to `fail.log` and **set exit 1 — then still convert to `_1/_2/_3.fastq`** (452 MB,
3 files present). The exit code reports failure while the output is complete. Same
genuine quirk seen on Fabric; worth one sentence in the paper.

**6. Many-core node changes the *convert* CPU ceiling, not the model.** On the
128-core node, `fasterq-dump` (adaptiseq/iseq/kingfisher SRA arms) spikes to
**peak ~2900 % CPU** (≈29 cores momentarily) vs Fabric's 8-core (~800 %) ceiling —
the convert step scales its thread fan-out to available cores. But **sustained**
convert CPU is similar (~2.5–3 cores mean), so the total `cpu_core_s` is governed
by output size, not core count.

---

## Instrument caveats (Expanse-specific)

- **`peak_cpu_pct` is unreliable on this node — use `mean_cpu%` / `cpu_core_s`.**
  The ENA trace shows a single ~2900 % CPU spike **at t=0** (process import/startup)
  with sustained CPU ≈0 thereafter. On a 128-core node psutil's momentary
  `cpu_percent` max is dominated by that transient and by cross-core sampling; it is
  **not** a meaningful sustained figure. The robust CPU metrics are `mean_cpu%`
  (delivered-rate proxy) and `cpu_core_s` (∫ CPU dt).
- **Disk-write total carries ±1-tick error** (buffered flushes land in one 2 Hz
  tick); `bytes_on_disk` is the ground-truth volume, verified against the manifest
  on the ENA completions (md5 = 1).
- **ENA wall-times are node-egress artefacts**, pre-registered (plan §8/§13). E8's
  deliverable is the RSS/CPU/IO *envelope* + task-time breakdown, which is robust;
  these single-file ENA walls must **not** be read as a throughput claim (that is
  E2/E3's job, where aria2c winning single-file is the honest pre-registered
  result).

## Figures
- `fig6a_traces_8-ENA.png` / `fig6a_traces_8-SRA.png` — RSS/CPU/disk-write vs time.
- `fig6b_taskbar_8-ENA.png` / `fig6b_taskbar_8-SRA.png` — stacked setup/fetch/verify.
- `e8_results.tsv` — all 40 rows; `logs/e8_trace_*.tsv` — raw 2 Hz traces.
