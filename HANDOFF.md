# adaptiSeq / adaptiFetch — project handoff

A single-file orientation so a fresh chat can continue with minimal context. Read
this, then `NOTES.md` (the authoritative divergence/decision log) and the per-part
docs as needed.

- **Repo:** `/home/ubuntu/adaptiSeq` — git remote `origin`
  `https://github.com/swargo98/adaptiFetch.git`, branch `main`. **All work is
  committed and pushed.**
- **Status:** Parts 1–5 complete. **131 passed, 1 skipped** (the 1 skip is a live
  cross-check that needs stock `iseq` installed; it is intentional).
- **Version string:** `adaptiSeq 0.1.0`. Console entry point: `adaptiseq`.
- **Python:** 3.10 in the sandbox; package targets >=3.8.

## What this project is

A faithful, tested, importable **Python reimplementation of the `iseq` Bash tool**
(BioOmics/iSeq) for downloading public sequencing data + metadata from GSA / SRA /
ENA / DDBJ / GEO — extended with a segmented resumable engine, an adaptive
concurrency controller, batch/parallel download, and adaptive Aspera. The original
Bash lives (gitignored) at `iSeq-main/bin/iseq` (1120 lines) — **the source of
truth for parity**. The build was driven by three spec files in the repo root:
`adaptiSeq_part1_python_port.md`, `..._part2_segmented_engine.md`,
`..._part3_adaptive_and_batch.md`. Parts 4 and 5 were user-directed follow-ups with
plans in `PART4_PLAN.md` / `PART5_PLAN.md`.

**Load-bearing principle:** the engine and scheduler change only *how* bytes arrive
and *when* files are scheduled — **never which bytes**. Resolution, metadata,
integrity, logs, and merge stay byte-for-byte faithful to `iseq`. The Part 1
differential tests are the parity guarantee and still pass.

## The five parts (what each added)

- **Part 1 — faithful port (classic engine).** `iseq` ported to a package on the
  classic `wget`/`axel`/`ascp` path, no behaviour change. Differential test harness
  with golden fixtures proves parity. No speed claim.
- **Part 2 — segmented engine.** Resumable, range-based HTTP(S)/FTP downloader
  (`aiohttp`/`aioftp`) behind the single download seam, now the default
  (`--engine segmented`); per-host connection cap + reactive circuit breaker;
  HTTPS-first transport selection. Fixed concurrency.
- **Part 3 — adaptive + batch.** Gradient controller (ported from `search.py`,
  bookkeeping bugs fixed) tunes the active-*worker* count; batch parallel download
  pool (`-j/--jobs`, default 20); parallel metadata resolution (`--meta-jobs`) with
  per-endpoint rate limits (ENA/NCBI/GSA; NCBI 3 rps / 10 with `NCBI_API_KEY`).
- **Part 4 — true default + batch-USP benchmark.** Default is segmented+adaptive;
  auto transport **never** falls back to classic (degrades to single-stream inside
  the adaptive pool); classic is opt-in only. Benchmarked vs **iseq / Kingfisher**
  (the real competitors). Also fixed 3-file runs that iseq mishandles.
- **Part 5 — fair benchmark, progress bar, adaptive Aspera.** Benchmark reports
  bytes+MB/s+format. Live file-level progress bar. Adaptive parallel Aspera via an
  additive-increase + efficiency-hysteresis controller (`--aspera-efficiency`,
  default 0.70) — since `ascp` can't pause/resume mid-file.

## Architecture map (where things live)

