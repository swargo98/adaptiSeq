# adaptiSeq Part 3 of 3: Adaptive concurrency, batch download, and the benchmark

> This is the third of three build specifications. It assumes **Parts 1 and 2 are
> complete**: a faithful Python port of `iseq` exists with a self-contained
> segmented HTTP(S)/FTP engine wired into the download seam, fixed concurrency,
> a per-host cap, and a reactive circuit breaker.
>
> Part 3 adds the three things that distinguish adaptiSeq from a static segmented
> downloader: a gradient adaptive concurrency controller over the active worker
> count, batch parallel download with resolution/download overlap, and a benchmark
> that proves or disproves the speed claim honestly.

---

## 0. What Part 3 adds, and why the architecture is the way it is

Until now, concurrency across files has been fixed. Part 3 introduces a pool of up
to `-j/--jobs` workers and a controller that tunes how many of them are active at
any moment, between 1 and `-j`, based on measured throughput. The controller is
**gradient descent**, ported from `search.py`. It is on by default.

The single most important architectural point, stated up front because it is easy
to get wrong:

> The optimizer controls the number of active **workers**, not the number of
> **connections**. Each active worker downloads one file and opens its own
> file-size-derived segment connections (Part 2, Section 3). Total connections in
> flight is emergent: the sum over active workers of each worker's connection
> count, and it is clipped by the per-host cap (Part 2, Section 6). The optimizer
> never sets a connection count. It only opens or closes worker slots.

This mirrors fastbiodl's `download_process_status[i] = 1 if i < params[0] else 0`,
where `params[0]` is the active-worker count and the connection count is decided
elsewhere. fastbiodl tracks the emergent connection total only as a logged metric
(`active_connections`), never as a control input. Reproduce that exactly.

---

## 1. Inputs you must read first

| File | Why it matters in Part 3 |
|------|--------------------------|
| `search.py` | Source of the controller. Port `gradient_opt_fast` and its helper `run_probe`, plus the constants `exit_signal = 10 ** 10` and `cc_change_limit = 5`. **Do not port `base_optimizer`**; it pulls in `skopt` and `scipy`, and the gradient path needs neither. |
| `fastbiodl_upgrade.py` | Read `download_probing` and `run_download_optimizer` (lines ~995 to 1064) and the parallel-resolution fan-out (lines ~1235 to 1259) for the **wiring pattern**. Reproduce the behaviour without the multiprocessing/tmpfs scaffolding. |
| Part 2 engine seam | The pause token you stubbed in Part 2 (Section 2) becomes the worker gate here. |

Do not assume contents. Open and read them. Note that `search.py`'s optimizer has
bookkeeping defects; Section 3.1 tells you to fix them rather than port them
verbatim.

---

## 2. The adaptive controller (ported from `search.py`)

Port `gradient_opt_fast` and `run_probe` faithfully as the optimization
**algorithm**, then wire them as follows. Study fastbiodl's `download_probing` and
`run_download_optimizer` and reproduce their behaviour without the
multiprocessing, tmpfs, or shared-array scaffolding.

- **Worker controller.** Replace fastbiodl's `download_process_status` shared
  array with a single mutable `active_workers` integer (or an equivalent resizable
  gate) that the pool honours: at most `active_workers` workers download at once.
  Raising it lets idle workers pick up files; lowering it pauses workers, which
  cancel their in-flight segments and re-queue the file, exactly as fastbiodl does
  on pause. This is what the Part 2 pause token now drives. Bound it by `-j/--jobs`.

- **One optimizer per session, not per file.** A single controller tunes one
  global active-worker count for the whole run.

- **Throughput meter.** Maintain a 1 Hz sampler that records per-second aggregate
  throughput (Mbps) into a rolling buffer, fed by the byte-count callback you
  injected in Part 2. This is the clean equivalent of fastbiodl's
  `report_network_throughput` deque, without the CSV side effects or the
  `elapsed > 1000` heuristic.

- **Probe function** (the black box the optimizer minimizes). Given a candidate
  worker count `w`: set `active_workers = w`, wait one second for the change to
  settle, then average throughput over the remaining window, for a total
  **probe window of 5 seconds** (`--probe-window`, default 5; mirrors
  `probing_sec`). Return a **negative score**, because the optimizer minimizes.

