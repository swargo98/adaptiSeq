# adaptiSeq benchmark

Spec §6 requires proving (or retracting) the speed premise rather than assuming
it. This file records a wall-clock comparison and reports honestly.

## How to run

```bash
python bench/benchmark.py                      # default: 4 small ENA runs
python bench/benchmark.py SRR... SRR... ...     # your own workload
```

Each available method downloads the same resolved file set into a fresh temp
directory; the script reports wall-clock time, total bytes, and throughput.

## Methods

| Method | What it is |
|--------|-----------|
| `iseq -p 8` | stock iseq with 8 axel connections (baseline) |
| `aria2c -x8 -s8` | aria2c, 8 connections / 8 splits (strong baseline) |
| `adaptiseq --no-adaptive -j 20 --max-segments 8` | fixed concurrency |
| `adaptiseq --adaptive -j 20 --max-segments 8` | the gradient controller |

The **adaptive vs no-adaptive** comparison is the one that isolates the
controller's contribution: if `--adaptive` does not beat `--no-adaptive`, the
controller is not paying for itself, and this file says so.

## Result recorded in this sandbox (2026-06-11)

Workload: 4 small, long-archived ENA runs (`SRR1553457`, `SRR1553380`,
`SRR1553453`, `SRR1553469`) → **7 fastq.gz files, ~13.6 MB total**.

| Method | Wall time | Throughput |
|--------|-----------|-----------|
| `iseq -p 8` | — | SKIPPED (iseq not installed in sandbox) |
| `aria2c -x8 -s8` | **1.49 s** | **73.2 Mbps** |
| `adaptiseq --no-adaptive` | 3.03 s | 36.0 Mbps |
| `adaptiseq --adaptive` | 2.92 s | 37.4 Mbps |

## Honest interpretation

- **aria2c wins on raw throughput (~2×).** This is expected — aria2c is a strong,
  C-based, highly-tuned downloader. As the spec anticipates, adaptiSeq's honest
  pitch is **not** raw speed; it is the differential-tested **parity with `iseq`**
  (the exact same URLs, metadata, integrity policy, logs, and merge) and the
  **importable, typed Python API** — neither of which aria2c offers. aria2c also
  does not resolve SRA/ENA/GSA/GEO accessions, fetch metadata, verify MD5/
  vdb-validate, write success/fail logs, or merge runs.

- **Adaptive ≈ fixed here, and the comparison is inconclusive on this workload.**
  The entire run finishes in ~3 s, which is *shorter than the controller's first
  5 s probe window* (`--probe-window 5`). The optimizer therefore never completes
  a probe cycle before the queue drains and `exit_signal` ends the loop — by
  design the overhead is naturally bounded for tiny jobs (spec §2: "no small-job
  gate ... the optimizer simply returns `exit_signal` quickly"). So on a 13 MB
  workload the controller can neither help nor hurt meaningfully; the ~3 % delta
  is noise.

- **What this sandbox could not measure.** A representative workload where the
  controller earns its keep is *many large files over a sustained multi-minute
  run on a real network*, long enough for several 5 s probe windows so the
  gradient can actually search the worker-count space. That workload (hundreds of
  MB to GBs) was not run here because the sandbox is bandwidth/space constrained
  and the realistic ENA fastqs are ~130 MB each. **We therefore do not claim the
  adaptive controller improves real-network throughput; that claim is unproven
  here and should be benchmarked on a production-sized run before being made.**

- **What *was* proven.** Correctness/parity: the segmented engine (adaptive and
  fixed) produces **byte-identical** files to `wget`/iseq (verified live on
  `SRR1553469` `_1`/`_2`), and the full Part 1/2 differential suite still passes.
  The controller's *logic* (convergence, step-bounding, the §2.1 fixes) is unit-
  tested on synthetic traces; its live trajectory is observable in the logs.

## Reproducing the controller's behaviour on a longer run

To actually exercise the controller, run a larger list with a short probe window
and watch the trajectory line adaptiSeq logs:

```bash
adaptiseq -i big_list.txt -g -j 20 --adaptive --probe-window 5
# ... Note: adaptive worker trajectory: 1w@..Mbps, 2w@..Mbps, 5w@..Mbps, ...
```
