# Installation

adaptiSeq is a Python package (Python **≥ 3.10**) plus a small set of external
command-line tools it shells out to.

## 1. Install with conda (recommended)

The conda package pulls the Python dependencies **and** every external tool
(`wget`, `axel`, `pigz`, `coreutils`, `sra-tools`, and `aspera-cli` for `ascp`
plus its ENA key), so all modes work without further setup:

```bash
conda create -n adaptiseq -c conda-forge -c bioconda adaptiseq
conda activate adaptiseq
```

> **Note**
> The bioconda submission is pending. Until it is accepted, build the package
> locally from the recipe in this repository:
>
> ```bash
> conda install -n base conda-build
> conda build recipe -c conda-forge -c bioconda
> conda create -n adaptiseq -c local -c conda-forge -c bioconda adaptiseq
> ```
>
> `aspera-cli` ships a Linux x86_64 `ascp`; on other platforms `-a` is
> unavailable and the remaining modes work as usual.

## 2. Install with pip

```bash
pip install adaptiseq
```

pip installs only the Python package. Install the external tools (below)
yourself, or use conda.

## 3. Install from source (development)

```bash
git clone https://github.com/swargo98/adaptiSeq.git
cd adaptiSeq
conda env create -f environment.yml   # external tools + editable install + pytest
conda activate adaptiseq
python -m pytest -q
```

Without conda, `pip install -e '.[test]'` gives the editable install and pytest;
the external tools must then come from elsewhere.

## Packaging notes

- [`recipe/meta.yaml`](https://github.com/swargo98/adaptiSeq/blob/main/recipe/meta.yaml)
  is the bioconda recipe. It builds the released PyPI sdist, and its test step
  runs the offline test suite shipped in that sdist.
- [`environment.yml`](https://github.com/swargo98/adaptiSeq/blob/main/environment.yml)
  is the development environment for a checkout.
- CI builds the recipe and creates the development environment on every push.

## Python dependencies

Installed automatically by pip:

| Package | Why |
| ------- | --- |
| `aiohttp` (≥ 3.8) | segmented HTTP(S) engine |
| `aioftp` (≥ 0.21) | native segmented FTP transport |
| `numpy` (≥ 1.21) | gradient adaptive-concurrency controller |

## External command-line tools

adaptiSeq fetches metadata and runs integrity/conversion through a small set of
external tools. Which ones you need depends on what you ask for:

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
