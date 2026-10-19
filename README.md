<h1 align="center">
  <img src="https://raw.githubusercontent.com/swargo98/adaptiSeq/main/adaptiseq/assets/logo.png" alt="adaptiSeq" width="480">
</h1>

<p align="center"><b>An adaptive tool to fetch public sequencing data</b></p>

<p align="center">
  <a href="https://github.com/swargo98/adaptiSeq/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="https://pypi.org/project/adaptiseq/"><img src="https://img.shields.io/pypi/v/adaptiseq.svg" alt="PyPI version"></a>
  <a href="https://github.com/swargo98/adaptiSeq/actions/workflows/ci.yml"><img src="https://github.com/swargo98/adaptiSeq/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://swargo98.github.io/adaptiSeq/"><img src="https://img.shields.io/badge/docs-online-0a6b6b" alt="Documentation"></a>
  <a href="https://colab.research.google.com/github/swargo98/adaptiSeq/blob/main/adaptiSeq_Colab_Quickstart.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a>
</p>

<p align="center">
  <a href="https://swargo98.github.io/adaptiSeq/"><b>📖 Documentation</b></a>
  &nbsp;·&nbsp;
  <a href="#installation">Installation</a>
  &nbsp;·&nbsp;
  <a href="#usage">Usage</a>
  &nbsp;·&nbsp;
  <a href="#related-tools">Comparison</a>
</p>

## Description

