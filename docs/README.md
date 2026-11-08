<img class="hero-logo" src="assets/logo.png" alt="adaptiSeq">

# adaptiSeq documentation

**adaptiSeq** is a fast, importable tool for fetching public sequencing data and
metadata from **[GSA](https://ngdc.cncb.ac.cn/gsa/)**,
**[SRA](https://www.ncbi.nlm.nih.gov/sra/)**,
**[ENA](https://www.ebi.ac.uk/ena/)**,
**[DDBJ](https://www.ddbj.nig.ac.jp/)**, and **[GEO](https://www.ncbi.nlm.nih.gov/geo/)**.
It accepts any standard accession (Project / Study / BioSample / Sample /
Experiment / Run, plus GEO `GSE`/`GSM`), resolves it across databases, downloads
the sequence files with a **segmented, resumable, self-tuning** engine, verifies
integrity, and optionally converts and merges FASTQ.

adaptiSeq is a tested Python tool with a batch-parallel download path built for the
workload real pipelines actually have: **lists of accessions**, downloaded
concurrently, from a script, notebook, or the shell.

> **Note**
> To use adaptiSeq your system must be **connected to the network** and able to
> reach the databases over **HTTP, HTTPS, and (optionally) FTP / Aspera**.

## Contents

- [Installation](installation.md) — pip, source, conda, and external tools
- **Usage**
  - [Usage overview](usage/README.md) — the command, the three things it does
  - [Downloading sequence data](usage/download.md) — `-g`, `-q`, `-d`, `-r`, `-p`
  - [Fetching metadata](usage/metadata.md) — `-m`
  - [Merging FASTQ](usage/merge.md) — `-e`
  - [Batch & adaptive download](usage/batch.md) — `-j`, `--adaptive`, `--meta-jobs`
  - [Aspera](usage/aspera.md) — `-a`
  - [Python API](usage/python-api.md) — `fetch`, `resolve`, `get_metadata`
- [Method details](methods.md) — the transports and engines, and how one is chosen
- [Examples](examples.md) — worked, copy-pasteable commands
- [FAQ](faq.md) — common errors and how to solve them

## The three things adaptiSeq does

| Mode | Flag | Output |
| ---- | ---- | ------ |
| Fetch metadata | `-m` | `${accession}.metadata.tsv` (or `.csv` + `.xlsx` for GSA) |
| Download sequence data | *(default)* / `-g` / `-q` | `.sra` or `*.fastq.gz`, md5-verified |
| Convert / merge | `-q` / `-e` | FASTQ (per Run) or merged FASTQ (per Experiment/Sample/Study) |

Every Run is **md5-checked** against the public database; on mismatch adaptiSeq
retries up to **three rounds**, recording successes in `success.log` and failures
in `fail.log`.

## Quick links

- Repository: <https://github.com/swargo98/adaptiSeq>
- Citation: see [Citation](#citation)

## Citation

A manuscript is in preparation. adaptiSeq builds on two earlier tools; if you use
it, please also cite:

- **iSeq**, whose accession resolution, metadata, integrity, and merge behaviour
  adaptiSeq reimplements in Python: Chao H, Li Z, Chen D, Chen M. *iSeq: An
  integrated tool to fetch public sequencing data.* **Bioinformatics**, 2024,
  btae641, [doi:10.1093/bioinformatics/btae641](https://doi.org/10.1093/bioinformatics/btae641).
- **FastBioDL**, from which the segmented, resumable transfer engine is ported:
  Swargo RM, Arslan E, Arifuzzaman M. *Adaptive Parallel Downloader for Large
  Genomic Datasets.* [arXiv:2508.05511](https://arxiv.org/abs/2508.05511).

## License

adaptiSeq is released under the [MIT License](https://github.com/swargo98/adaptiSeq/blob/main/LICENSE),
which also reproduces iSeq's MIT notice (Copyright (c) 2024 BioOmics).
