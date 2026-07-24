# adaptiSeq — Implementation notes and design-decision log

This file is the running log of every deliberate judgement call in adaptiSeq's
implementation.

Decision policy: non-obvious behaviour must be **deliberate and documented**, never
accidental. Every entry below names the behaviour and the reason.

---

## 1. Plan (build order, per Section 9.2)

1. Scaffold the installable package + console entry point + the engine seam.
2. Accession validation (`validateQuery`) + routing (GSA vs SRA/ENA).
3. Metadata fetching for ENA, SRA-fallback, and GSA (CSV + XLSX).
4. Per-run URL resolution (`downloadSRA` / `downloadGSA`) through the classic seam.
5. Integrity (`checkSRA` / `checkGSA`) + `success.log` / `fail.log`.
6. Conversion (`fasterq-dump` + `pigz`) and merge (`mergeSRArun` / `mergeGSArun`).
7. The per-accession process loop and the file-list input path.
8. Public library API (`fetch`, `resolve`, `get_metadata`).
9. Differential harness + golden fixtures + unit tests + API-drift canary.
10. README, environment.yml, install verification.

## 2. Architecture decisions

- **Metadata bytes come from `wget`, not `requests`.** adaptiSeq fetches every
  metadata file by shelling to `wget` with specific flags, user-agents, and POST
  bodies, so the files are exactly what the archive serves, rather than
  reimplementing the HTTP with `requests`. This keeps `requests` out of the hard
  dependency set. All network I/O for metadata/GEO/GSA-search/spider-size lives in
  `adaptiseq/net.py`.
- **The engine seam** (`adaptiseq/engine/classic.py::ClassicEngine.fetch`) is the
  single place bytes of *sequence data* are pulled. `downloadSRA`/`downloadGSA`
  ports in `resolve.py` call `engine.fetch(url, dest)` (wget/axel) or
  `engine.fetch_aspera(link, db)` (ascp). Part 2 swaps the engine without touching
  resolution, integrity, logging, or merge.
- **Global Bash state becomes an `Options`/`RunContext` dataclass** threaded
  explicitly instead of shell globals (`gzip`, `fastq`, `database`, `parallel`,
  `aspera`, `speed`, `skip_md5`, `protocol`, `quiet`, `metadata`, `merge`,
  `threads`, `output`). `database` is mutable (ENA→SRA fallback).
