# Merging FASTQ (`-e`)

Merge the FASTQ files of multiple Runs into one file per **Experiment** (`ex`),
**Sample** (`sa`), or **Study** (`st`).

```bash
adaptiseq -i SRX003906 -g -e ex
```

Most Experiments contain a single Run, but some span several (e.g.
[SRX003906](https://www.ebi.ac.uk/ena/browser/view/SRX003906),
[CRX020217](https://ngdc.cncb.ac.cn/gsa/search?searchTerm=CRX020217)). `-e` merges
them in a **consistent order** so paired-end `_1`/`_2` files stay aligned.

- `-e ex` — merge all FASTQ of the same **Experiment**. Accepts `ERX, DRX, SRX, CRX`.
- `-e sa` — merge all FASTQ of the same **Sample**. Accepts `ERS, DRS, SRS, SAMC, GSM`.
- `-e st` — merge all FASTQ of the same **Study**. Accepts `ERP, DRP, SRP, CRA`.

Output:

- **single-end** → `SRX*.fastq.gz`
- **paired-end** → `SRX*_1.fastq.gz` and `SRX*_2.fastq.gz`

> **Note 1**
> `-e` cannot be used when the input accession is a **Run ID**. adaptiSeq merges
> gzip-compressed and uncompressed FASTQ, but not BAM or `tar.gz` files.

> **Note 2**
> When an Experiment has one Run and the Run's files share its prefix, adaptiSeq
> renames them directly to `SRX*_1.fastq.gz` / `SRX*_2.fastq.gz`. When a Run's
> files use different prefixes (e.g. `CRX006713`/`CRR007192`), they are renamed as
> `SRX*_<original_filename>`.

> **Note 3 (parity)**
> Merge logic is a faithful port of `iseq` — the same inputs produce the same
> merged bytes. adaptiSeq's engine changes only *how* the per-Run files are
> fetched, never their contents.
