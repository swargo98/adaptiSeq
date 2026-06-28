# Batch & adaptive download

adaptiSeq is built for the workload real pipelines have: **lists of accessions**,
downloaded concurrently. Pass a file (one accession per line) — mixed SRA/ENA/GSA
is fine:

```bash
adaptiseq -i accessions.txt -g
```

## How a batch runs

For SRA/ENA accessions on the default segmented engine, adaptiSeq runs a two-phase
batch:

1. **Parallel resolution** (`--meta-jobs`, default 3) — resolves accession → URLs
   for the whole list concurrently, bounded by polite per-endpoint rate limits
   (ENA / NCBI / GSA).
2. **Adaptive download pool** (`-j`, default 20) — a single-process asyncio worker
   pool pulls the resolved files, each fetched by the segmented engine.

Per-file semantics are preserved from `iseq`: skip-if-in-`success.log`, md5 check,
retry up to 3, `fail.log`, continue past failures, non-zero overall exit on any
failure. GSA accessions, `--engine classic`, `-m`, and GSA-Aspera use the
sequential path.

> **Note**
> Resolution finishes for the whole batch before downloading starts; the two
> phases do not currently overlap. (The internal `resolve_all` exposes an
> `on_task` hook for future producer/consumer streaming.)

## `-j`, `--jobs` — worker-pool size

```bash
adaptiseq -i accessions.txt -g -j 8
```

Maximum number of files downloading at once (default **20**). With `--adaptive`
(the default), this is the **ceiling**; the controller chooses how many of these
workers are actually active.

## `--adaptive` / `--no-adaptive`

```bash
adaptiseq -i accessions.txt -g                 # adaptive (default)
adaptiseq -i accessions.txt -g --no-adaptive   # fixed: all -j workers, no probing
```

The **gradient adaptive-concurrency controller** measures achieved throughput and
tunes the *active* worker count up or down, backing off when extra workers stop
paying for themselves (so you neither under-utilise the link nor hammer the
server). The controller gates workers at **file-pickup boundaries** — it never
cancels an in-flight download, which would risk corruption — so it changes *how
many* files download at once, not *which bytes* are written.

Tuning knobs:

| Flag | Meaning | Default |
| ---- | ------- | ------- |
| `--probe-window` | seconds per probe before re-measuring | 5 |
| `--cc-penalty` | worker-cost penalty `K` in `score = throughput / K**workers` | 1.01 |

Adaptive probes are logged during the run, for example:

```text
Note: adaptive probe 3: active file workers=2, measured throughput=145.2 Mbps over 4s, allowed file workers=2
```

At completion, adaptiSeq prints a compact summary with total probe count, best
probe, last probe, and only the most recent probe history. It does not retain or
print the full long-run trajectory.

> **Honesty note**
> On small batches, adaptive vs fixed is within measurement noise — the payoff is
> on long, sustained runs. See [BENCHMARK.md](../../BENCHMARK.md).

## `--meta-jobs` — resolution parallelism

```bash
adaptiseq -i big_list.txt -g --meta-jobs 5
```

How many accessions resolve concurrently (default **3**). Bounded by per-endpoint
rate limiters, not by pool size; NCBI E-utilities is held to 3 req/s (10 with
`NCBI_API_KEY`).

## Segmented-engine knobs

| Flag | Meaning | Default |
| ---- | ------- | ------- |
| `--segment-size` | target byte-range segment size (MB) | 512 |
| `--max-segments` | max concurrent connections per file | 8 |
| `--max-conns-per-host` | global cap on connections to any one host | 8 |

The per-host cap plus a reactive circuit breaker (429/503/refused → global
backoff + temporarily lowered cap) keep adaptiSeq a polite client even at high
concurrency.
