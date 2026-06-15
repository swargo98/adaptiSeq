# adaptiSeq

**adaptiSeq** is a fast, importable Python tool for fetching public sequencing data
and metadata from **GSA, SRA, ENA, DDBJ, and GEO**. It takes any of the standard
accession types — Project / Study / BioSample / Sample / Experiment / Run, plus
GEO `GSE`/`GSM` — resolves them across databases, downloads the sequence files with a
**segmented, resumable, self-tuning engine**, verifies integrity, and (optionally)
converts and merges FASTQ.

It is built for the workload that real pipelines actually have: **lists of
accessions**, downloaded in parallel, from a script or notebook — not one accession
at a time from the shell.

## What makes it different

- **A real Python API.** `fetch`, `resolve`, and `get_metadata` return values and
  raise typed exceptions — no `sys.exit`, no colour codes, no shelling out. You can
  resolve URLs, pull metadata, or download from inside your own Python code.
- **Batch parallel download.** Give it a file of accessions (or any run with several
  files) and it downloads through an asyncio worker pool instead of sequentially.
- **Adaptive worker count.** A runtime controller tunes *how many* downloads run at
  once by measuring achieved throughput and backing off when extra workers stop
  paying for themselves — so you get good throughput without hand-tuning or
  hammering the server.
- **Parallel metadata resolution.** Accession → URL resolution runs concurrently
  across the databases, bounded by polite per-endpoint rate limits, and streams
  resolved files into the download queue so transfer overlaps resolution.
- **Segmented, resumable transfers.** Each file is fetched in multiple byte-range
  connections with atomic `.part`/`.part.meta` resume; interrupt and rerun to
  continue, not restart.
- **Adaptive parallel Aspera.** With `-a`, downloads go through a parallel `ascp`
  pool whose concurrency is tuned by an efficiency-hysteresis controller.

The first four are the core of the project and are not offered by the common
single-shot downloaders. Everything else (integrity policy, FASTQ conversion/merge,
multi-database routing) is there so adaptiSeq is a complete drop-in for an
accession-to-FASTQ workflow.

## Installation

```bash
pip install adaptiseq           # once published to PyPI
pip install adaptiseq[xlsx]     # + openpyxl, for parsing GSA project XLSX

# from a checkout (development install):
pip install -e .
pip install -e '.[test]'        # + pytest, to run the suite
```

Runtime Python dependencies: **`aiohttp`, `aioftp`, `numpy`** (`openpyxl` is an
optional extra, `[xlsx]`, for parsing GSA project XLSX in the Python API). External
command-line tools used at run time: `wget` (metadata/discovery), `sra-tools`
(`srapath`, `fasterq-dump`, `vdb-validate`), `pigz`, `md5sum`, and — only for `-a` —
a real IBM `ascp`. `axel` is used by the opt-in classic engine.

## Quick start

Command line:

```bash
adaptiseq -i SRR7706354 -m              # metadata only -> SRR7706354.metadata.tsv
adaptiseq -i SRR7706354 -g              # download direct .fastq.gz where available
adaptiseq -i accessions.txt -g          # batch: mixed SRA/GSA/ENA list, in parallel
adaptiseq -i SRX003906 -g -e ex         # merge an Experiment's runs
adaptiseq -i CRR311377                  # GSA run -> .metadata.csv + CRA*.xlsx + data
```

Python:

```python
from adaptiseq import fetch, resolve, get_metadata

records = get_metadata("SRR7706354")                 # parsed metadata rows (list[dict])
urls    = resolve("SRR7706354", database="ena")      # resolved download URLs (no download)
result  = fetch("accessions.txt", outdir="data/",    # batch download + verify
                gzip=True, jobs=20, adaptive=True)
print(result.success_ids, result.fail_ids, result.failed)
```