- **Worker-cost penalty (do not skip this).** Do not score on raw throughput.
  Reproduce fastbiodl's `score = throughput / (K ** w)`, where `w` is the
  active-worker count, and return its negation. `K` is exposed as `--cc-penalty`,
  **default 1.01**. The penalty makes the optimizer prefer fewer active workers
  unless additional ones pay for themselves in proportional throughput. Pure
  throughput maximization would peg workers at `-j`, open the maximum number of
  connections, and hammer the servers. At `K = 1.01`, adding a 20th worker must
  earn roughly a 1.01^20 ~ 1.22, i.e. about a 22 percent, cumulative throughput
  premium over a single worker to be preferred, which is a mild but real bias
  toward restraint. Document this arithmetic in `README.md`.

- **Bounds and exit.** Clamp `w` to `[1, --jobs]`. Keep `cc_change_limit = 5` to
  damp oscillation and the best-seen cache reset that `gradient_opt_fast` already
  does. Return `exit_signal` when the transfer is done so the loop terminates.

- **Always on, including for small jobs.** The controller runs by default for
  every run, regardless of file count or size. `--adaptive/--no-adaptive` toggles
  it (default `--adaptive`); `--no-adaptive` runs all `-j` workers with no
  probing. There is no small-job gate. When total work is tiny and finishes inside
  a window or two, the optimizer simply returns `exit_signal` quickly and the loop
  ends, so the overhead is naturally bounded rather than special-cased.

Caveat to record in `NOTES.md`: network throughput is noisy and gradient estimates
from single 5-second windows can swing. The `cc_change_limit` clamp, the best-seen
reset, and the one-second settle delay are the mitigations; keep all three. If in
testing the controller oscillates badly, widen `--probe-window` or damp the step.
Do not remove the penalty.

### 2.1 Fix the optimizer's bookkeeping; do not port its defects

The "port faithfully" rule that applies to accession regexes does **not** apply to
`gradient_opt_fast`'s internal bookkeeping. The regexes are a behavioural contract;
the optimizer's cache handling is just code, and it has defects that will degrade
the controller if copied verbatim. Port the gradient *algorithm* (the step, the
clamp, the best-seen reset) but fix the following:

- The best-seen cache is keyed on `abs(value)` (absolute throughput-derived
  score). Two distinct worker counts that happen to produce the same absolute
  score collide and overwrite each other, corrupting the `soft_limit` derivation
  that reads `cache[max(cache.keys())]`. Key the cache on the worker count, or
  store `(score, worker_count)` pairs, so the best-seen worker count is recovered
  correctly.
- The gradient computation falls back to `gradient = 1` in degenerate cases
  (`prev == 0`) without signalling. Make the fallback explicit and logged so a
  flat or zero probe does not silently drive a full step.
- `cache.popitem(last=True)` evicts the most recently inserted entry, which is
  usually the freshest observation. Confirm the eviction policy you actually want
  (evict oldest or worst, not newest) and implement it deliberately.

State each fix in `NOTES.md` with a one-line reason. These are corrections, not
divergences from `iseq` behaviour, since `iseq` has no optimizer.

### 2.2 Interaction with the per-host cap at `--jobs 20`

With `-j/--jobs` defaulting to **20** and each worker opening up to `--max-segments`
connections, the naive emergent total against a single host could reach 20 ×
`max_segments`, which is unacceptable. This is exactly why the per-host cap from
Part 2 exists and is always on. For the common single-host batch (for example an
all-ENA list hitting EBI), the per-host cap is the **binding constraint**: the
optimizer may raise `active_workers` toward 20, but the cap clips the emergent
connection count, so effective concurrency against that host is roughly
`max_conns_per_host / connections_per_file`, not 20. Document this plainly in
`README.md` so the default `-j 20` is not misread as "160 connections to EBI." The
optimizer, the per-file segmenter, and the cap all coexist: the optimizer chooses
worker slots, the segmenter chooses per-file connections, and the cap is the hard
ceiling on what actually reaches the wire.

