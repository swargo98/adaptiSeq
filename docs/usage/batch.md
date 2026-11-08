# Batch & adaptive download

adaptiSeq is built for the workload real pipelines have: **lists of accessions**,
downloaded concurrently. Pass a file (one accession per line) — mixed SRA/ENA/GSA
is fine:

```bash
adaptiseq -i accessions.txt -g
```

## How a batch runs

For accessions on the default segmented engine, adaptiSeq runs a two-phase batch:

1. **Parallel resolution** (`--meta-jobs`, default 3) — resolves accession → URLs
   and checksums for the whole list concurrently, each archive endpoint behind its
   own rate limiter (ENA 8 requests/s, GSA 5, NCBI 3, or 10 with `NCBI_API_KEY`).
   A failed or empty ENA answer is retried with backoff and is not read as "not in
   ENA" until about three minutes of continuous failure, a budget shared by the
   whole list. Only then does a Run fall back to NCBI SRA — and the fallback is
   announced (`N accession(s) had no usable ENA metadata and will be downloaded from
   SRA: ...`). Use [`--no-sra-fallback`](download.md) to refuse it.
2. **Adaptive download pool** (`-j`, default 20) — a single-process asyncio worker
   pool pulls the resolved files; each file is fetched by the segmented engine in
   byte ranges on several connections, and idle connections take over the
   remainder of the largest outstanding range, so connections stay busy until the
   last byte.

Per-file semantics: skip-if-in-`success.log`; **each file is md5-checked in the
pool as soon as it lands**, and a corrupt copy is deleted and fetched again in
parallel with the rest of the list (not after the batch); retry up to 3 rounds;
failures go to `fail.log` while the rest of the list continues; the overall exit
status is `1` if any Run could not be delivered and verified.

GSA accessions join the same pool (their links come from GSA's run-info table).
The **sequential path** is used for `--engine classic`, for `-m` (metadata only),
and for GSA with Aspera.

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
workers are actually active. (The `knee` controller limits *connections*, not
workers, and may use up to 64 workers when `-j` is not given.)

## `--adaptive` / `--no-adaptive`

```bash
adaptiseq -i accessions.txt -g                 # adaptive (default)
adaptiseq -i accessions.txt -g --no-adaptive   # fixed: all -j workers, no probing
```

An adaptive controller measures achieved throughput and tunes how many workers
are *active*, backing off when extra workers stop paying for themselves (so you
neither under-utilise the link nor hammer the server). Controllers gate workers
at **file-pickup boundaries** — they never cancel an in-flight download, which
would risk corruption — so they change *how many* files download at once, not
*which bytes* are written.

## `--controller` — which adaptive controller

```bash
adaptiseq -i accessions.txt -g --controller budget
```

| Controller | What it does | Use it when |
| ---------- | ------------ | ----------- |
| `topdown` *(default)* | starts at the most workers that have files to hold and steps down only when fewer is clearly faster; then watches the rate passively and searches again after a sustained drop | you want no tuning |
| `bottomup` | the original gradient optimizer: keeps probing up and down | for comparison |
| `greedy` | every worker active; backs off only on HTTP 429/503 | the archive does not push back and you want `-j` behaviour with a safety valve |
| `budget` | every worker active; steers a per-host *connection* budget: raises while it pays, cuts when it does not or on pushback | you want the fewest connections for good speed (loads the archive least) |
| `knee` | every worker active; starts at 4 connections and doubles while each doubling pays, then settles on the smallest budget that paid | you want the fewest connections for near-full speed |

The two that limit connections (`budget` and `knee`) used the fewest connections
in our benchmark (about 13 on average, against 19 for `topdown`) and were slower on
average than holding many connections; they stay available for users who want to
load an archive less. How each works and what the benchmark showed:
[Adaptive controller](../ADAPTIVE_CONTROLLER.md). From Python:
`fetch(..., controller="knee")`. The environment variable `ASEQ_ADAPTIVE_MODE`
sets the controller when neither the flag nor the argument is given.

Tuning knobs (`topdown` and `bottomup`):

| Flag | Meaning | Default |
| ---- | ------- | ------- |
| `--probe-window` | seconds per probe before re-measuring | 5 |
| `--cc-penalty` | worker-cost penalty `K` in `score = throughput / K**workers` | 1.01 |

The chosen trajectory (e.g. `1w@…→2w@…`) is logged at the end of the run.

> **Honesty note**
> In our benchmark on ENA, a fixed pool (`--no-adaptive -j 20`) was usually faster
> than the adaptive default (on one site the default took a median 1.6 and 2.0 times
> as long on a list of small runs and of large runs, on a second site 1.25 and 1.10),
> because more connections up to the archive's ceiling nearly always helped there. The adaptive default needs no
> value chosen for the list and is within about 3 % of the best fixed pool on
> lists from ENA, NCBI and GSA taken together; on NCBI extra connections bought
> nothing, and on GSA the best fixed value changed from run to run.

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
| `--max-conns-per-host` | cap on connections to any one host | auto (`-j` × `--max-segments`) |

A file is split into one range per `--segment-size`, at most `--max-segments`
(a file near the end of the list, or one fetched again after a bad checksum, may
use more of the spare budget). Set `--max-conns-per-host` lower to be gentler on a
host. The per-host guard also reacts to the archive: a refused connect while
other connections are open is read as the host's **connection ceiling** (it waits
for a slot instead of backing off), HTTP 429/503 halves the cap with exponential
backoff, and the cap climbs back by one connection every 5 s without a new
refusal. Together these keep adaptiSeq a polite client even at high concurrency.
