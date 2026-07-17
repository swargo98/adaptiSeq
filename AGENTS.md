# Repository Guidelines

> **Start here when onboarding:** read [HANDOFF.md](HANDOFF.md) for the architecture
> map and five-part build order, then [NOTES.md](NOTES.md) for the detailed
> decision log per part. [CHANGES_FROM_ISEQ.md](CHANGES_FROM_ISEQ.md) documents
> every deliberate divergence from the upstream `iseq` Bash tool.

## Project Structure & Module Organization

This repository is a Python package for `adaptiseq`. Core package code lives in
`adaptiseq/`; the CLI entry point is `adaptiseq/cli.py`, with engine
implementations under `adaptiseq/engine/`. Tests for the package live in
`tests/`. The standalone publication benchmark harness lives in `sysbench/` and
has its own tests in `sysbench/tests/`. User-facing documentation is under
`docs/`, benchmark scripts and input lists are under `bench/`, and package
metadata is defined in `pyproject.toml`.

## Architecture: Key Modules

| Module | Responsibility |
|---|---|
| `core.py` | Per-accession orchestration; two-phase batch/aspera wiring |
| `batch.py` | `BatchDownloader`, adaptive controller, parallel `resolve_all` |
| `resolve.py` | URL resolution — faithful ports of `downloadSRA`/`downloadGSA` |
| `metadata.py` | ENA filereport / SRA eutils / GSA CSV+XLSX (byte-identical to `iseq`) |
| `routing.py` | Database routing (GSA vs SRA/ENA/DDBJ/GEO) + `-e` merge guards |
| `integrity.py` | MD5 checks + `vdb-validate` retry policy (up to 3 → `fail.log`) |
| `aspera.py` | Adaptive Aspera pool — hysteresis controller (not gradient) |
| `errors.py` | Typed exception hierarchy; all subclass `AdaptiSeqError` |
| `options.py` | `Options` dataclass (all CLI flags) + `RunContext` |
| `preflight.py` | Needs-based tool checks; runs after `--help`/`--version` |

### Engine sub-package (`engine/`)

| Module | Responsibility |
|---|---|
| `seam.py` | `SegmentedEngine` — plugs into the Part 1 seam; same interface as `ClassicEngine` |
| `segmented.py` | Resumable HTTP(S)/FTP downloader (`aiohttp`/`aioftp`); `.part`/`.part.meta` bookkeeping |
| `ftp.py` | Native segmented FTP via `aioftp` (REST/RETR commands) |
| `gate.py` | `WorkerGate` (mutable active-worker count); `WorkerToken` (pause-token) |
| `optimize.py` | `gradient_opt_fast()` — minimises `-(throughput / K**workers)` |
| `ratelimit.py` | `TokenBucket` (aggregate cap) + `HostGuard` (per-host cap + circuit breaker) |
| `classic.py` | Legacy `wget`/`axel`/`ascp` engine; selected only with `--engine classic` |

`get_engine(options, ...)` returns `SegmentedEngine` by default.
**No auto-classic fallback** — segmentation-impossible degrades to single-stream
inside the adaptive pool.

## Public Python API

```python
from adaptiseq import fetch, resolve, get_metadata, FetchResult

rows   = get_metadata("SRR7706354")                      # list[dict]
urls   = resolve("SRR7706354", database="ena", gzip=True)  # list[str]
result = fetch("SRR7706354", outdir="data/", jobs=20, adaptive=True)
# result.success_ids, result.fail_ids, result.failed (bool)
```

Typed exceptions (all subclass `AdaptiSeqError`): `InvalidAccessionError`,
`MetadataError`, `DownloadError`, `IntegrityError`, `MergeError`,
`PreflightError`, `EngineUnavailableError`. Never `sys.exit` from the library.

**Module-name shadowing:** `adaptiseq.resolve` is the **public function**, which
shadows the `resolve` submodule. Reach the submodule via
`importlib.import_module("adaptiseq.resolve")`.