```
adaptiseq/
  __init__.py     # public API: fetch(), resolve(), get_metadata(); FetchResult
  cli.py          # argparse mirroring iseq + all Part 2-5 flags; needs-based preflight
  core.py         # per-accession process loop + two-phase batch/aspera wiring (run())
  accession.py    # validateQuery regexes (verbatim) + GEO resolution + is_gsa()
  routing.py      # GSA-vs-SRA routing + -e merge guards
  metadata.py     # ENA filereport / SRA eutils+sra-db-be / GSA CSV+XLSX (via wget)
  resolve.py      # downloadSRA/downloadGSA ports + resolve_sra_urls/resolve_gsa_urls
  integrity.py    # checkSRA/checkGSA md5 + vdb-validate retry policy
  convert.py      # fasterq-dump + pigz ; merge.py: mergeSRArun/mergeGSArun
  logs.py         # success.log / fail.log ; preflight.py: CheckSoftware port
  net.py          # wget wrappers (metadata bytes; consults ratelimits)
  ratelimits.py   # per-endpoint resolution rate limiters (ENA/NCBI/GSA)
  options.py      # Options dataclass (all flags) + RunContext
  console.py      # exact ANSI Note/Error style + Reporter (Ansi/Null/List)
  progress.py     # Part 5 live file-level progress bar
  batch.py        # Part 3 batch pool + AdaptiveController + resolve_all (parallel)
  aspera.py       # Part 5 adaptive Aspera: hysteresis_search + AsperaBatchDownloader
  engine/
    classic.py    # wget/axel + ascp (Part 1 engine); get_engine() factory
    segmented.py  # Part 2 segmented HTTP downloader + shared .part.meta helpers
    ftp.py        # Part 2 native segmented FTP (aioftp, REST/RETR)
    seam.py       # SegmentedEngine: transport selection + fetch/fetch_async seam
    ratelimit.py  # Part 2 TokenBucket + HostGuard (per-host cap + circuit breaker)
    optimize.py   # Part 3 gradient_opt_fast (with §2.1 fixes)
    throughput.py # Part 3 ThroughputMeter + Part 5 DirGrowthMeter
    gate.py       # Part 3 WorkerGate + WorkerToken (the integer the optimizer drives)
```

**The seam:** every sequence-data byte is fetched through one interface —
`engine.fetch(url, save_path)` (sync, Part 2) or `engine.fetch_async(...)` (Part 3
batch, shares one event loop). `get_engine(options, ...)` returns `SegmentedEngine`
by default, `ClassicEngine` only for `--engine classic`.

**Two-phase batch (core.run):** Phase A resolves SRA/ENA accessions in parallel and
downloads via the adaptive pool (or aspera pool); Phase B is the unchanged
per-accession Part 1 loop (integrity/convert/merge/logs) over already-present files
(`download_with_resume` recognises complete files, so Phase B is a no-op for them).
GSA, `--engine classic`, `-m`, and `-a`-for-GSA stay sequential.

## CLI flags (defaults)

`-i/--input`, `-m/--metadata`, `-g/--gzip`, `-q/--fastq`, `-t/--threads 8`,
`-e/--merge [ex|sa|st]`, `-d/--database [ena|sra]` (auto), `-a/--aspera`,
`-s/--speed 1000`, `-k/--skip-md5`, `-r/--protocol [ftp|https]` (auto, HTTPS-first),
`-Q/--quiet`, `-o/--output`, `-p/--parallel` (alias for `--max-segments` on
segmented), `--engine [segmented|classic]` (**segmented**),
`--segment-size 512` (MB), `--max-segments 8`, `--max-conns-per-host 8`,
`-j/--jobs 20`, `--adaptive/--no-adaptive` (**adaptive**), `--probe-window 5`,
`--cc-penalty 1.01`, `--meta-jobs 3`, `--aspera-efficiency 0.70`, `-h`, `-v`.

## Library API (Section 6 — no sys.exit, no colour, typed exceptions)

```python
from adaptiseq import fetch, resolve, get_metadata
recs   = get_metadata("SRR7706354")             # parsed metadata rows
urls   = resolve("SRR7706354", database="ena")  # resolved URLs (no download)
result = fetch("SRR1553469", outdir="data/", gzip=True, adaptive=True)
# NOTE: `adaptiseq.resolve` (the attribute) is the public FUNCTION and shadows the
# resolve.py submodule — reach the submodule via importlib.import_module.
```

## Key decisions & divergences (full list in NOTES.md)

- Metadata bytes pulled by **`wget`** (same commands as iseq) → byte-identical.
- **Per-host transport cache stores only the transport *kind*, not the URL** — a
  critical fix; caching the URL made every file on a host download the first
  file's bytes (corrupted paired-end). (NOTES §P3.6)