The API functions never call `sys.exit` and never print colour codes; they raise the
typed exceptions in `adaptiseq.errors` (`InvalidAccessionError`, `MetadataError`,
`DownloadError`, `IntegrityError`, `MergeError`, `PreflightError`,
`EngineUnavailableError`, all subclassing `AdaptiSeqError`). `FetchResult` carries
`accession`, `outdir`, `failed` (bool), `success_ids`, and `fail_ids`.

> Note: `adaptiseq.resolve` (the package attribute) is the public *function*; the
> internal `resolve.py` submodule is reached via `importlib.import_module`.

## Command-line reference

```
adaptiseq -i accession [options]
```

| Flag | Meaning |
|------|---------|
| `-i, --input [text\|file]` | Single accession, or a file with one accession per line (batch). |
| `-m, --metadata` | Fetch metadata only; no sequence download. |
| `-g, --gzip` | Prefer direct `.fastq.gz`; fall back to `.sra` then convert. |
| `-q, --fastq` | Convert `.sra` to FASTQ with `fasterq-dump`. |
| `-t, --threads int` | Threads for `fasterq-dump`/`pigz` (default 8). |
| `-e, --merge [ex\|sa\|st]` | Merge at Experiment / Sample / Study level. |
| `-d, --database [ena\|sra]` | Force database (default: auto-detect). |
| `-a, --aspera` | Download via a parallel `ascp` pool (ENA/GSA only). |
| `-s, --speed int` | Speed cap in MB/s (default 1000). |
| `-k, --skip-md5` | Skip the integrity check. |
| `-r, --protocol [ftp\|https]` | ENA protocol. Default `auto` = HTTPS-first transport selection. |
| `-Q, --quiet` | Suppress progress output. |
| `-o, --output text` | Output directory (created if missing). |
| `--engine [segmented\|classic]` | Download engine. **Default `segmented`.** `classic` (`wget`/`axel`/`ascp`) is opt-in. |
| `-j, --jobs int` | Max batch worker-pool size (default 20). With `--adaptive`, the controller picks how many are active. |
| `--adaptive` / `--no-adaptive` | Adaptive worker-count control (default: on). `--no-adaptive` runs all `-j` workers with no probing. |
| `--probe-window int` | Adaptive probe window in seconds (default 5). |
| `--cc-penalty float` | Worker-cost penalty `K` in `score = throughput / K**workers` (default 1.01). |
| `--meta-jobs int` | Parallelism for metadata/URL resolution (default 3), bounded by per-endpoint rate limits. |
| `-p, --parallel int` | On `segmented`, alias for `--max-segments`; on `classic`, the `axel` connection count. |
| `--segment-size int` | Segmented engine: target segment size in MB (default 512). |
| `--max-segments int` | Segmented engine: max connections per file (default 8). |
| `--max-conns-per-host int` | Global cap on concurrent connections to any one host (default 8). |
| `--aspera-efficiency float` | Keep an added `ascp` worker only if throughput ≥ this fraction of `workers × single-worker baseline` (default 0.70). |
| `-h, --help` / `-v, --version` | Help / version (`adaptiSeq 0.1.0`). |

During a non-quiet batch download in a terminal, adaptiSeq shows a live file-level
progress bar with files done/total, the instantaneous (last-second) throughput the
controller probes on, and the active worker count. It is silent under `-Q` and when
output is not a TTY.

## The download engine

By default adaptiSeq downloads each file in multiple byte-range segments and resumes
interrupted transfers:

- **Per-file concurrency from size:** `min(--max-segments, max(1, size //
  --segment-size))` connections; strict HTTP `206`, written at the correct offset
  via `os.pwrite`, with atomic `.part` + `.part.meta` resume. Hosts that cannot serve
  ranges degrade to a single stream — never a truncated or zero-byte file.
- **Native segmented FTP** (`REST`/`RETR`) where the host allows it.
- **Transport selection (`auto`, default):** prefer the range-capable **HTTPS**
  mirror (confirmed by a cheap per-host probe), then native segmented FTP, then a
  single stream. `-r https` / `-r ftp` force the choice. The default path never
  auto-falls-back to the classic engine; `--engine classic` is a manual opt-in.
