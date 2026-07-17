[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/swargo98/adaptiSeq/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/adaptiseq.svg)](https://pypi.org/project/adaptiseq/)
[![CI](https://github.com/swargo98/adaptiSeq/actions/workflows/ci.yml/badge.svg)](https://github.com/swargo98/adaptiSeq/actions/workflows/ci.yml)

<!-- PyPI/bioconda badges resolve once the package is published; until then see Installation. -->

# [adaptiSeq](https://github.com/swargo98/adaptiSeq): An [adapti](https://github.com/swargo98/adaptiSeq)ve tool to fetch public [Seq](https://github.com/swargo98/adaptiSeq)uencing data

**Cite us**: TBD — a manuscript is in preparation. adaptiSeq builds on **iSeq**
(Chao *et al.*, *Bioinformatics*, 2024, btae641,
[doi:10.1093/bioinformatics/btae641](https://doi.org/10.1093/bioinformatics/btae641));
please cite iSeq if you use adaptiSeq today.

## Description

**adaptiSeq** is a fast, importable Python tool that downloads sequencing data and
metadata from **[GSA](https://ngdc.cncb.ac.cn/gsa/)**,
**[SRA](https://www.ncbi.nlm.nih.gov/sra/)**,
**[ENA](https://www.ebi.ac.uk/ena/)**,
**[DDBJ](https://www.ddbj.nig.ac.jp/)**, and
**[GEO](https://www.ncbi.nlm.nih.gov/geo/)**. It is a tested reimplementation of
the [iSeq](https://github.com/BioOmics/iSeq) Bash tool — **byte-for-byte faithful**
on resolution, metadata, integrity, and merge — extended for the workload real
pipelines actually have: **lists of accessions**, downloaded in parallel, with a
**segmented, resumable, self-tuning** engine and a **real Python API**.

_Pipeline diagram: **TBD** (to be added at `docs/img/adaptiSeq-Pipeline.png`)._
<!-- When ready: ![adaptiSeq-pipeline](docs/img/adaptiSeq-Pipeline.png) -->

> **Important**
> To use adaptiSeq your system must be **connected to the network** and able to
> reach the databases over **HTTP, HTTPS, and (optionally) FTP / Aspera**.

## Update Notes

### 0.1.3
- **Fix**: a segmented download whose `.part` file is missing at finalize (e.g.
  every segment's connection was refused) now fails cleanly and retries, instead
  of raising a confusing `FileNotFoundError` from an unguarded `.part` rename.

### 0.1.2
- **Fix**: the notebook event-loop handling from 0.1.1 now also works when
  `nest_asyncio` is active (it previously hung/erered on batch downloads). The
  API detects a re-entrant loop and drives the coroutine on it directly; plain
  Jupyter still uses a worker thread. Works with or without `nest_asyncio`.

### 0.1.1
- **Fix**: the Python API (`fetch`/`resolve`) now works inside a running asyncio
  event loop (Jupyter / Google Colab / IPython), where it previously raised
  `asyncio.run() cannot be called from a running event loop`. The CLI was
  unaffected.

### 0.1.0 (initial release)
- First public release: faithful iSeq port + segmented engine + adaptive batch
  pool + parallel metadata resolution + adaptive Aspera + Python API.
- Validated against the **real ENA Aspera** endpoint with a genuine IBM `ascp`.
- Offline test suite (parity, engine, batch, adaptive) green; CI on Python
  3.10–3.12.

<details>
<summary>Design highlights vs iSeq</summary>

- **Segmented, resumable HTTP(S)/FTP engine** (the default) with `.part`/`.part.meta`
  resume — interrupt and re-run to continue, not restart.
- **Batch-parallel download** of accession lists through an asyncio worker pool.
- **Adaptive concurrency**: a gradient controller tunes how many downloads run at
  once from measured throughput.
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

### 1. From PyPI (once published)
```bash
pip install adaptiseq            # TBD: not yet on PyPI
pip install adaptiseq[xlsx]      # + openpyxl, for parsing GSA project XLSX
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
conda env create -f iSeq.yml && conda activate adaptiseq
```

External tools (same as iSeq): `wget` (always), `sra-tools`, `pigz`, `md5sum`,
`axel` (classic `-p`), and IBM `ascp` (`-a`). adaptiSeq requires each **only when a
run actually needs it**. Full detail: **[docs/installation.md](docs/installation.md)**.

## Example

1. Download all Runs and metadata for an accession.
```bash
adaptiseq -i PRJNA211801
```
<!-- TBD: ![e01](docs/img/e01.png) -->

2. Batch download a list, directly as gzip FASTQ, through the adaptive pool.
```bash
adaptiseq -i SRR_Acc_List.txt -g
```
<!-- TBD: ![e02](docs/img/e02.png) -->

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
  --probe-window  int           Adaptive probe window in seconds (default: 10).
  --cc-penalty    float         Worker-cost penalty K (default: 1.01).
  --meta-jobs     int           Parallelism for metadata/URL resolution (default: 3).
  --aspera-efficiency float     Keep an extra ascp worker only above this efficiency (0.70).
  -h, --help                    Show the help information.
  -v, --version                 Show the program version.
```

Display cadence defaults live in `adaptiseq/options.py`: the file-level progress
bar repaints every 2 seconds, and segmented HTTP/FTP meter lines print every 10
seconds. These do not change the adaptive probe window.

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
through an asyncio worker pool (`-j`) whose active size a gradient controller
tunes (`--adaptive`).

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
[FAQ](docs/faq.md) ·
[Benchmark](BENCHMARK.md).

## Inspired

adaptiSeq was inspired by **[iSeq](https://github.com/BioOmics/iSeq)** (which it
ports and extends), and by [fastq-dl](https://github.com/rpetit3/fastq-dl),
[fetchngs](https://github.com/nf-core/fetchngs),
[pysradb](https://github.com/saketkc/pysradb), and
[Kingfisher](https://github.com/wwood/kingfisher-download). A comparison:

| Software | Languages | Databases | Accessions | Formats | Methods | Metadata | MD5 | Resumable | Parallel | Merge | Skip done | Conda |
| -------- | --------- | --------- | ---------- | ------- | ------- | :------: | :-: | :-------: | :------: | :---: | :-------: | :---: |
| **adaptiSeq** | Python | GSA, SRA, ENA, DDBJ, GEO | All | fq, fq.gz, sra, bam | segmented http(s)/ftp, aspera, wget/axel | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | TBD (pip ✔) |
| [iSeq](https://github.com/BioOmics/iSeq) | Shell | GSA, SRA, ENA, DDBJ, GEO | All | fq, fq.gz, sra, bam | wget, axel, aspera | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| [SRA Toolkit](https://github.com/ncbi/sra-tools) | C | SRA, ENA, DDBJ | All except Run | fq, fq.gz, sra | prefetch | ❌ | ✔ | ✔ | ❌ | ❌ | ✔ | ✔ |
| [enaBrowserTools](https://github.com/enasequence/enaBrowserTools) | Python | SRA, ENA, DDBJ | All except GSA/GEO | fq, fq.gz, sra | urllib, aspera | ✔ | ✔ | ✔ | ❌ | ❌ | ✔ | ✔ |
| [fastq-dl](https://github.com/rpetit3/fastq-dl) | Python | SRA, ENA, DDBJ | All except GSA/GEO | fq, fq.gz, sra | wget | ✔ | ✔ | ❌ | ❌ | ✔ | ✔ | ✔ |
| [fetchngs](https://github.com/nf-core/fetchngs) | Python | SRA, ENA, DDBJ, GEO | All except GSA | fq, fq.gz | wget, aspera, prefetch | ✔ | ✔ | ✔ | ❌ | ❌ | ✔ | ❌ |
| [pysradb](https://github.com/saketkc/pysradb) | Python | SRA, ENA, DDBJ, GEO | All except GSA | fq, fq.gz, sra, bam | requests, aspera | ✔ | ✔ | ✔ | ❌ | ❌ | ✔ | ✔ |
| [Kingfisher](https://github.com/wwood/kingfisher-download) | Python | SRA, ENA, DDBJ | All except GSA/GEO | fq, fq.gz, sra | curl, aria2c, aspera | ✔ | ✔ | ❌ | ✔ | ❌ | ✔ | ✔ |

Beyond this matrix, adaptiSeq adds what the single-shot downloaders do not: an
**adaptive, batch-parallel** download path, **parallel metadata resolution**, a
**segmented resumable** engine, and an importable **Python API**. See
[BENCHMARK.md](BENCHMARK.md) for honest measurements (on a 35-file ENA batch,
adaptiSeq > Kingfisher > iSeq in MB/s).

## Contributing

Contributions are welcome — please open an issue for bugs/suggestions, or fork,
branch, and submit a pull request. The offline test suite runs with
`python -m pytest`.

## Cite us

TBD (manuscript in preparation). Until then, please cite **iSeq**:
Chao H, Li Z, Chen D, Chen M. *iSeq: An integrated tool to fetch public sequencing
data.* **Bioinformatics**, 2024, btae641,
[doi:10.1093/bioinformatics/btae641](https://doi.org/10.1093/bioinformatics/btae641).

## License

This project is licensed under the [MIT License](LICENSE).