- **No auto-classic fallback** (Part 5/4): segmentation-impossible degrades to
  single-stream inside the adaptive pool; classic is manual-only. (NOTES §P4.1)
- **3-file runs** (orphan/barcode + `_1` + `_2`): adaptiSeq downloads all parts;
  stock iseq fails them. (NOTES §P4.2)
- **Worker gate is at file-pickup boundaries**, not mid-file cancel/resume
  (avoids corruption; ascp can't resume anyway). (NOTES §P3.5)
- Gradient optimizer **bookkeeping bugs fixed** (cache by worker count, logged
  degenerate-gradient fallback, evict-oldest). (NOTES §P3.2)
- **Adaptive Aspera** uses a different controller (hysteresis), not the gradient
  one, because ascp can't pause/resume. (NOTES §P5.3)

## Tests & benchmark

- Run all: `python3 -m pytest` (from repo root). 131 pass, 1 skip.
- Offline-safe: most tests use local HTTP (`tests/servers.py`) / `aioftp` servers,
  synthetic traces, and golden fixtures (`tests/fixtures/`). Live tests skip when
  offline (`ADAPTISEQ_NO_NETWORK=1` forces skip).
- Differential parity harness: `tests/test_differential.py` (fixture mode never
  skips; live mode + stock-iseq cross-check skip gracefully).
- Batch USP benchmark: `bash bench/benchmark_batch.sh` (uses
  `bench/subset_small.txt`; results in `bench/results_batch.tsv`).
  **Latest result:** on 35 ENA fastq.gz files (~89 MB, identical bytes/format for
  all tools), MB/s: **adaptiseq 5.6 / 4.4 > Kingfisher 4.0 > iseq 2.0**;
  `iseq -p 8` (axel on EBI FTP) **times out**. adaptiSeq wins the batch workload.

## Honest limitations (do not overstate)

1. **Adaptive vs fixed is within noise on small batches** — two runs flipped which
   won. No claim that adaptive beats fixed on short jobs; its payoff needs a long
   sustained run (not measurable in the sandbox).
2. **Real ENA Aspera was never run** — no `aspera-cli` in the sandbox and EBI
   restricts Aspera. The hysteresis controller, `DirGrowthMeter`, and pool are
   tested with synthetic curves + a fake `ascp` only.
3. **Medium/large benchmark lists (49–55 GB each)** were too big to download
   repeatedly; only the many-small-files "small" list was benchmarked.
4. Full ~130 MB real ENA files and native segmented FTP against EBI were not run
   (EBI restricts FTP REST → HTTPS-first is the design response).

## Environment notes (sandbox)

- Installed: `aria2c`, `wget`, `pigz`, `curl`, `axel`, `srapath`/`vdb-validate`
  (apt `sra-toolkit`), `kingfisher` (pip), `numpy`, `aiohttp`, `aioftp`, `openpyxl`.
  **Missing:** real `aspera-cli` (a no-op `ascp` **stub** lives at
  `~/.local/bin/ascp` purely so stock `iseq` passes its startup check during
  benchmarks — remove it for real Aspera).
- `pip install -e .` works; deps: `aiohttp`, `aioftp`, `numpy`. Conda env:
  `iSeq.yml`.
- Uploaded benchmark lists were at `/home/ubuntu/.claude/uploads/<id>/...` (small=
  PRJNA916347 243 runs, medium=PRJNA353374 12 runs, large=PRJNA251383 4 runs).

## Possible next steps (not started)

- Benchmark the medium/large (large-file) lists to test the segmented engine's
  per-file speedup and give the adaptive controller a long run to prove itself.
- Real Aspera validation once `aspera-cli` + a key are available.
- GSA aspera through the adaptive pool (currently sequential; Huawei-wins rule).
- Package/publish (PyPI/bioconda); CI for the offline suite.

## Doc index

`NOTES.md` (decisions/divergences, authoritative) · `CHANGES_FROM_ISEQ.md` ·
`BENCHMARK.md` · `README.md` · `PART4_PLAN.md` · `PART5_PLAN.md` · the three
`adaptiSeq_part*.md` specs · `iSeq-main/` (reference Bash + README, gitignored).
