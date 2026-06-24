# Installation

adaptiSeq is a Python package (Python **≥ 3.10**) plus a small set of external
command-line tools it shells out to (the same ones `iseq` uses).

## 1. Install with pip (recommended)

```bash
pip install adaptiseq            # once published to PyPI
pip install adaptiseq[xlsx]      # + openpyxl, to parse GSA project XLSX in the API
```

> **Note**
> adaptiSeq is not yet on PyPI/bioconda. Until then, install from source (below).

## 2. Install from source

```bash
git clone https://github.com/swargo98/adaptiSeq.git
cd adaptiSeq
pip install -e .                 # editable / development install
pip install -e '.[test]'         # + pytest, to run the test suite
adaptiseq --version
```

## 3. Conda environment

A conda environment file ([`iSeq.yml`](../iSeq.yml)) is provided that pulls both
the external tools and the Python dependencies:

```bash
conda env create -f iSeq.yml
conda activate adaptiseq
```

A dedicated `bioconda` package is **TBD**.

## Python dependencies

Installed automatically by pip:

| Package | Why |
| ------- | --- |
| `aiohttp` (≥ 3.8) | segmented HTTP(S) engine |
| `aioftp` (≥ 0.21) | native segmented FTP transport |
| `numpy` (≥ 1.21) | gradient adaptive-concurrency controller |
| `openpyxl` (≥ 3.0) | *optional* (`[xlsx]`) — parse GSA project XLSX in the library API |

## External command-line tools

adaptiSeq fetches metadata and runs integrity/conversion through the same
external tools as `iseq`. Which ones you need depends on what you ask for:

| Tool | Needed for |
| ---- | ---------- |
| `wget` | metadata / discovery (**always**) |
| `sra-tools` (`srapath`, `fasterq-dump`, `vdb-validate`) | SRA-fallback resolution, FASTQ conversion, md5/validation |
| `pigz` | gzip compression after conversion (`-g`/`-q`) |
| `md5sum` (coreutils) | md5 integrity checks (skipped with `-k`) |
| `axel` | only the opt-in classic engine with `-p` |
| IBM `ascp` (Aspera) | only `-a` |

adaptiSeq uses **needs-based preflight**: a pure ENA `*.fastq.gz` download needs
only `wget` — `sra-tools` and the rest are required (with a clear message) only
when a run actually takes a path that uses them. See the [FAQ](faq.md) for the
exact messages and how to resolve them.

## Verifying the install

```bash
adaptiseq --version
adaptiseq -i SRR7706354 -m          # metadata-only smoke test
```