- **Connection etiquette:** a global per-host connection cap
  (`--max-conns-per-host`) and a reactive circuit breaker that backs off a host
  returning `429`/`503` or refusing connections, then recovers.
- **Speed cap:** `-s/--speed` MB/s via a shared token-bucket limiter.

### Adaptive batch download

For an accession list — or any run with multiple files — accessions are resolved in
parallel and files download through a worker pool whose **active** size is tuned at
runtime:

- **The controller manages *workers*, not raw connections.** It opens/closes worker
  slots between 1 and `-j/--jobs`; each active worker downloads one file with that
  file's own size-derived segments. Total connections in flight is emergent and
  clipped by the per-host cap.
- **Worker-cost penalty `K` (`--cc-penalty`, default 1.01).** The controller scores a
  worker count `w` by `throughput / K**w`, biasing toward fewer workers unless extra
  ones genuinely pay off — pure throughput maximization would peg workers at `-j` and
  hammer the server.
- **`--no-adaptive`** runs all `-j` workers with no probing.

Per-file semantics are preserved end to end: skip if already in `success.log`, MD5
(or `vdb-validate`) check, retry up to 3 times then record in `fail.log`, continue
past failures, non-zero exit on any failure. The controller's chosen worker
trajectory is logged. See [BENCHMARK.md](BENCHMARK.md) for honest measurements.

### Parallel metadata resolution

`--meta-jobs` (default 3) runs the multi-database, preference-ordered resolver
(ENA-first with SRA fallback; GSA; GEO indirection) for many accessions at once and
streams resolved files into the download queue, so downloading overlaps resolution.
Request rates are bounded by **per-endpoint** limiters (ENA / NCBI / GSA), not by
pool size; NCBI E-utilities is throttled to 3 req/s without a key and 10 with one
(`NCBI_API_KEY` / `NCBI_EMAIL` from the environment).

## Adaptive Aspera (`-a`)

`ascp` transfers cannot be paused/resumed mid-file, so the batch controller (which
pauses and re-queues) does not apply. With `-a`, adaptiSeq runs a parallel `ascp`
pool gated at **file-pickup boundaries**, tuned by an **additive-increase +
efficiency-hysteresis** controller: measure per-worker throughput at one worker
(baseline); each interval tentatively add a worker and keep it only if aggregate
throughput reaches at least `--aspera-efficiency` (default 0.70) of
`workers × baseline`, otherwise drop it and hold (no flapping). Throughput for
`ascp` (whose bytes are written out-of-process) is measured by sampling
output-directory growth.

Validated against the **real ENA Aspera** endpoint with a genuine IBM `ascp`:
single-file and multi-file batches transfer and pass md5, and the controller
correctly converges (e.g. it backs off to a single session when the endpoint
throttles a second concurrent `ascp`). See [BENCHMARK.md](BENCHMARK.md) for the
measured trajectory. Aspera is **opt-in** (`-a`) and supports **ENA/GSA only**.

## Supported accessions, databases, and output

Accepts Project (`PRJEB`/`PRJNA`/`PRJDB`/`PRJC`), Study (`ERP`/`DRP`/`SRP`/`CRA`),
BioSample (`SAMD`/`SAME`/`SAMN`/`SAMC`), Sample (`ERS`/`DRS`/`SRS`), Experiment
(`ERX`/`DRX`/`SRX`/`CRX`), Run (`ERR`/`DRR`/`SRR`/`CRR`), and GEO (`GSE`/`GSM`)
identifiers across **GSA, SRA, ENA, DDBJ, and GEO**.

Output, per accession:
- **SRA/ENA/DDBJ/GEO:** sequence files, `${accession}.metadata.tsv`, `success.log`,
  `fail.log`.
- **GSA:** sequence files (mostly `.gz`), `${accession}.metadata.csv`,
  `${CRA}.metadata.xlsx`, `success.log`, `fail.log`.

## Known limitations

