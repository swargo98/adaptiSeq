# Part 5 plan — fair byte-aware benchmark, live progress, adaptive Aspera

Four items from the user. Commit at each milestone so work survives a usage-limit
pause and resumes cleanly.

## Item 1 — downloaded bytes as a first-class benchmark metric

**Problem:** different tools may download different *formats/sizes* (e.g. `.sra` vs
`.fastq.gz`, different compression), so wall-time alone is unfair.

**Plan:**
- Report, per method: wall time, **bytes downloaded**, **throughput (MB/s)**, file
  count, and the *format* fetched (extensions seen).
- Make MB/s the headline fairness metric (bytes/time), alongside raw time.
- When a method's byte total or format differs materially from the others, flag it
  explicitly in `BENCHMARK.md` so the reader isn't misled by time alone.
- Keep "files removed between runs". (`bench/benchmark_batch.sh` already removes
  and already measures `.fastq.gz`; broaden to count *all* downloaded data files
  and record format + total bytes + MB/s.)

## Item 2 — live file-level progress bar (user-friendliness)

When the batch downloader runs, show a single self-updating line:

```
adaptiSeq  [=====>      ]  12/35 files | 41.8 Mbps (1s) | 8 workers
```

- **files done / total** — a batch progress counter (incremented on each completed
  file; total = number of resolved tasks).
- **instantaneous throughput** — the **last-1-second** sample from
  `ThroughputMeter` (the exact number the optimizer probes on), not the average.
- **active workers** — `WorkerGate.active`.

**Plan:**
- Add `ThroughputMeter.last_sample()` (most recent 1 s Mbps).
- Add a `Progress` object (in `adaptiseq/progress.py`) the batch updates:
  `set_total`, `inc_done`, and a `render(meter, gate)` that writes a `\r` line to
  stderr. A background asyncio task in `BatchDownloader` repaints ~2 Hz.
- Suppressed by `-Q/--quiet`; only drawn when stderr is a TTY (CLI) — the library
  default stays silent. Final newline on completion so it doesn't clobber summary.
- Tests: progress counter math; `last_sample`; that quiet/non-TTY draws nothing.

## Item 3 — adaptive Aspera (the tough part)

**Constraint:** `ascp` transfers cannot be paused/resumed mid-file. So the gradient
controller (which pauses/re-queues) does **not** apply. Aspera concurrency is
controlled only at **file-pickup boundaries** (start/don't-start a new `ascp`), and
tuned by a different controller.

**Controller — additive-increase with efficiency hysteresis:**
- Establish a **baseline**: per-worker throughput measured at `active = 1` over one
  probe interval.
- Each interval: tentatively **add one worker** (`active += 1`), wait the interval,
  measure aggregate throughput `T`. Theoretical for `active` workers is
  `active × baseline`. Compute `efficiency = T / theoretical`.
  - If `efficiency >= --aspera-efficiency` (default **0.70**): the new worker is
    pulling its weight → **keep it** and try one more next interval.
  - Else: the link is saturated/contended → **drop that worker** (`active -= 1`) and
    **hold** (hysteresis: stop adding; do not flap). Optionally re-probe rarely.
- Bound by `-j/--jobs`. Always terminates when the queue drains.
- New flag: `--aspera-efficiency FLOAT` (0–1, default 0.70).

**Throughput for ascp (out-of-process bytes):** the Part 2/3 byte-counter only sees
the Python segmented engine; `ascp` writes bytes itself. So add a
**directory-growth meter**: sample the summed size of the output dir's in-progress
files once per second → aggregate Mbps. Reuses the `ThroughputMeter` rolling-buffer
shape but is fed by a sampler instead of a callback.

**Wiring:** an aspera batch path (workers run `ClassicEngine.fetch_aspera` per file
in an executor, file-boundary gated), driven by the `HysteresisController` over the
dir-growth meter. `core.run` routes `-a` through it (instead of today's sequential
aspera). Huawei-Cloud-wins-for-GSA and key-file discovery are unchanged.

**Testing (rigorous, since real aspera isn't in the sandbox):**
- `HysteresisController` over synthetic throughput curves: linear (keeps adding to
  `-j`), saturating at K (settles near K), noisy (no flapping), efficiency-threshold
  boundary cases. Assert the kept worker count and that it holds after backing off.
- Directory-growth meter: write bytes to files over time, assert sampled Mbps.
- End-to-end with a **fake `ascp`** (a script that writes a file's bytes over a
  short time) so the whole aspera pool + controller + meter run locally without
  real Aspera. Assert files complete and the controller adjusted workers.
- Document clearly that **real ENA Aspera was not exercised** (no aspera-cli in the
  sandbox; EBI also restricts it): controller + plumbing are tested with synthetic
  traces and a fake ascp.

## Item 4 — stop/resume on usage limit

No code; operational. Commit after every milestone (plan, benchmark, progress,
meter, controller, wiring, tests, docs) so a limit pause never loses work and the
next session resumes from a clean, pushed state.

## Build order

1. Plan (this file). 2. Benchmark bytes/throughput. 3. `last_sample` + progress
bar. 4. Dir-growth meter. 5. `HysteresisController` + synthetic tests. 6. Aspera
batch path + fake-ascp e2e test. 7. CLI flag + core wiring. 8. Docs + full suite.
