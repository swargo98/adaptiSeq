# Downloading sequence data

By default `adaptiseq -i <accession>` resolves the accession, downloads every Run
it contains through the **segmented engine**, and md5-verifies each file.

```bash
adaptiseq -i PRJNA211801          # all Runs in a project
adaptiseq -i SRR7706354           # a single Run
adaptiseq -i accessions.txt       # a file of accessions (batch; see batch.md)
```

For each Run, adaptiSeq downloads, **checks the md5** against the public database,
and on mismatch retries up to **three rounds** before recording the result in
`success.log` / `fail.log`.

## `-g`, `--gzip` — direct `*.fastq.gz`

Download FASTQ directly in gzip format.

```bash
adaptiseq -i SRR1178105 -g
```

For **GSA** accessions most data is already gzip, so `-g` is effectively always
on. For **SRA/ENA/DDBJ/GEO**, adaptiSeq first tries ENA's `*.fastq.gz` mirror; if
that is unavailable it falls back to downloading the `.sra` file and converting it
with `fasterq-dump` + `pigz`.

> **Note**
> A pure ENA `*.fastq.gz` download needs only `wget` (plus `pigz` for any
> conversion). `sra-tools` is required **only if** the SRA fallback actually
> triggers — adaptiSeq then prints a clear "install sra-tools" message rather
> than failing obscurely.

## `-q`, `--fastq` — convert SRA to FASTQ

After downloading the `.sra` file, decompose it into uncompressed FASTQ with
`fasterq-dump`.

```bash
adaptiseq -i SRR1178105 -q
adaptiseq -i SRR1178105 -q -t 10      # 10 conversion threads
```

> **Note**
> `-q` is particularly useful for **single-cell** data: it can decompose a run
> into `I1/R1/R2/R3`, whereas a direct `-g` download may yield only `R1/R3`.
> Used together, `-q -g` downloads the `.sra`, converts it, then gzips the result.

## `-t`, `--threads`

Threads for SRA→FASTQ conversion and gzip compression (default **8**).

```bash
adaptiseq -i SRR1178105 -q -t 10
```

More is not always better — `fasterq-dump` is IO-heavy, and too many threads
raise CPU/IO load. A ceiling around 15 is a sensible default.

## `-d`, `--database` — force ENA or SRA

```bash
adaptiseq -i SRR1178105 -d sra
```

By default adaptiSeq auto-detects the best database, so `-d` is usually
unnecessary. Force `-d sra` when ENA is slow for a given file.

> **Note**
> If a file is not in **ENA**, adaptiSeq switches to **SRA** automatically even
> with `-d ena`.

## `-r`, `--protocol` — ENA transport

```bash
adaptiseq -i SRR7706354 -g -r https
```

For the segmented engine, ENA transport defaults to **auto (HTTPS-first)**: it
prefers the HTTPS mirror (confirmed by a cheap per-host range probe), then native
segmented FTP, then a single stream **inside** the segmented engine. Pass
`-r https` or `-r ftp` to force one.

## `-p`, `--parallel` — classic-engine parallelism

```bash
adaptiseq -i PRJNA211801 --engine classic -p 10
```

`-p` sets the **axel** connection count and applies only to the **opt-in classic
engine** (`--engine classic`). The default segmented engine already fetches each
file in multiple byte-range connections (`--max-segments`) and runs a batch
worker pool (`-j`), so `-p` is not needed there. See [Method details](../methods.md).

## `-s`, `--speed` — speed cap

```bash
adaptiseq -i SRR7706354 -g -s 50      # cap at 50 MB/s
```

Token-bucket rate limit in MB/s (default **1000**), applied by the engine.

## `-k`, `--skip-md5`

Skip md5/`vdb-validate` integrity checks. Remove `-k` and re-run to verify later.

## `-Q`, `--quiet`

Suppress the live progress bar and non-essential messages — cleaner logs for
batch/CI use.
