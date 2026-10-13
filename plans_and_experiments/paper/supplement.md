# Supplementary material (draft)

Assembled from existing result files, unchanged. Each section opens with the
caveat that must travel with it. Source files are named so every value can be
traced; nothing here was re-measured for this draft.

All experiments below ran adaptiSeq **0.1.3**, iSeq 1.9.8, Kingfisher 0.5.0,
sra-tools 3.4.1. The main text benchmarks 0.1.4, which differs from 0.1.3 only in
the exit status and logging of SRA-only runs under `-g` (see S3, footnote).

---

## S1. Reliability and resumability (E7b, E7c, E7d)

**Caveat.** One machine (Fabric, 8 cores), 2 repetitions per condition; the
never-truncate, short-read, and synthetic circuit-breaker checks run against a
local test server, not a public archive.

Source: `e7_results_fabric/e7_resume.tsv`, `e7_engine.tsv`, `FINDINGS.md`.

**Table S1. Resume after a kill (404 MB file, single stream).**

| Tool | Killed at | Outcome | Bytes re-downloaded | Final md5 valid | Trials |
|---|---|---|---|---|---|
| adaptiSeq | 25%, 50%, 75% | resumed from offset | 0% | 6/6 | 6 |
| iSeq | 25%, 50%, 75% | resumed from offset | 0% | 6/6 | 6 |

Both tools resume correctly. Resume is reported as a verified property of
adaptiSeq, not as an advantage over iSeq.

**Table S2. Transfer-engine failure handling (adaptiSeq).**

| Check | Condition | Passed | What was observed |
|---|---|---|---|
| Never truncate | server without range support | 2/2 | single-stream fallback; complete file, md5 match |
| Short read | connection dropped mid-body | 2/2 | truncated `.part` never renamed to the final file |
| Corruption | one byte flipped after download (live ENA) | 1/1 | md5 check caught it; re-download gave a valid md5 |
| Circuit breaker | synthetic HTTP 429 responses | 2/2 | host cap halved per trip, backoff 1, 2, 4, 8 s; completed, md5 valid |
| Circuit breaker | live ENA, `-j 40` | 1/1 | 42 server pushbacks; backed off; 200 runs completed |

---

## S2. Request-rate etiquette of parallel resolution (E10c)

**Caveat.** This is a simulation. It drives the production limiter
(`adaptiseq.ratelimits.EndpointLimiters`, unmodified) with the real per-accession
request pattern, but the network is replaced by a fixed 50 ms delay and no
request reaches a live endpoint. It shows the mechanism holds the cap; it does
not measure resolution speed against other tools.

Source: `e10_results_fabric/e10_etiquette.tsv`, `FINDINGS.md` (section 10c).
120 synthetic accessions (40% SRA-only, 40% ENA, 20% GSA). Metric: peak requests
to NCBI in any 1-second window.

**Table S3. Peak NCBI request rate (requests/s) against `--meta-jobs`.**

| Resolver | NCBI API key | Documented cap | 1 | 3 | 8 | 16 |
|---|---|---|---|---|---|---|
| adaptiSeq limiter | no | 3 | 3 | 3 | 3 | 3 |
| same pool, no limiter | no | 3 | 8 | 22 | 56 | 96 |
| adaptiSeq limiter | yes | 10 | 4 | 8 | 8 | 8 |
| same pool, no limiter | yes | 10 | 8 | 22 | 56 | 96 |

---

## S3. Resource use (E8)

**Caveat.** Single-file transfers, so these are resource envelopes, not
throughput results; wall times on the ENA panel reflect each machine's link to
ENA on the day and are not comparable between machines. The SRA panel used a
different accession on each machine (Fabric SRR1031066, Expanse SRR1031060).

Source: `e8_results_fabric/FINDINGS.md` (3 reps), `e8_results_expanse/FINDINGS.md`
(5 reps); medians.

**Table S4. Peak memory and CPU, one 2.65 GB ENA paired run (`.fastq.gz`).**

| Machine | Tool | Peak RSS (MB) | Mean CPU (%) | CPU core-seconds | Completed |
|---|---|---|---|---|---|
| Fabric | adaptiSeq | 52 | 12.7 | 34.9 | 3/3 |
| Fabric | iSeq | 22 | 3.2 | 23.5 | 3/3 |
| Fabric | Kingfisher | 137 | 62.3 | 76.0 | 3/3 |
| Expanse | adaptiSeq | 63 | 2.6 | 47.2 | 2/5 (1800 s limit) |
| Expanse | iSeq | 21 | 0.1 | 2.4 | 0/5 (1800 s limit) |
| Expanse | Kingfisher | 153 | 5.4 | 69.5 | 5/5 |