- **Colour output is produced only by the CLI's reporter**, never by the library
  functions, satisfying Section 6 ("must not call sys.exit or print colour
  codes"). `adaptiseq/console.py` holds `AnsiReporter` (exact bash escape codes)
  and `NullReporter`. Library API uses `NullReporter` by default.

## 3. Behaviour checklist — output requirements (Section 3)

- [x] URL resolution: `downloadSRA`/`downloadGSA`/`getSRAMetadata`/
      `getGSAMetadata`/`validateQuery` (ENA vol path, srapath,
      GSA Huawei vs ftp, fastq.gz vs .sra, `-d`/`-g`/`-a`/`-r` interactions).
- [x] Metadata endpoints + filenames + formats + columns + user-agents fixed by
      the archive APIs.
- [x] Accession regexes are a behavioural contract (see `accession.py` docstrings).
- [x] MD5/integrity policy: `vdb-validate` for `.sra`, md5-vs-metadata
      for `.fastq.gz`, GSA vs project `md5sum.txt`; ≤3 rounds then `fail.log`;
      `success.log` line format `$(date)\t$ID`; `-k` skips.
- [x] Resume/skip: ID already in `success.log` is skipped.
- [x] External tools shelled out, not reimplemented (fasterq-dump, pigz,
      vdb-validate, srapath, ascp, md5sum, wget, axel). `CheckSoftware` → preflight.
- [x] Merge (`-e ex|sa|st`) implements symlink/rename/concatenate logic incl.
      single-run rename and differing-prefix cases.
- [x] Coloured `Note`/`Error`/`How to solve?` message style.

## 4. Behaviour checklist — CLI flags (Section 4)

`-i/--input`, `-m/--metadata`, `-g/--gzip`, `-q/--fastq`, `-t/--threads` (8),
`-e/--merge [ex|sa|st]`, `-d/--database [ena|sra]` (auto), `-a/--aspera`,
`-s/--speed` (1000), `-k/--skip-md5`, `-r/--protocol [ftp|https]` (ftp),
`-Q/--quiet`, `-o/--output`, `-p/--parallel`, `-h/--help`, `-v/--version`
(`adaptiSeq 0.1.0`), `--engine [segmented|classic]` (classic-only in Part 1).

## 5. Deliberate design decisions (with reasons)

1. **Preflight runs after argparse handles `--help`/`--version`.** Acceptance
   criteria 1 & 2 require `adaptiseq --help`/`--version` to work unconditionally,
   and argparse exits on those during parsing. So adaptiSeq runs the tool preflight
   only for real work (after help/version), gated so it never blocks help.
2. **Per-run retry counter resets per Run.** The retry counter is reset per Run, so
   a Run that exhausts its 3 retries does not push every subsequent Run in the same
   accession straight to `fail.log`. The README documents "a maximum of three
   rounds" *per Run*. The differential harness compares `success.log`/`fail.log` as
   sets of IDs, so the common (all-success) path is unaffected.
3. **`file`-based text detection for input.** adaptiSeq treats `-i` as a file when a
   path exists at that string and is a regular file; otherwise a single accession.
   CRLF is stripped on read. This avoids depending on libmagic, while a real
   accession string (e.g. `SRR7706354`) is never an existing path.

4. **Needs-based tool preflight.** adaptiSeq's CLI runs a *needs-based* preflight:
   metadata-only (``-m``) requires only ``wget``; a real download requires the full
   base set (plus ``fasterq-dump`` for ``-q``/``-e``, ``axel`` for ``-p``). It never
   demands a tool a given run won't use, which also makes the metadata differential
   test runnable on machines without sra-tools.

5. **GSA retry is a per-file loop.** The md5 retry re-fetches only the failing file
   (not every file of the CRR), with the counter reset per file (same family as
   decision #2). Observable ``success.log``/``fail.log`` ID sets are unaffected on
   the common path.

6. **`success.log` cleanup uses the literal SaveName.** The "already downloaded"
   hints render ``sed -i '/SaveName/d' success.log`` with the actual save name.
   Cosmetic stdout only; the harness compares log contents, not these hints.

7. **`adaptiseq.resolve` (the public function) shadows the `resolve.py`
   submodule.** Section 6 mandates ``from adaptiseq import resolve`` to be the
   URL-resolving *function*, while Section 5 names ``resolve.py`` as a module.
   The public function wins at the package namespace; the submodule is internal
   and reached by internal aliased imports (``from . import resolve as _resolve``)
   or, in tests, via ``importlib.import_module("adaptiseq.resolve")``. Just a
   naming note for maintainers.

(Append further entries here as they arise during implementation.)

---

# Part 2 — Segmented engine (fixed concurrency)

## P2.1 Decoupling plan (`SegmentedDownloader`, fastbiodl_upgrade.py L63-777)

The class reaches into module globals and multiprocessing state. Before porting
it is made self-contained (spec §2). Mapping of every entanglement:

| Original (global / mp) | Replacement (injected, self-contained) |
|---|---|
| `download_process_status[self.process_id]` pause check | **pause token**: `pause.should_continue() -> bool`. Part 2 wires a constant "always run" (`AlwaysRun`); Part 3 swaps in the gradient gate. |
| `process_counter` (`mp.Value`) + `flush_counter` | **byte-counter callback** `on_bytes(n)`; default no-op. Part 2 uses it for a simple meter; Part 3 feeds the throughput meter. |
| `active_connections` (`mp.Value`) | the **per-host connection cap** in `engine/ratelimit.py` (acquire before opening a segment, release on close). |
| `available_space_bytes(download_dir)` in the hot loop; `reserve/release_disk_space` & friends | **single cheap free-space check** before a download starts (`shutil.disk_usage`), out of the hot loop. All reservation machinery discarded. |
| `download_dir` module global | constructor arg `outdir`; `local_path` is absolute. |
| `session` from caller | constructor arg (an `aiohttp.ClientSession`). |
| speed limiting (external) | **token-bucket** in `engine/ratelimit.py`, shared across a file's segments, honouring `-s/--speed` MB/s. |
| `converter.SRAConverter`, `config_fastbiodl`, `storage_config`, `get_nvme_device`, tmpfs, `ncbi_lookup`, `search.base_optimizer` | **not imported**. Conversion stays the explicit Part 1 `convert.py` step; URLs come from Part 1 `resolve.py`. |

Result: `engine/segmented.py` depends only on `aiohttp`, the stdlib, and our own
`engine/ratelimit.py`; `engine/ftp.py` adds `aioftp`. No `fastbiodl` globals, no
`mp`, no tmpfs (spec acceptance #9).

## P2.2 Boundary kept for Part 3

Concurrency in Part 2 is **fixed**: each file opens
`min(max_segments, max(1, size // segment_size))` segment connections, bounded by
the per-host cap. No optimizer, no `-j/--jobs`, no `--adaptive*`. The pause token
and byte-counter seams are the only hooks Part 3 will use.

## P2.3 Part 2 divergences and decisions (with reasons)

P2-a. **Default transport changed to `auto` (HTTPS-first); default protocol is no
   longer `ftp`.** Part 1 defaulted `-r` to `ftp`. Part 2 introduces a third
   protocol state, `auto` (the new default), so the segmented engine can prefer
   the HTTPS mirror per spec §5.1. An explicit `-r ftp` or `-r https` still forces
   the transport and is final. `--engine classic` treats `auto` as `ftp` (the plain
   URL form), so classic behaviour is unchanged. The Part 1 resolution
   tests pin an explicit protocol, so they are unaffected.

P2-b. **Same-host HTTPS upgrade only (ENA); GSA cross-host mirror not auto-swapped.**
   For an `ftp://H/path` URL under `auto`, the engine probes `https://H/path`
   (same host, same file — a transport change, not a URL/database change, allowed
   by §0). This is the clean ENA case (`ftp.sra.ebi.ac.uk` serves HTTPS on the
   same host). For GSA, the dedicated HTTPS mirror is a *different* host
   (`download.cncb.ac.cn` vs the `ftp://download.big.ac.cn` link), which would
   require a resolution change; Part 2 does **not** swap to it. GSA `ftp://` links
   therefore go: same-host-https probe → native segmented FTP → single → classic.
   Documented limitation; revisit if GSA throughput needs it.

P2-c. **Per-host cap / circuit-breaker state is per-fetch in Part 2.** The
   `HostGuard` is instantiated inside each `fetch()`'s event loop (asyncio
   primitives are loop-bound; Part 2 drives one `asyncio.run` per file through the
   sync seam). Since Part 2 downloads files sequentially, only one file's segments
   are ever in flight, so the per-file cap equals the across-run cap for the
   binding case (one large file). Part 3's single-loop worker pool will own one
   `HostGuard` for the whole run to coalesce the cap/breaker across files. The
   class is already written for that.

P2-d. **`-p/--parallel` is now an alias for `--max-segments`** on the segmented
   engine (with a printed note), per spec §7; it keeps its original `axel`
   meaning only on `--engine classic`.

P2-e. **Preflight refined to be transport-aware.** With the segmented engine,
   `axel` is no longer required (it is needed only by `--engine classic -p`), and
   integrity/convert tools are demanded only when the run will use them. It never
   demands a tool the run won't use (extends decision #4).

## P2.4 Transport-probe verdicts observed (live, this sandbox)

- `ftp.sra.ebi.ac.uk` (ENA): HTTPS mirror returns `206` with valid `Content-Range`
  on `Range: bytes=0-0` → verdict **segmented HTTPS**. Confirmed live: a 2.2 MB
  real fastq (`SRR1553469_1.fastq.gz`) downloaded in 4 ranged segments is
  byte-identical (md5) to `wget`.
- **Known EBI FTP constraint:** EBI restricts FTP `REST` and caps concurrent
  connections per IP — exactly the two features segmentation needs — which is why
  HTTPS-first is the right default for ENA. The native FTP path remains for hosts
  that do allow `REST` + concurrency (verified against a local `aioftp` server).
- Local `aioftp` server: `REST` + concurrency confirmed → **segmented FTP**,
  byte-identical. (EBI itself was not exercised over native FTP segmentation.)

## P2.5 Which paths were exercised live vs unit-only (honesty, spec §8)

- **Live:** ENA HTTPS range probe + multi-segment download byte-identical to wget;
  ENA metadata (Part 1 differential, still green on the segmented default).
- **Local server (real code paths, deterministic):** segmented HTTP byte-identity,
  mid-file resume, strict-206 → single-stream fallback, per-host cap, circuit
  breaker recovery; native segmented FTP byte-identity + REST/concurrency probe.
- **Unit only:** segment calculation, `.part.meta` bookkeeping, token bucket,
  `HostGuard` cap + breaker state machine, transport-selection decision order.
- **Not executed:** a full ~130 MB real ENA file (too large for the sandbox);
  native segmented FTP against EBI (EBI restricts `REST`, as noted).

---

# Part 3 — Adaptive concurrency, batch download, parallel resolution

## P3.1 Decouple-and-fix plan (gradient optimizer + fastbiodl wiring)

The optimizer controls the number of active **workers**, not connections (spec §0).
Each active worker downloads one file and opens its own size-derived segment
connections; the emergent connection total is clipped by the Part 2 per-host cap.
The optimizer only opens/closes worker slots.

Mapping fastbiodl's mp/tmpfs scaffolding to a single-process asyncio design:

| fastbiodl (mp / globals) | adaptiSeq (single-process asyncio) |
|---|---|
| `download_process_status[i] = 1 if i < params[0] else 0` (shared array) | one mutable `WorkerGate.active` integer; worker `i` runs iff `i < active`. The Part 2 pause token is `gate.token(i)` whose `should_continue()` is `i < active`. |
| pause → worker cancels in-flight segments, re-queues file | the segmented downloader already raises `CancelledError` when `should_continue()` is False and writes `.part.meta`; the worker re-queues the file. |
| `report_network_throughput` deque + CSV + `elapsed>1000` heuristic | `ThroughputMeter`: 1 Hz sampler fed by the Part 2 byte-counter callback into a rolling Mbps deque. No CSV side effects, no 1000 s heuristic. |
| `process_counters` (`mp.Value`) summed | one shared `on_bytes(n)` callback accumulating into the meter. |
| `download_probing` (sets status, sleeps 1, averages window, `score=thrpt/K**w`, returns `-score`) | `probe(w)` in `engine/optimize.py`: `gate.active=w`, settle 1 s, average meter over the remaining `--probe-window-1` s, `score=thrpt/(K**w)`, return `int(round(-score))`; `exit_signal` when done. |
| `run_download_optimizer` (initial window, then `gradient_opt_fast`, then keep probing) | `AdaptiveController.run()` coroutine: wait one window, run `gradient_opt_fast`, then hold final `w` until the queue drains. |
| `base_optimizer` (skopt/scipy) | **not implemented** (spec §1). Gradient path only; no skopt/scipy. |

## P3.2 Optimizer bookkeeping fixes (spec §2.1)

These are bug-fixes to the gradient-search algorithm:

1. **Cache keyed by worker count, not `abs(score)`.** Original
   `cache[abs(values[-1])] = ccs[-1]` collides when two worker counts yield the
   same |score|, corrupting `soft_limit = cache[max(cache.keys())]`. Fix: store
   `cache[worker_count] = score` and derive the best-seen worker count by best
   score, so `soft_limit` recovers the actual best worker count.
2. **Explicit, logged gradient fallback.** Original silently falls back to
   `gradient = 1` when `prev == 0`, which drives a full +step on a flat/zero probe.
   Fix: detect the degenerate case, log it at WARNING, and use `gradient = 0` (no
   move) rather than a silent unit step.
3. **Deliberate eviction (oldest, not newest).** Original `cache.popitem(last=True)`
   evicts the *freshest* observation. Fix: bound the cache and evict the
   **oldest** entry (`popitem(last=False)`), keeping recent observations.

## P3.3 Per-host cap is the binding constraint at `-j 20` (spec §2.2)

With `-j 20` and each worker opening up to `--max-segments` connections, the naive
emergent total to one host would be `20 × max_segments`. The always-on per-host cap
(`--max-conns-per-host`, default 8) clips this: for a single-host batch (e.g. an
all-ENA list hitting EBI), effective concurrency to that host is roughly
`max_conns_per_host / connections_per_file`, **not** 20×8. The optimizer raises
worker slots; the segmenter sets per-file connections; the cap is the hard wire
ceiling. Documented in README so `-j 20` is not misread as "160 connections to EBI."

## P3.4 Part 3 boundary

Adaptivity and batching change only *scheduling*, never which URL/bytes are
fetched. All Part 1/2 differential tests remain the load-bearing regression guarantee.
Single-process asyncio (one event loop, one `HostGuard`, one gate integer) is used
over a process pool to keep resume/log logic race-free (spec §3).

## P3.5 Gate at file-pickup boundaries, not mid-file (deliberate divergence)

The spec (§2) describes lowering `active_workers` as cancelling a worker's
in-flight segments and re-queuing the file. adaptiSeq instead gates at the
**file-pickup boundary**: an idle worker waits until its slot is active, then
downloads one file to completion; lowering `active` stops workers from *starting*
new files but lets in-flight files finish. Reason: cancelling and resuming
mid-file is the one place corruption can creep in for no real throughput benefit,
and a 2.2 MB file finishes in well under one probe window anyway. The controller
still governs how many files download concurrently (the meaningful control); the
throughput meter and trajectory are unchanged. Documented as a divergence from the
fastbiodl pause/re-queue mechanic.

## P3.6 Critical fix: per-host transport cache stored full URLs (also fixes Part 2)

While wiring the batch pool, the per-host transport-verdict cache in
`engine/seam.py` was found to cache the *effective URL* of the first file probed
on a host, so every subsequent file on that host downloaded the **first file's
bytes**. This corrupted paired-end runs (`_1`/`_2` share `ftp.sra.ebi.ac.uk`):
both files received `_2`'s content at `_2`'s size. This affected the Part 2
sequential seam too (the `SegmentedEngine` persists across a run's files). Fix:
the cache stores only the transport *kind* (a host-level property); the effective
URL is derived per file via `_eff_url(url, kind)`. Verified live: `SRR1553469`'s
`_1` and `_2` are each byte-identical to `wget`. Regression test added
(`test_transport_cache_derives_url_per_file`).

## P3.7 Two-phase batch integration (SRA/ENA), GSA sequential

`core.run` routes SRA/ENA downloads through the adaptive batch pool (phase A:
parallel resolve + worker pool), then runs the unchanged per-accession Part 1 loop
(phase B: integrity / convert / merge / logs) over the already-present files —
`download_with_resume` recognises a complete file and does not re-fetch, so phase
B is a no-op for batched files and only fills any the batch missed. GSA accessions
and the classic engine use the sequential path unchanged (GSA's `download_gsa`
keys "already downloaded" on `success.log`, which the batch does not write, so
batching GSA cleanly would need a resolution change — deferred, documented).
`-m` (metadata only) and `-a` (aspera) never use the batch path.

---

# Part 4 — segmented+adaptive as the true default, and the batch-USP benchmark

## P4.1 Default policy: never auto-fall-back to classic

Per the user's direction, **segmented + adaptive is the default** and the auto
transport selector **never** drops to the classic `wget`/`axel` engine. When a
host cannot serve ranges, the file degrades to *single-stream within the async
engine* (`http-single`/`ftp-single`), so it stays inside the adaptive batch pool —
still multi-worker across files, just one connection for that file. The classic
engine (`wget`/`axel`/`ascp`) is reachable **only** by explicitly choosing
`--engine classic`. Rationale: "segmentation impossible" must not collapse
cross-file concurrency to a single worker/single connection, and it must not
silently change transport family. Edge case: a non-ENA/GSA FTP-only host with no
`REST` and no HTTPS mirror will fail the file (recorded in `fail.log`) rather than
auto-using `wget`; such hosts need `--engine classic` chosen manually. Documented.

## P4.2 3-file runs: adaptiSeq is more robust than iseq

Real PRJNA916347 runs frequently have **three** fastq files (an orphan/barcode
`SRR.fastq.gz` plus `_1`/`_2`); ~40 of ~241 runs in that project are like this.
iseq mishandles them: its `downloadSRA` "paired but one link" branch greps all
three `.fastq.gz` matches and feeds `wget` a multiline URL, so the download fails
(verified live: stock iseq exits 1 on `SRR22904269`). adaptiSeq now resolves and
downloads **every** `.fastq.gz` part (in both `download_sra` and the batch
`resolve_sra_urls`), so the md5 check over all files passes (verified: 3 clean
files, `success.log` updated). This is a deliberate correctness improvement over
iseq on the 3-file case.

## P4.3 Benchmark method (batch USP)

The competitor set is **dedicated SRA fetchers** (stock `iseq`, `iseq -p 8`,
`Kingfisher -m ena-ftp`), not aria2c — adaptiSeq's edge is *parallel URL
resolution + batch concurrent download*, which those tools do sequentially
(one run resolved and downloaded at a time). Workload: a byte-bounded subset of
the many-files small list (PRJNA916347), 1-/2-file runs only so every tool
succeeds. Files are deleted between each method. To run stock iseq in the sandbox
(which lacks aspera), a **no-op `ascp` stub** is placed on `PATH` purely to pass
iseq's startup `CheckSoftware` gate; iseq's actual ENA path uses `wget`/`axel`, so
the stub is never invoked and the comparison stays fair. Results in BENCHMARK.md.

---

# Part 5 — fair byte benchmark, live progress, adaptive Aspera

## P5.1 Benchmark fairness by bytes + format
Different fetchers may pull different formats/sizes, so the batch harness records
**bytes, MB/s, and format** per method (not time alone). On the headline run all
tools fetched the same 89 MB of `.fastq.gz`, so MB/s is a fair apples-to-apples
metric. adaptiSeq leads; `iseq -p 8` (axel over EBI FTP) times out.

## P5.2 Adaptive vs fixed is within noise on small batches (honest)
Two runs flipped: run A `--adaptive` 16.9 s vs `--no-adaptive` 19.9 s; run B
`--adaptive` 20.4 s vs `--no-adaptive` 15.9 s. On a ~16–20 s job the controller has
only ~3 probe windows and its probing overhead can exceed its gain. We do **not**
claim adaptive beats fixed on small batches; its payoff needs a long sustained run
(not measurable in the sandbox). Robust across both runs: adaptiSeq beats iseq and
Kingfisher.

## P5.3 Adaptive Aspera — why a different controller
`ascp` cannot pause/resume mid-file, so the gradient controller (pause + re-queue)
is inapplicable. Aspera concurrency is gated only at file-pickup boundaries and
tuned by **additive-increase + efficiency hysteresis** (`hysteresis_search`):
baseline at 1 worker; each interval add one worker and keep it iff aggregate
throughput ≥ `--aspera-efficiency × (workers × baseline)`, else drop and hold. This
intentionally stops near the point where *cumulative* efficiency crosses the
threshold (it can overshoot the marginal knee by one worker — a deliberate, bounded
bias). Throughput is sampled from output-directory growth (`DirGrowthMeter`) since
ascp writes bytes out-of-process.

## P5.4 What was NOT exercised live (Aspera)
No `aspera-cli` in the sandbox and EBI restricts Aspera, so **real ascp transfers
were not run**. The controller logic, the directory meter, and the full pool are
validated on synthetic throughput curves and with a fake `ascp` (a function that
writes a file's bytes over time) end-to-end. The production `download_fn` is
`ClassicEngine.fetch_aspera`; the ENA resolution reuses the Part 1 resolver
(scheme stripped to the `host/path` form ascp expects). GSA Aspera (Huawei-wins)
stays on the sequential path.
