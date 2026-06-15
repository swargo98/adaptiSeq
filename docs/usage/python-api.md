# Python API

Unlike `iseq` (a Bash script), adaptiSeq ships a real, importable Python API. The
three public functions **return values and raise typed exceptions** — they never
call `sys.exit` and never print colour codes — so you can drive them from a
script, notebook, or pipeline.

```python
from adaptiseq import fetch, resolve, get_metadata
```

## `get_metadata` — parsed metadata rows

```python
rows = get_metadata("SRR7706354")                 # list[dict] (TSV columns)
rows = get_metadata("CRR311377")                  # GSA -> list[dict] (CSV columns)
rows = get_metadata("SRR7706354", database="ena") # force a database
```

Writes the same `*.metadata.*` files the CLI writes; with no `outdir` it uses a
temporary directory and cleans up.

## `resolve` — URLs without downloading

```python
urls = resolve("SRR7706354", database="ena")      # list[str] of download URLs
urls = resolve("SRR7706354", gzip=True)            # the *.fastq.gz links
```

Fetches metadata, then returns the URLs the engine *would* fetch — useful for
auditing or feeding another downloader.

## `fetch` — download and verify

```python
# a single accession
result = fetch("SRR1553469", outdir="data/", gzip=True)

# a whole batch (same -i semantics as the CLI: a file of accessions)
result = fetch("accessions.txt", outdir="data/", gzip=True,
               jobs=20, adaptive=True)

print(result.accession, result.outdir, result.failed)
print(result.success_ids, result.fail_ids)
```

`fetch` is a thin wrapper over the same pipeline the CLI runs. It returns a
`FetchResult`:

| Field | Type | Meaning |
| ----- | ---- | ------- |
| `accession` | `str` | the input (accession or file path) |
| `outdir` | `Path` | where files were written |
| `failed` | `bool` | whether any Run ultimately failed |
| `success_ids` | `list[str]` | Runs in `success.log` |
| `fail_ids` | `list[str]` | Runs in `fail.log` |

`fetch` accepts keyword equivalents of every CLI flag (`metadata`, `gzip`,
`fastq`, `threads`, `merge`, `database`, `aspera`, `speed`, `skip_md5`, `protocol`,
`quiet`, `engine`, `segment_size_mb`, `max_segments`, `max_conns_per_host`, `jobs`,
`adaptive`, `probe_window`, `cc_penalty`, `meta_jobs`, `aspera_efficiency`), plus
an optional `reporter` to capture progress.

## Typed exceptions

All inherit from `AdaptiSeqError` (in `adaptiseq.errors`):

| Exception | Raised when |
| --------- | ----------- |
| `InvalidAccessionError` | the accession matches no supported format |
| `MetadataError` | metadata could not be fetched / was empty everywhere |
| `DownloadError` | a file could not be resolved or downloaded |
| `IntegrityError` | a file failed md5 / `vdb-validate` after all retries |
| `MergeError` | a merge input was missing |
| `PreflightError` | a required external tool is missing from `PATH` |
| `EngineUnavailableError` | an unknown engine was requested |

```python
from adaptiseq import fetch
from adaptiseq.errors import PreflightError, MetadataError

try:
    fetch("SRR1553469", outdir="data/", gzip=True)
except PreflightError as e:
    print("missing tool:", e.message, "->", e.solution)
except MetadataError as e:
    print("metadata problem:", e.message)
```

> **Note**
> `adaptiseq.resolve` (the package attribute) is the public **function**; it
> shadows the internal `resolve.py` submodule, which is reached via
> `importlib.import_module("adaptiseq.resolve")`.

## Type hints

The package ships a `py.typed` marker, so type checkers see adaptiSeq's
annotations.