**adaptiSeq** is a fast, importable Python tool that downloads sequencing data and
metadata from **[GSA](https://ngdc.cncb.ac.cn/gsa/)**,
**[SRA](https://www.ncbi.nlm.nih.gov/sra/)**,
**[ENA](https://www.ebi.ac.uk/ena/)**,
**[DDBJ](https://www.ddbj.nig.ac.jp/)**, and
**[GEO](https://www.ncbi.nlm.nih.gov/geo/)**. It is built for the workload real
pipelines actually have: **lists of accessions**, downloaded in parallel, with a
**segmented, resumable, self-tuning** engine and a **real Python API**.

adaptiSeq builds on **[iSeq](https://github.com/BioOmics/iSeq)** (Chao *et al.*,
*Bioinformatics*, 2024,
[doi:10.1093/bioinformatics/btae641](https://doi.org/10.1093/bioinformatics/btae641)):
its accession resolution, metadata, integrity, and merge behaviour are a Python
reimplementation of iSeq's. If you use adaptiSeq, **please cite iSeq** as well
(see [Cite us](#cite-us)).

> **Important**
> To use adaptiSeq your system must be **connected to the network** and able to
> reach the databases over **HTTP, HTTPS, and (optionally) FTP / Aspera**.

## Update Notes

### 0.1.8 (in development)
- **New** `--controller NAME` (and `fetch(controller=...)`) picks the adaptive
  controller: `topdown` (the default, unchanged), `bottomup` (the original
  gradient optimizer), and two candidates under evaluation: `budget`, which
  keeps every worker active and steers a per-host connection budget (raise
  while it pays, cut when it does not or on server pushback), and `greedy`,
  which runs every worker and backs off only on HTTP 429/503. The default will
  be chosen from a benchmark on every archive adaptiSeq supports.
- **Fix (GSA)**: GSA's browse page now answers scripts with a browser check and
  no links, so GSA runs had nothing to download. Links now come from the
  run-info table GSA's API returns, fetched from `download.cncb.ac.cn` over
  HTTPS (`-r ftp` keeps `download.big.ac.cn` FTP; Aspera unchanged).
- **GSA in batch mode**: GSA runs now join the parallel pool with the other
  archives (they downloaded one file at a time), with md5 checks in the pool
  from the project's `md5sum.txt`.
- **Fix (GSA)**: after an md5 mismatch the bad file is deleted before the first
  retry, so the retry downloads again instead of re-checking the same bytes.

### 0.1.7 (built for the benchmark; not yet on PyPI)
- **Fix**: a range probe that gets no answer (refused, reset, timed out) is
  retried, and waits at the host's connection limit like a segment does.
  Previously it was read as "the server has no ranges" and the whole file
  went over one connection; when ENA refused a few probes, 1.5 to 2 GB files
  downloaded single-stream for 15 to 30 min each. A probe that never gets an
  answer now fails the file (the batch retries it); transport selection still
  falls back to FTP when HTTPS never answers.

### 0.1.6 (built for the benchmark; not yet on PyPI)
- **Segmented HTTPS** keeps a file's connections busy to the end: when a
  segment finishes, its connection takes over half of the largest remaining
  piece of the same file, and once the batch queue is empty, unused per-host
  connection budget splits in-flight files further (up to `--max-segments`).
  Previously the last bytes of each file arrived on one connection; on a
  16-file, 26 GB list that tail took 15 of 26 minutes.

### 0.1.5 (built for the benchmark; not yet on PyPI)
- **Fix**: an ENA metadata query that fails (HTTP 500, timeout, network error)
  or comes back with no rows is no longer read as "not in ENA". Previously such
  a Run went to the SRA fallback, and the converted FASTQ could not be checked
  against ENA's md5; during an ENA portal outage this hit whole lists. A failed
  query is now retried like the error body (4 tries, 2/4/8 s apart); an empty
  answer is retried once, so a Run that is really SRA-only costs one extra query.
- **Batch mode** (`-j`) now says which accessions are downloaded from SRA
  instead of ENA ("N accession(s) had no usable ENA metadata and will be
  downloaded from SRA: ..."). Previously that fallback was silent until each
  Run's verification note.
- **New** `--no-sra-fallback`: a Run with no usable ENA metadata or file fails
  (exit 1; in a list it goes to `fail.log` and the rest continue) instead of
  being fetched from NCBI SRA, so every file that is kept was checked against
  ENA's md5. A cached SRA runinfo file from an earlier run is queried again on
  ENA. Cannot be combined with `-d sra`.
- **Batch mode** checks each `.fastq.gz` against ENA's md5 as soon as it lands.
  A corrupt transfer is deleted and downloaded again inside the pool, in
  parallel with the other files, instead of after the batch, one file at a
  time. The per-Run check reuses the digest rather than hashing the file twice.
  On a 26 GB, 16-file list with several corrupt transfers, the serial retries
  had taken 1.5 to 2.5 h of a 2 to 3 h run.
- **Fix**: a refused connect while other connections to the same host are open
  is treated as the host's connection limit (ENA refuses some connects once a
  client has many open). The per-host cap is held at the number of open connections
  and the segment waits for a slot. Previously each refusal halved the cap,
  blocked the host for a backoff, and used up one of the segment's three
  attempts, so a few refusals could fail a whole file.
- **Batch mode**: a file that starts near the end of a batch (or is fetched
  again after an md5 mismatch) shares the per-host connection budget with the
  files still to do, so it may use up to `--max-segments` segments of at least
  64 MiB. Previously its split was fixed at `size // --segment-size` (three for
  a 1.6 GB file), and the last files of a batch ran on one to three
  connections. A resumed download keeps the split it started with.

### 0.1.4
- **Fix**: `-g` on a Run with no ENA FASTQ mirror (SRA-only, e.g. `SRR1031066`)
  no longer exits with code 1 and a `fail.log` entry after producing complete
  FASTQ. The `.sra` is now validated with `vdb-validate`, recorded in
  `success.log`, and not re-downloaded.
- **Fix**: after an MD5 mismatch, the mismatching file is deleted before the
  first retry, so every retry is a fresh download. Previously the first retry
  found the full-size file, treated it as already complete, and re-checked the
  same bytes.
- **Fix**: ENA's portal sometimes answers a metadata query with an in-band
  error (`ERROR occurred. Not all results may have been written...`). adaptiSeq
  took that line for a Run, cached it as the accession's `.metadata.tsv`, and
  lost the accession. The error body is now retried (4 tries, 2/4/8 s apart,
  then the SRA fallback) and a cached error body is fetched again.
- **Fix**: in an accession list, one accession that cannot be resolved or
  downloaded no longer stops the rest. It is reported, written to `fail.log`,
  and the run continues (exit status 1 at the end), as iSeq does. Previously
  the verification pass after a batch download stopped at that accession, so
  later Runs were neither md5-checked nor retried. A single accession still
  raises as before.
- **Fix**: resume state left without its data (`.part.meta` present, `.part`
  gone) is discarded instead of resumed. Previously a re-download after an MD5
  mismatch could fetch only the segments that state listed as unfinished and
  leave the rest of the file as zeros; segmented FTP could also report success
  with no file written. A single-connection download now also clears the resume
  state of an earlier segmented attempt.
- **Docs**: iSeq's and FastBioDL's MIT notices added to `LICENSE`; iSeq and
  FastBioDL credited in the README and `CITATION.cff`. Comparison table updated
  for Kingfisher 0.5.0 (Python API, experimental GSA) and pysradb 2.5.1
  (`--threads`).

### 0.1.3
- **Fix**: a segmented download whose `.part` file is missing at finalize (e.g.
  every segment's connection was refused) now fails cleanly and retries, instead
  of raising a confusing `FileNotFoundError` from an unguarded `.part` rename.

### 0.1.2
- **Fix**: the notebook event-loop handling from 0.1.1 now also works when
  `nest_asyncio` is active (it previously hung/errored on batch downloads). The
  API detects a re-entrant loop and drives the coroutine on it directly; plain
  Jupyter still uses a worker thread. Works with or without `nest_asyncio`.

### 0.1.1
- **Fix**: the Python API (`fetch`/`resolve`) now works inside a running asyncio
  event loop (Jupyter / Google Colab / IPython), where it previously raised
  `asyncio.run() cannot be called from a running event loop`. The CLI was
  unaffected.

### 0.1.0 (initial release)
- First public release: segmented engine + adaptive batch pool + parallel
  metadata resolution + adaptive Aspera + Python API.
- Validated against the **real ENA Aspera** endpoint with a genuine IBM `ascp`.
- Offline test suite (fixtures, engine, batch, adaptive) green; CI on Python
  3.10–3.12.

<details>
<summary>Design highlights</summary>

- **Segmented, resumable HTTP(S)/FTP engine** (the default) with `.part`/`.part.meta`
  resume — interrupt and re-run to continue, not restart.
- **Batch-parallel download** of accession lists through an asyncio worker pool.
- **Adaptive concurrency**: an adaptive controller (top-down knee search by
  default) tunes how many downloads run at once from measured throughput.
- **Parallel metadata resolution** under polite per-endpoint rate limits.
- **Adaptive parallel Aspera** via an efficiency-hysteresis controller.
- **Python API** (`fetch`, `resolve`, `get_metadata`) that returns values and
  raises typed exceptions.
- Correctly downloads **3-file runs** (orphan/barcode + `_1` + `_2`) that iSeq
  mishandles.

</details>

## Features
- **Multiple database support**: GSA / SRA / ENA / DDBJ / GEO.
- **Multiple input formats**: Project, Study, BioSample, Sample, Experiment, or
  Run accession — single, or a file of many (mixed databases allowed).
- **Metadata download**: per-accession sample metadata (`-m`).
<details>
<summary>More features</summary>

- **File-format selection**: direct gzip FASTQ (`-g`) or SRA→FASTQ conversion (`-q`).
- **Multi-threaded conversion/compression** (`-t`).
- **File merging** per Experiment/Sample/Study (`-e`).
- **Batch-parallel download** of accession lists (`-j`), with **adaptive**
  concurrency (`--adaptive`) and **parallel metadata resolution** (`--meta-jobs`).
- **Segmented, resumable transfers** with HTTPS-first transport selection.
- **Aspera high-speed download** for GSA/ENA (`-a`), adaptive for ENA.
- **Automatic retry** (up to three rounds) and **md5 / `vdb-validate` verification**.
- **Importable Python API** with typed exceptions and `py.typed`.
- **Error handling**: clear, actionable messages with suggested solutions.

</details>

## Installation

### 1. From PyPI (recommended)
```bash
pip install adaptiseq
adaptiseq --version
```

### 2. From source
```bash
git clone https://github.com/swargo98/adaptiSeq.git
cd adaptiSeq
pip install -e .
adaptiseq --version
```

### 3. Conda environment
```bash
conda env create -f environment.yml && conda activate adaptiseq
```

External tools: `wget` (always), `sra-tools`, `pigz`, `md5sum`,
`axel` (classic `-p`), and IBM `ascp` (`-a`). adaptiSeq requires each **only when a
run actually needs it**. Full detail: **[docs/installation.md](docs/installation.md)**.

## Example

1. Download all Runs and metadata for an accession.
```bash
adaptiseq -i PRJNA211801
```

2. Batch download a list, directly as gzip FASTQ, through the adaptive pool.
```bash
adaptiseq -i SRR_Acc_List.txt -g
```

See **[docs/examples.md](docs/examples.md)** for more.

## Usage

```
$ adaptiseq --help

Usage:
  adaptiseq -i accession [options]

Required option:
  -i, --input     [text|file]   Single accession or a file containing multiple accessions.
                                Note: only one accession per line in the file.

Optional options:
  -m, --metadata                Skip the sequencing data downloads and only fetch metadata.
  -g, --gzip                    Download FASTQ files in gzip format directly (*.fastq.gz).
  -q, --fastq                   Convert SRA files to FASTQ format.
  -t, --threads   int           Threads for SRA->FASTQ / compression (default: 8).
  -e, --merge     [ex|sa|st]    Merge fastq files per Experiment, Sample, or Study.
  -d, --database  [ena|sra]     Force database for SRA data (default: auto-detect).
      --no-sra-fallback         Fail a Run that ENA cannot serve instead of fetching it from SRA.
  -p, --parallel  int           axel connection count (classic engine only), e.g. -p 10.
  -a, --aspera                  Use Aspera (ascp); GSA/ENA only.
  -s, --speed     int           Download speed limit (MB/s) (default: 1000).
  -k, --skip-md5                Skip the md5 check for downloaded files.
  -r, --protocol  [ftp|https]   ENA transport (default: auto, HTTPS-first).
  -Q, --quiet                   Suppress download progress bars.
  -o, --output    text          Output directory (created if missing; default: cwd).
  --engine        [segmented|classic]   Download engine (default: segmented).
  --segment-size  int           Target segment size in MB (default: 512).
  --max-segments  int           Max connections per file (default: 8).
  --max-conns-per-host int      Global cap on connections to one host (default: 8).
  -j, --jobs      int           Max worker-pool size for batch download (default: 20).
  --adaptive / --no-adaptive    Gradient adaptive-concurrency controller (default: on).
  --probe-window  int           Adaptive probe window in seconds (default: 5).
  --cc-penalty    float         Worker-cost penalty K (default: 1.01).
  --meta-jobs     int           Parallelism for metadata/URL resolution (default: 3).
  --aspera-efficiency float     Keep an extra ascp worker only above this efficiency (0.70).
  -h, --help                    Show the help information.
  -v, --version                 Show the program version.
```

### 1. `-i`, `--input`

Input the accession to download, or a **file** with one accession per line
(databases may be mixed). adaptiSeq retrieves the accession's metadata, then
downloads each Run it contains.

```bash
adaptiseq -i PRJNA211801
adaptiseq -i accessions.txt        # batch
```

Currently **supports 6 accession formats** across **5 databases**:

| Databases | BioProject | Study | BioSample | Sample | Experiment | Run  |
| --------- | ---------- | ----- | --------- | ------ | ---------- | ---- |
| **GSA**   | PRJC       | CRA   | SAMC      | \      | CRX        | CRR  |
| **SRA**   | PRJNA      | SRP   | SAMN      | SRS    | SRX        | SRR  |
| **ENA**   | PRJEB      | ERP   | SAME      | ERS    | ERX        | ERR  |
| **DDBJ**  | PRJDB      | DRP   | SAMD      | DRS    | DRX        | DRR  |
| **GEO**   | GSE        | \     | GSM       | \      | \          | \    |

GEO `GSE/GSM` accessions are resolved to their associated `PRJNA/SAMN` and then
downloaded from SRA. Every contained Run is **md5-checked**; on mismatch adaptiSeq
retries up to **three rounds**, recording results in `success.log` / `fail.log`.

### 2. `-m`, `--metadata`

Download only the sample metadata and skip the sequence data.

```bash
adaptiseq -i PRJNA211801 -m
adaptiseq -i CRR343031 -m
```

ENA → TSV (`${accession}.metadata.tsv`); GSA → CSV + project XLSX
(`${accession}.metadata.csv`, `CRA*.metadata.xlsx`). Details:
**[docs/usage/metadata.md](docs/usage/metadata.md)**.

### 3. `-g`, `--gzip`

Download FASTQ directly in gzip format; if unavailable on ENA, download the `.sra`
and convert with `fasterq-dump` + `pigz`.

```bash
adaptiseq -i SRR1178105 -g
```

### 4. `-q`, `--fastq`

Convert the downloaded `.sra` into FASTQ (single-cell friendly: `I1/R1/R2/R3`).

```bash
adaptiseq -i SRR1178105 -q -t 10
```

### 5. `-e`, `--merge`

Merge a group of Runs into one FASTQ per Experiment (`ex`), Sample (`sa`), or
Study (`st`).

```bash
adaptiseq -i SRX003906 -g -e ex
```

### 6. `-d` / `-r` / `-p` / `-s` / `-k` / `-Q`

Force database (`-d ena|sra`), ENA transport (`-r https|ftp`, default auto
HTTPS-first), classic-engine axel connections (`-p`, with `--engine classic`),
speed cap (`-s` MB/s), skip md5 (`-k`), and quiet (`-Q`). See
**[docs/usage/download.md](docs/usage/download.md)**.

### 7. Batch & adaptive (`-j`, `--adaptive`, `--meta-jobs`)

For accession lists, adaptiSeq resolves in parallel (`--meta-jobs`) then downloads
through an asyncio worker pool (`-j`) whose active size the adaptive controller
tunes (`--adaptive`; `topdown` by default, `ASEQ_ADAPTIVE_MODE=bottomup` for the
gradient controller — see `docs/ADAPTIVE_CONTROLLER.md`).

```bash
adaptiseq -i accessions.txt -g -j 8
adaptiseq -i accessions.txt -g --no-adaptive
```

Full detail: **[docs/usage/batch.md](docs/usage/batch.md)**.

### 8. `-a`, `--aspera`

Use IBM Aspera (`ascp`); **GSA/ENA only**. ENA uses an **adaptive** parallel pool
(efficiency hysteresis); GSA is sequential, best-effort (Huawei-Cloud preferred).

```bash
adaptiseq -i PRJNA211801 -a -g
```

Detail: **[docs/usage/aspera.md](docs/usage/aspera.md)**.

### 9. Python API

```python
from adaptiseq import fetch, resolve, get_metadata

rows   = get_metadata("SRR7706354")               # parsed metadata rows
urls   = resolve("SRR7706354", database="ena")    # resolved URLs (no download)
result = fetch("accessions.txt", outdir="data/", gzip=True, jobs=20, adaptive=True)
print(result.success_ids, result.fail_ids, result.failed)
```

The API never calls `sys.exit` and never prints colour codes; it raises the typed
exceptions in `adaptiseq.errors`. Full reference:
**[docs/usage/python-api.md](docs/usage/python-api.md)**.

## Output

- **SRA / ENA / DDBJ / GEO** accessions:

| Output        | Description |
| ------------- | ----------- |
| SRA files     | Convert to FASTQ with `-q` |
| `.metadata.tsv` | Metadata for the query accession |
| `success.log` | Runs downloaded successfully |
| `fail.log`    | Runs that failed |

- **GSA** accessions:

| Output         | Description |
| -------------- | ----------- |
| GSA files      | Mostly `*.gz` (a few bam/tar/bz2) |
| `.metadata.csv`  | Metadata for the query accession |
| `.metadata.xlsx` | Project metadata (xlsx) for the accession |
| `success.log`  | Runs downloaded successfully |
| `fail.log`     | Runs that failed |

## Documentation

Full documentation lives in **[`docs/`](docs/README.md)**:
[Installation](docs/installation.md) ·
[Usage overview](docs/usage/README.md) ·
[Downloading](docs/usage/download.md) ·
[Metadata](docs/usage/metadata.md) ·
[Merging](docs/usage/merge.md) ·
[Batch & adaptive](docs/usage/batch.md) ·
[Aspera](docs/usage/aspera.md) ·
[Python API](docs/usage/python-api.md) ·
[Method details](docs/methods.md) ·
[Examples](docs/examples.md) ·
[FAQ](docs/faq.md).

## Related tools

adaptiSeq sits among other downloaders for public sequencing data —
[iSeq](https://github.com/BioOmics/iSeq),
[fastq-dl](https://github.com/rpetit3/fastq-dl),
[fetchngs](https://github.com/nf-core/fetchngs),
[pysradb](https://github.com/saketkc/pysradb), and
[Kingfisher](https://github.com/wwood/kingfisher-download). A comparison:

The last three columns — **Batch**, **Adaptive**, and **Python API** — are what set
adaptiSeq apart.

| Software | Languages | Databases | Accessions | Formats | Methods | Metadata | MD5 | Resumable | Parallel | Batch | Adaptive | Python API | Merge | Skip done | Conda |
| -------- | --------- | --------- | ---------- | ------- | ------- | :------: | :-: | :-------: | :------: | :---: | :------: | :--------: | :---: | :-------: | :---: |
| **adaptiSeq** | Python | GSA, SRA, ENA, DDBJ, GEO | All | fq, fq.gz, sra, bam | segmented http(s)/ftp, aspera, wget/axel | ✔ | ✔ | ✔ | ✔ | **✔** | **✔** | **✔** | ✔ | ✔ | TBD (pip ✔) |
| [iSeq](https://github.com/BioOmics/iSeq) | Shell | GSA, SRA, ENA, DDBJ, GEO | All | fq, fq.gz, sra, bam | wget, axel, aspera | ✔ | ✔ | ✔ | ✔ | ❌ | ❌ | ❌ | ✔ | ✔ | ✔ |
| [SRA Toolkit](https://github.com/ncbi/sra-tools) | C | SRA, ENA, DDBJ | All except Run | fq, fq.gz, sra | prefetch | ❌ | ✔ | ✔ | ❌ | ❌ | ❌ | ❌ | ❌ | ✔ | ✔ |
| [enaBrowserTools](https://github.com/enasequence/enaBrowserTools) | Python | SRA, ENA, DDBJ | All except GSA/GEO | fq, fq.gz, sra | urllib, aspera | ✔ | ✔ | ✔ | ❌ | ❌ | ❌ | ❌ | ❌ | ✔ | ✔ |
| [fastq-dl](https://github.com/rpetit3/fastq-dl) | Python | SRA, ENA, DDBJ | All except GSA/GEO | fq, fq.gz, sra | wget | ✔ | ✔ | ❌ | ❌ | ❌ | ❌ | ❌ | ✔ | ✔ | ✔ |
| [fetchngs](https://github.com/nf-core/fetchngs) | Python | SRA, ENA, DDBJ, GEO | All except GSA | fq, fq.gz | wget, aspera, prefetch | ✔ | ✔ | ✔ | ❌ | ✔ | ❌ | ❌ | ❌ | ✔ | ❌ |
| [pysradb](https://github.com/saketkc/pysradb) | Python | SRA, ENA, DDBJ, GEO | All except GSA | fq, fq.gz, sra, bam | requests, aspera | ✔ | ✔ | ✔ | ❌ | ✔ | ❌ | ✔ | ❌ | ✔ | ✔ |
| [Kingfisher](https://github.com/wwood/kingfisher-download) | Python | SRA, ENA, DDBJ, GSA (experimental) | All except GEO | fq, fq.gz, sra | curl, aria2c, aspera | ✔ | ✔ | ❌ | ✔ | ❌ | ❌ | ✔ | ❌ | ✔ | ✔ |

> **Parallel** = multiple connections/segments per transfer · **Batch** = many
> accessions downloaded **in parallel** in one run (not one-at-a-time) ·
> **Adaptive** = a controller that self-tunes the worker count from measured
> throughput · **Python API** = importable library (`fetch`/`resolve`/`get_metadata`),
> not only a command-line tool.

No other tool combines all three. adaptiSeq pairs them with **parallel metadata
resolution** and a **segmented, resumable** engine, so a list of hundreds of
accessions is resolved and downloaded concurrently, self-tuning to the throughput
the servers actually give — from a script, notebook, or the shell.

## Contributing

Contributions are welcome — please open an issue for bugs/suggestions, or fork,
branch, and submit a pull request. The offline test suite runs with
`python -m pytest`.

## Cite us

A manuscript describing adaptiSeq is in preparation; citation metadata for the
software itself is in [`CITATION.cff`](CITATION.cff).

adaptiSeq builds on two earlier tools. If you use it, please also cite:

- **iSeq**, whose accession resolution, metadata, integrity, and merge behaviour
  adaptiSeq reimplements in Python:
  Chao H, Li Z, Chen D, Chen M. *iSeq: An integrated tool to fetch public sequencing
  data.* **Bioinformatics**, 2024, btae641,
  [doi:10.1093/bioinformatics/btae641](https://doi.org/10.1093/bioinformatics/btae641).
- **FastBioDL**, from which the segmented, resumable transfer engine
  (`adaptiseq/engine/segmented.py`) is ported:
  Swargo RM, Arslan E, Arifuzzaman M. *Adaptive Parallel Downloader for Large
  Genomic Datasets.* [arXiv:2508.05511](https://arxiv.org/abs/2508.05511).

## License

This project is licensed under the [MIT License](LICENSE). The `LICENSE` file also
reproduces the MIT notice of [iSeq](https://github.com/BioOmics/iSeq)
(Copyright (c) 2024 BioOmics), from which adaptiSeq is derived.