On Expanse the ENA link delivered roughly 1.5 to 2 MB/s for a single file during
this job, so adaptiSeq and iSeq hit the 30-minute limit in most repetitions. The
memory figures are unaffected.

**Table S5. Peak memory and CPU, one SRA-only run converted to FASTQ.**

| Machine | Tool | Wall (s) | Peak RSS (MB) | CPU core-seconds | Output |
|---|---|---|---|---|---|
| Fabric | adaptiSeq | 37 | 1134 | 145.6 | `.fastq.gz` * |
| Fabric | iSeq | 36 | 1094 | 143.8 | `.fastq` * |
| Fabric | Kingfisher | 20 | 1178 | 39.9 | `.fastq` |
| Fabric | prefetch | 14 | 10 | 6.1 | `.sra` only |
| Expanse | adaptiSeq | 24.6 | 1146 | 78.0 | `.fastq.gz` * |
| Expanse | iSeq | 23.5 | 1099 | 65.0 | `.fastq` * |
| Expanse | Kingfisher | 13.1 | 1196 | 34.6 | `.fastq` |
| Expanse | prefetch | 9.4 | 57 | 1.8 | `.sra` only |

\* adaptiSeq 0.1.3 and iSeq 1.9.8 exited with status 1 on these runs although the
output was complete. adaptiSeq 0.1.4 validates the `.sra` and exits 0; iSeq's
behaviour is unchanged. The memory peak in every converting tool is
`fasterq-dump`.

---

## S4. Adaptive and fixed worker counts in an earlier benchmark (old E3)

**Caveat.** An earlier adaptiSeq (0.1.3) under non-default settings
(`--meta-jobs 8`; the top-down arms also used a probe window of 8 instead of 5),
and the arm order was effectively fixed across repetitions, so arms did not
sample network conditions evenly. These numbers support one qualitative
statement only: a fixed `-j 40` can collapse on a many-small-files workload,
and the adaptive controller started from the same cap does not. They do not show
that adaptive beats a well-chosen fixed setting (compare `fixed -j 20`).

Source: `e3_results_expanse/e3_results.tsv`, `e3_results/e3_results.tsv` (Fabric);
median verified MB/s [IQR], n = 3 (241 runs) or 5 (201 runs, 8 runs).

**Table S6. Median verified throughput (MB/s) by worker policy.**

| Machine | Dataset | fixed `-j 8` | fixed `-j 20` | fixed `-j 40` | top-down, cap 20 | top-down, cap 40 |
|---|---|---|---|---|---|---|
| Expanse | 241 runs, 7.6 GB | 44.7 [41.9, 49.9] | 66.9 [61.1, 77.1] | **7.4** [7.3, 7.7] | 65.0 [63.1, 71.7] | 49.8 [42.4, 55.0] |
| Fabric | 241 runs, 7.6 GB | 40.8 [40.6, 44.0] | 70.0 [59.8, 76.1] | **9.7** [6.7, 29.3] | 73.1 [64.5, 73.7] | 39.4 [39.3, 46.6] |
| Expanse | 201 runs, 4.4 GB | 26.2 [25.0, 37.4] | 44.6 [43.6, 55.1] | 27.1 [11.1, 50.2] | 40.8 [38.1, 42.7] | 46.0 [32.1, 60.2] |
| Fabric | 201 runs, 4.4 GB | 36.5 [30.0, 39.2] | 35.4 [34.2, 39.2] | **6.8** [6.4, 9.4] | 32.0 [31.1, 32.7] | 31.0 [23.0, 36.2] |
| Expanse | 8 runs, 25.9 GB | 123.5 [115.7, 137.7] | 132.5 [130.5, 136.1] | 147.8 [102.0, 180.1] | 173.9 [147.0, 177.4] | 149.5 [149.5, 160.9] |
| Fabric | 8 runs, 25.9 GB | 130.9 [75.8, 135.5] | 123.1 [119.2, 142.9] | 153.4 [115.7, 155.2] | 122.2 [89.8, 134.4] | 93.6 [75.0, 102.3] |

"Top-down" is the controller that 0.1.3 and 0.1.4 use by default (recorded in the
result files as `adaptiseq-climb-j20` / `-j40`).

---

## Not included

Dropped as the plan directs: the mixed-database panel 3c, the E10 comparison of
resolution speed against other tools, E5 (Aspera speed), E2, E4, E9.
