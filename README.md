# adaptiSeq

**adaptiSeq** is a tested, importable Python reimplementation of the
[`iseq`](https://github.com/BioOmics/iSeq) Bash tool for fetching public
sequencing data and metadata from **GSA, SRA, ENA, DDBJ, and GEO**.

> **Parts 1 and 2 are complete (Part 3 pending).**
> - **Part 1** is a *behaviour-preserving* port of `iseq` on the classic
>   `wget`/`axel`/`ascp` path (no new engine, no speed claim).
> - **Part 2** adds a **segmented, resumable HTTP(S)/FTP download engine** as a
>   drop-in replacement at the single download seam, now the default
>   (`--engine segmented`), with fixed (non-adaptive) concurrency, a per-host
>   connection cap, a reactive circuit breaker, and HTTPS-first transport
>   selection. The engine changes only *how* bytes arrive, never *which* bytes:
>   resolution, metadata, integrity, logs, and merge are untouched and all Part 1
>   differential tests still pass on the segmented default.
> - **Part 3** (pending) adds the gradient-adaptive concurrency controller,
>   batch/parallel download, parallel metadata resolution, and the benchmark.

## Why port a working Bash script? (design intent)

The load-bearing justification for Part 1 is **maintainability and an importable
library API**, *not* performance. The original `iseq` is a single 1,100-line Bash
script: it cannot be unit-tested, imported, or reused from a Python pipeline, and
its URL-resolution / retry / merge logic is entangled with shell control flow.
adaptiSeq fixes that:

- a real package with focused modules and a clean **engine seam** (the single
  place bytes are fetched), so Parts 2 and 3 can swap the download engine without
  touching resolution, integrity, logging, or merge;
- a small, documented, **importable API** (`fetch`, `resolve`, `get_metadata`)
  that returns values and raises typed exceptions — no `sys.exit`, no colour
  codes — so downstream Python can use adaptiSeq without shelling out;
- a **differential test harness** with golden fixtures that proves parity with
  `iseq` rather than asserting it.

Part 1 deliberately makes **no speed claim**. Speed is the concern of Parts 2–3,
and even there it is to be *proven*, not asserted.

## Parity with `iseq`

adaptiSeq accepts the same accessions, resolves the same download URLs, fetches
the same metadata from the same endpoints into the same files, downloads with the
same classic tools, verifies integrity with the same policy, writes the same
`success.log`/`fail.log`, and performs the same FASTQ conversion and merge. A user
who replaces `iseq` with `adaptiseq` in Part 1 should observe no difference except
the program name and version string.

Metadata files are byte-for-byte identical because adaptiSeq fetches them with the
same `wget` invocations `iseq` uses. The handful of *deliberate* divergences (help
works without the full tool set, retry counter resets per Run, a corrected Bash
`$$` quirk, etc.) are each documented with their rationale in
[`NOTES.md`](NOTES.md) and summarised in
[`CHANGES_FROM_ISEQ.md`](CHANGES_FROM_ISEQ.md).

## Installation

From source (editable):

```bash
pip install -e .
```

Or build the conda environment with the external tools and Python deps:

```bash
conda env create -f iSeq-main/iSeq.yml   # provides wget, axel, pigz, aspera-cli, sra-tools, python
pip install -e .
```

Part 1 adds only light Python dependencies (none required at runtime; `openpyxl`
is an optional extra for parsing GSA XLSX in the library API). The external tools
(`wget`, `axel`, `pigz`, `ascp`, `sra-tools`, `md5sum`) are the same ones `iseq`
requires.

## Command-line usage

```
adaptiseq -i accession [options]
```

| Flag | Meaning |
|------|---------|
| `-i, --input [text\|file]` | Single accession or a file with one accession per line. |
| `-m, --metadata` | Fetch metadata only; no sequence download. |
| `-g, --gzip` | Prefer direct `.fastq.gz`; fall back to `.sra` then convert. |
| `-q, --fastq` | Convert `.sra` to FASTQ with `fasterq-dump`. |
| `-t, --threads int` | Threads for `fasterq-dump`/`pigz` (default 8). |
| `-e, --merge [ex\|sa\|st]` | Merge at Experiment / Sample / Study level. |
| `-d, --database [ena\|sra]` | Force database (default: auto-detect). |
| `-p, --parallel int` | `axel` connection count. |
| `-a, --aspera` | Aspera via `ascp` (GSA/ENA; Huawei Cloud still wins for GSA). |
| `-s, --speed int` | Speed cap in MB/s (default 1000). |
| `-k, --skip-md5` | Skip the integrity check. |
| `-r, --protocol [ftp\|https]` | ENA protocol. Unspecified = `auto` (HTTPS-first transport selection); `ftp`/`https` force it. |
| `-Q, --quiet` | Suppress progress output. |
| `-o, --output text` | Output directory (created if missing). |
| `--engine [segmented\|classic]` | Download engine (**default: `segmented`**). `classic` is the Part 1 `wget`/`axel` path; `segmented` falls back to it per-host when a host cannot serve ranges. |
| `--segment-size int` | Segmented engine: target segment size in MB (default 512). |
| `--max-segments int` | Segmented engine: max connections per file (default 8). |
| `--max-conns-per-host int` | Global cap on concurrent connections to any one host (default 8). |
| `-h, --help` / `-v, --version` | Help / version (`adaptiSeq 0.1.0`). |

`-p, --parallel N` is an alias for `--max-segments N` on the segmented engine (it
keeps its original `axel` connection-count meaning on `--engine classic`).

Examples:

```bash
adaptiseq -i SRR7706354 -m              # metadata only -> SRR7706354.metadata.tsv
adaptiseq -i CRR311377                  # GSA run -> .metadata.csv + CRA*.metadata.xlsx + data
adaptiseq -i accessions.txt -g          # mixed SRA/GSA list, direct fastq.gz where possible
adaptiseq -i SRX003906 -g -e ex         # merge an Experiment's runs
```

## Library API

```python
from adaptiseq import fetch, resolve, get_metadata

records = get_metadata("SRR7706354")               # parsed metadata rows (list of dicts)
urls    = resolve("SRR7706354", database="ena")    # resolved download URLs
result  = fetch("SRR7706354", outdir="data/",      # download + verify
                gzip=True)
print(result.success_ids, result.fail_ids, result.failed)
```

These functions never call `sys.exit` and never print colour codes. They raise the
typed exceptions in `adaptiseq.errors` (`InvalidAccessionError`, `MetadataError`,
`DownloadError`, `IntegrityError`, `MergeError`, `PreflightError`,
`EngineUnavailableError`). The CLI (`adaptiseq.cli`) is a thin wrapper that catches
them and renders the matching coloured `Error` / `How to solve?` lines.

> Note: `adaptiseq.resolve` (the package attribute) is the public *function*; the
> internal `resolve.py` submodule is reached via `importlib.import_module` or the
> aliased internal imports. See `NOTES.md`.

## Segmented download engine (Part 2)

The default engine downloads each file in multiple range-based segments and
resumes interrupted transfers:

- **Per-file concurrency from size:** `min(--max-segments, max(1, size //
  --segment-size))` segment connections; the last segment takes the remainder.
- **Strict `206` HTTP(S)** segments written at the right offset via `os.pwrite`,
  with atomic `.part` + `.part.meta` resume (interrupt and rerun to continue, not
  restart). Single-connection fallback for hosts without ranges.
- **Native segmented FTP** (`REST`/`RETR`) for FTP hosts that allow it.
- **Transport selection:** with `auto` (the default) the engine prefers the HTTPS
  mirror, confirmed by a cheap per-host probe, then native segmented FTP, then
  single-stream, then `--engine classic`. `-r https` / `-r ftp` force it. It never
  writes a zero-byte or truncated file.
- **Connection etiquette:** a global per-host connection cap
  (`--max-conns-per-host`) and a reactive circuit breaker (back off a host that
  returns 429/503 or refuses connections, then recover).
- **Speed cap:** `-s/--speed` MB/s via a shared token-bucket limiter.

> **EBI FTP note:** EBI restricts FTP `REST` and caps concurrent connections per
> IP — the two things segmentation needs — so `auto` prefers the ENA **HTTPS**
> mirror (`https://ftp.sra.ebi.ac.uk/...`, same host, range-capable). Verified
> live: a small real ENA fastq fetched in multiple segments is byte-identical to
> `wget`.

```python
from adaptiseq import fetch
fetch("SRR1553469", outdir="data/", gzip=True,           # segmented by default
      max_segments=8, max_conns_per_host=8, segment_size_mb=512)
fetch("SRR1553469", outdir="data/", engine="classic")     # Part 1 wget/axel path
```

## Output files

For **SRA/ENA/DDBJ/GEO** accessions: `SRA files`, `${accession}.metadata.tsv`,
`success.log`, `fail.log`. For **GSA** accessions: `GSA files` (mostly `.gz`),
`${accession}.metadata.csv`, `${CRA}.metadata.xlsx`, `success.log`, `fail.log`.

## Testing

```bash
pip install -e ".[test]"
pytest                       # fixture-mode parity + unit tests (offline) + live tests
ADAPTISEQ_NO_NETWORK=1 pytest # force offline; live/canary tests skip, fixtures still run
```

Two differential modes (Section 8.1 of the build spec):

- **Fixture mode (default, never skips):** diffs adaptiSeq's parsing/resolution
  against frozen golden summaries under `tests/fixtures/`. This is what guards CI,
  where `iseq` and/or the network may be absent.
- **Live mode (skips gracefully):** fetches metadata live and compares the stable
  Run/md5 sets to the golden; when `iseq` is installed it also runs stock
  `iseq -m` and `adaptiseq -m` into two directories and diffs the metadata files.

An **API-drift canary** (`tests/test_api_drift.py`) checks one stable accession per
database; when it fails, the message says an upstream API moved — not that
adaptiSeq is broken.

## Project layout

```
adaptiseq/
  __init__.py     # public API: fetch / resolve / get_metadata
  cli.py          # argparse, dispatch, version/help mirroring iseq
  accession.py    # validateQuery port: regexes + GEO resolution
  routing.py      # GSA vs SRA/ENA routing; -e merge guards
  metadata.py     # ENA filereport / SRA eutils+sra-db-be / GSA CSV+XLSX
  resolve.py      # per-run URL resolution (downloadSRA/downloadGSA ports)
  engine/
    classic.py    # wget/axel + ascp (Part 1 engine; the fetch seam + fallback)
    segmented.py  # Part 2: segmented HTTP(S) downloader (range, .part resume)
    ftp.py        # Part 2: native segmented FTP (REST/RETR via aioftp)
    seam.py       # Part 2: SegmentedEngine — transport selection + classic fallback
    ratelimit.py  # Part 2: token-bucket limiter, per-host cap, circuit breaker
    optimize.py   # STUB -> Part 3 (adaptive controller)
  convert.py      # fasterq-dump + pigz
  integrity.py    # vdb-validate + md5 checks (checkSRA/checkGSA)
  merge.py        # mergeSRArun / mergeGSArun ports
  preflight.py    # CheckSoftware port
  logs.py         # success.log / fail.log helpers
  console.py      # exact ANSI message style + Reporter abstraction
  net.py          # wget wrappers (metadata/discovery I/O)
  options.py      # Options / RunContext (replaces shell globals)
  errors.py       # typed exceptions
  core.py         # per-accession process loop
```

## License

MIT (same as `iseq`). adaptiSeq is a derivative reimplementation of
[BioOmics/iSeq](https://github.com/BioOmics/iSeq); please also cite the original:
Chao *et al.*, *iSeq: An integrated tool to fetch public sequencing data*,
Bioinformatics, 2024.