## CLI Defaults

`--engine segmented`, `--jobs 20`, `--segment-size 512MB`, `--max-conns 8`,
`--probe-window 5`, `--cc-penalty 1.01`, `--meta-jobs 3`.

## Async & Concurrency Design

Single-process asyncio (one loop, one `HostGuard`, one gate integer) — chosen
over multiprocessing for race-free resume/log logic. Workers are gated at the
file-pickup boundary; in-flight files finish instead of being cancelled mid-file.

## Build, Test, and Development Commands

Run commands from the repository root.

```bash
pip install -e '.[test]'        # editable install plus pytest/openpyxl/psutil
python -m pytest -q             # offline package test suite
python -m pytest sysbench/tests -q  # sysbench unit tests
ADAPTISEQ_NO_NETWORK=1 python -m pytest -q  # force live tests to skip
python -m build                 # build sdist and wheel
python -m twine check dist/*    # validate distribution metadata
adaptiseq --version             # verify CLI entry point
```

Use `conda env create -f iSeq.yml` when you need the external bioinformatics
tools listed in [docs/installation.md](docs/installation.md).

## Coding Style & Naming Conventions

Use Python 3.10+ syntax and keep modules typed where practical; the package ships
`py.typed`. Follow the existing style: four-space indentation, `snake_case`
functions and modules, `PascalCase` classes, and explicit error types from
`adaptiseq/errors.py` for user-facing failures. Keep shell-outs and network
preflight behavior centralized in the existing helper modules instead of adding
one-off subprocess calls.

## Testing Guidelines

Tests use `pytest`. Name test files `test_*.py` and keep fixtures or local server
helpers in `tests/conftest.py`, `tests/harness.py`, or `tests/servers.py`.
`tests/servers.py` provides a local `RangeServer` (HTTP) and `aioftp` server for
offline engine tests.

| Env var | Effect |
|---|---|
| `ADAPTISEQ_NO_NETWORK=1` | Force-skips all live network tests |
| `ADAPTISEQ_LIVE_ASPERA=1` | Opt-in for real ENA `ascp` tests |
| `NCBI_API_KEY=<key>` | Raises NCBI rate limit from 3 rps → 10 rps |

Prefer offline fixture or local-server tests for CI. `test_differential.py` and
`test_metadata_parse.py` use frozen golden fixtures for byte-for-byte parity
guarantees against `iseq` — these tests **never skip**. Add focused regression
tests for CLI behavior, accession resolution, download engines, and
integrity/log handling when touching those areas.

## Known Pitfalls

- **Transport cache key is `kind`, not URL** — caching full URLs caused
  paired-end corruption (fixed in Part 3; see `NOTES.md §P3.6`).
- **Rate limiters live in two places**: metadata fetches go through `net.py`;
  parallel resolution goes through `batch.py`. Both consult `ratelimits.py`.
- **3-file runs** (orphan/barcode + `_1` + `_2`) — adaptiSeq downloads all
  parts; stock `iseq` fails them. Do not regress this.
- **Parity constraint**: resolution, metadata, integrity, logs, and merge must
  produce byte-identical results to `iseq`. Engine and concurrency are the only
  permitted divergences.

## Commit & Pull Request Guidelines

Recent history uses short Conventional Commit-style prefixes such as `feat:`,
`docs:`, and `fix:`. Keep commits focused and imperative, for example
`fix: handle missing segmented part files cleanly`. Pull requests should describe
the behavior change, list tests run, mention network-dependent coverage, and link
related issues. Include screenshots only for docs or asset changes where visual
output matters.

## Security & Configuration Tips

Do not commit downloaded sequencing data, credentials, or benchmark run outputs.
Keep generated artifacts in ignored output directories such as `sysbench/runs/`.
When adding external tools, document when they are required and preserve the
needs-based preflight behavior described in the installation docs.