- **GSA / NGDC from outside China.** GSA data is hosted by NGDC (CNCB, Beijing).
  Plain HTTPS/FTP works but can be **slow and intermittent** across the border
  (observed ~0.3 MB/s with dropped connections from a US host). NGDC's
  **UDP-accelerated transport** — both its `edgeturbo` client and GSA Aspera — does
  not establish from such hosts (the accelerator's UDP session stalls at 0%). On
  GSA, adaptiSeq therefore uses ordinary HTTPS/FTP; run from a network with good
  NGDC connectivity for high-speed GSA transfers. (ENA Aspera, by contrast, works.)
- **Raw single-file speed vs. a tuned generic downloader.** adaptiSeq's edge is the
  batch + adaptive + metadata-integrated workflow and the Python API, not beating a
  hand-tuned `aria2c -x16` on one large file. See [BENCHMARK.md](BENCHMARK.md).
- **Adaptive payoff needs a sustained run.** On tiny batches the adaptive controller
  has too few probe windows to matter; its benefit shows on longer multi-file jobs.

## Testing

```bash
pip install -e ".[test]"
pytest                          # unit + parity (offline) + live tests
ADAPTISEQ_NO_NETWORK=1 pytest   # force offline; live/canary tests skip
```

Offline parity tests diff parsing/resolution against frozen golden fixtures
(`tests/fixtures/`) and never skip, so they guard CI without network access; live
tests fetch real metadata/data and skip gracefully when offline. An API-drift canary
(`tests/test_api_drift.py`) flags when an upstream API moves rather than blaming
adaptiSeq. Real-Aspera and other network-heavy checks are opt-in (e.g.
`ADAPTISEQ_LIVE_ASPERA=1 pytest tests/test_aspera_live.py`).

## Project layout

```
adaptiseq/
  __init__.py     # public API: fetch / resolve / get_metadata + FetchResult
  cli.py          # argparse + dispatch
  accession.py    # accession validation regexes + GEO resolution
  routing.py      # GSA vs SRA/ENA routing; merge guards
  metadata.py     # ENA filereport / SRA eutils / GSA CSV+XLSX
  resolve.py      # per-run URL resolution
  engine/
    segmented.py  # segmented HTTP(S) downloader (range, .part resume)
    ftp.py        # native segmented FTP (REST/RETR via aioftp)
    seam.py       # transport selection (the single fetch seam)
    classic.py    # opt-in wget/axel + ascp engine
    ratelimit.py  # token-bucket limiter, per-host cap, circuit breaker
    optimize.py   # adaptive worker-count controller
    throughput.py # throughput / directory-growth meters
    gate.py       # worker gate
  batch.py        # batch pool + adaptive controller + parallel resolution
  aspera.py       # adaptive parallel ascp pool (hysteresis controller)
  ratelimits.py   # per-endpoint resolution rate limiters (ENA/NCBI/GSA)
  convert.py      # fasterq-dump + pigz
  integrity.py    # vdb-validate + md5 checks
  merge.py        # FASTQ merge
  preflight.py    # external-tool checks
  logs.py         # success.log / fail.log
  console.py      # message style + Reporter
  net.py          # wget wrappers (metadata/discovery I/O)
  options.py      # Options / RunContext
  errors.py       # typed exceptions
  core.py         # per-accession + batch process loop
```

A standalone publication benchmark (per-second CPU/memory/I/O across the four
download phases for several tools) lives in `sysbench/` and is **not** part of the
installable package.

## License & attribution

MIT. adaptiSeq's accession-to-FASTQ behaviour is compatible with
[BioOmics/iSeq](https://github.com/BioOmics/iSeq); if you use it in published work,
please also cite the original iSeq paper (Chao *et al.*, *Bioinformatics*, 2024).
Compatibility notes and deliberate divergences are documented in
[`NOTES.md`](NOTES.md) and [`CHANGES_FROM_ISEQ.md`](CHANGES_FROM_ISEQ.md).