---

## 3. Batch parallel download

Mirror the fastbiodl worker-pool shape, simplified:

- Input: an accession-list `.txt` (one per line), the same input `iseq` accepts
  via `-i file`.
- Build a task queue of `(resolved_url, output_path, retry_count)` tuples across
  all runs of all accessions, fed **as resolution completes** (do not wait for all
  of it; see Section 4).
- Maintain a pool of up to `-j/--jobs` workers (default 20). Each worker owns one
  transport session (an `aiohttp` session for HTTP, or an FTP client), pulls one
  file at a time, and runs the segmented engine with that file's own connection
  count. The gradient controller (Section 2) decides how many workers are active
  at any moment; the rest idle until the active count rises.
- Preserve per-file semantics from Parts 1 and 2: skip-if-in-`success.log`, MD5
  check, retry up to 3, then `fail.log`. A failure of one run must not abort the
  batch; continue until the queue drains, then exit non-zero if any failures
  occurred (match the `.has_failed.flag` behaviour and final error message in
  `iseq`).

Prefer a single-process `asyncio` design with a bounded gate over `--jobs` if it
keeps the resume and log logic race-free; reach for a process pool only if you
must, and justify the choice in a short comment. The single-process design also
makes the active-worker gate trivial: it is one integer the event loop reads.

---

## 4. Parallel metadata and URL resolution (follow `iseq`'s preference order)

fastbiodl resolves accession URLs in parallel with a `ThreadPoolExecutor` that
fans out the lookup and feeds the download queue as results arrive. **Copy the
parallelism pattern, not its target.** fastbiodl only ever calls NCBI; adaptiSeq
must fan out **its own Part 1 resolver**, which is multi-database and
preference-ordered:

- the ENA-first preference for SRA/ENA/DDBJ/GEO accessions (`getSRAMetadata`
  queries ENA's `filereport` API first, falling back to the NCBI `eutils` +
  `sra-db-be` path only when ENA returns nothing), and the `-d ena|sra` override;
- the GSA path (`getGSAMetadata`) for `PRJC/CRA/SAMC/CRX/CRR`;
- the GEO indirection (`GSE`→`PRJNA`, `GSM`→`SAMN`) before the above.

Do not collapse this into a single-database lookup. The parallel stage runs that
whole preference chain for many accessions at once.

Requirements:

- Fan out resolution across accessions with a bounded pool sized by `--meta-jobs`
  (default 3). Stream resolved tasks into the download queue as they complete so
  downloading begins before every accession is resolved; the two phases overlap.
- The worker count controls queueing only. Enforce real request rates with
  **per-endpoint** rate limiters, not by pool size: ENA, NCBI, and GSA each get
  their own limiter, since one resolution may touch more than one. For NCBI, the
  eutils endpoints rate-limit to 3 requests per second without an API key and 10
  with one; throttle accordingly and read an optional key from `NCBI_API_KEY`
  (and `NCBI_EMAIL`) in the environment. Never exceed the unauthenticated limit
  when no key is present. Use the same user-agent strings the Bash uses.
- Resolution failures for one accession must not abort the others; log, continue,
  and surface unresolved accessions at the end.
- This is orthogonal to `-j/--jobs`, which governs concurrent file downloads. Keep
  the two pools and their knobs separate.

---

## 5. New flags introduced in Part 3

| Flag | Default | Semantics |
|------|---------|-----------|
| `-j, --jobs` | `20` | Maximum worker-pool size. Each worker downloads one file at a time. When `--adaptive` is on, the gradient optimizer chooses how many of these workers are active at any moment, between 1 and `-j`. |
| `--adaptive / --no-adaptive` | on | Enable the gradient controller (Section 2). `--no-adaptive` runs all `-j` workers with no probing. Always on by default, including for small jobs. |
| `--probe-window` | `5` | Optimizer probe window in seconds. |
| `--cc-penalty` | `1.01` | The `K` worker-cost penalty in the score `throughput / K**w` (Section 2). |
| `--meta-jobs` | `3` | Parallelism for metadata / URL resolution (Section 4), bounded by per-API rate limits. |

Update `iSeq.yml` to add `numpy` (the ported gradient optimizer needs it). Do
**not** add `skopt` or `scipy`; the gradient path does not use them.

---

## 6. Benchmark: verify the speed premise instead of assuming it (required)

adaptiSeq's name implies adaptivity, and the only place that adaptivity earns its
keep is wall-clock throughput on real multi-file runs. Prove it or retract the
claim. Add a `BENCHMARK.md` and a script that times wall-clock download of a
representative workload on the same machine and network, several ways:

- stock `iseq -p 8`;
- `aria2c` with comparable settings (`-x` connections, `-s` splits);
- `adaptiseq --no-adaptive -j 20 --max-segments 8` (fixed concurrency);
- `adaptiseq --adaptive -j 20 --max-segments 8` (the full controller).

Record throughput and total time for each, plus the active-worker trajectory the
controller chose over time. The comparison against fixed concurrency is the one
that isolates the controller's contribution: if `--adaptive` does not beat
`--no-adaptive`, the controller is not paying for itself and you should say so.

Report honestly. `aria2c` is a strong baseline and may win on raw throughput; if
it does, the honest pitch is the differential-tested parity with `iseq` and the
importable Python API, not speed. Do not overstate performance.

---

## 7. Acceptance criteria for Part 3

1. A batch run from a `.txt` list downloads multiple runs concurrently, respects
   `-j`, respects the per-host cap, continues past a single failing run, and exits
   non-zero overall when any run failed.
2. The gradient controller is on by default, adjusts the active-worker count
   during a run, and the trajectory is observable in the logs.
3. `--no-adaptive` runs all `-j` workers with no probing, and `--cc-penalty` and
   `--probe-window` change the controller's behaviour as documented.
4. The controller does not oscillate pathologically on synthetic throughput
   traces, verified by a unit test that drives `gradient_opt_fast` over canned
   sequences (rising, falling, noisy-flat) and asserts the step stays within
   `cc_change_limit` and converges.
5. The optimizer bookkeeping fixes of Section 2.1 are in place, each noted in
   `NOTES.md`, and a unit test covers the previously-colliding cache case.
6. Parallel resolution overlaps with downloading: tasks enter the download queue
   before all accessions are resolved, and per-endpoint rate limits (especially
   NCBI 3/s without a key) are never exceeded, verified against mocked endpoints.
7. All Part 1 and Part 2 differential and parity tests still pass; adaptivity and
   batching have not changed which bytes are fetched, only the scheduling.
8. The benchmark in Section 6 has been run and its results, including the
   adaptive-vs-fixed comparison, are recorded in `BENCHMARK.md`, whether or not
   adaptiSeq wins.

Where the sandbox is offline, the controller logic, the bookkeeping fixes, and the
rate limiters must be exercised as unit tests on synthetic traces and mocked
endpoints. State which paths were run live and which were only unit-tested. Do not
claim the controller helps on real networks if you could not benchmark it; record
that limitation in `BENCHMARK.md`.

---

## 8. How to work

1. Read `search.py` and the fastbiodl wiring functions. Write the
   decoupling-and-fix plan (Sections 2 and 2.1) before porting.
2. Build in this order, testing each before the next: the throughput meter on the
   Part 2 byte-count callback; the worker gate and pause/re-queue behaviour; the
   ported `gradient_opt_fast` + `run_probe` with the Section 2.1 fixes, tested on
   synthetic traces in isolation; the probe wired to the live meter; the batch
   pool; parallel resolution with rate limiters; then the benchmark.
3. Commit at each milestone.
4. Keep `NOTES.md` current: the optimizer fixes, the oscillation behaviour you
   observed, and the per-host-cap interaction at `-j 20`.
5. Finalize `README.md` (full flag reference, the `K` arithmetic, the per-host-cap
   explanation), `CHANGES_FROM_ISEQ.md` (what is identical, what is new, the FTP
   constraint, the adaptive controller), and `BENCHMARK.md`.

The controller is the one place novelty is wanted, and it must remain honest: it
schedules workers, it never changes which URL is chosen or which bytes are
written. Parity with `iseq`, proven by the Part 1 differential tests, is still the
load-bearing guarantee.
