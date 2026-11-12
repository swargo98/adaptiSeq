# FAQ

## `wget can not be found in your PATH ...`

adaptiSeq needs `wget` for metadata/discovery. Install it (e.g.
`conda install -c conda-forge wget`) and re-run. The same message appears for any
other required tool the run actually needs.

## `srapath can not be found in your PATH ...` on a `-g` run

A direct ENA `*.fastq.gz` download needs only `wget`. You see this only when the
run **fell back to the SRA path** (the file was not on ENA). Install `sra-tools`:

```bash
conda install -c bioconda 'sra-tools>=2.11.0'
```

adaptiSeq checks `srapath` / `fasterq-dump` **lazily** — only when the SRA
fallback is actually taken — so a pure-ENA workflow stays tool-light. (A missing
`srapath` used to be mis-reported as "not available in all databases"; it now
gives this clear message instead.)

## `fasterq-dump can not be found ...` during conversion

The run downloaded a `.sra` file and needs to convert it (`-q`, `-e`, or `-g`
falling back to SRA). Install `sra-tools` (as above).

## A download is slow

- Try forcing the SRA database: `-d sra` (or `-d ena`).
- Try a different ENA transport: `-r https` or `-r ftp`.
- For ENA/GSA, try Aspera: `-a` (needs a real `ascp` + key).
- Raise/lower batch concurrency: `-j N`, or pin it with `--no-adaptive`.

## `NCBI rate limit` / slow metadata for big batches

NCBI E-utilities allows 3 req/s without a key, 10 with one. Export a key:

```bash
export NCBI_API_KEY=your_key_here
export NCBI_EMAIL=you@example.com    # optional
```

## Aspera (`-a`) transfers nothing / authentication fails

- Ensure a **real IBM `ascp`** is on `PATH` (a no-op stub passes startup checks
  but transfers nothing).
- Ensure a key file exists (adaptiSeq searches the conda env and `~/.aspera`).
- ENA migrated DSA→RSA Aspera keys; the legacy `asperaweb_id_dsa.openssh` is
  rejected. adaptiSeq's RSA fallback covers this automatically.

## A file failed its md5 check

adaptiSeq retries up to **three rounds**, then records the Run in `fail.log` and
deletes the corrupt partial. Re-run the command to retry. To skip checks entirely
use `-k/--skip-md5` (then re-run without `-k` to verify later).

## A Run came from SRA, not ENA. Why?

ENA's portal API sometimes fails or returns nothing for a Run, and some Runs are only in NCBI SRA.
adaptiSeq retries a failed ENA query for up to about three minutes before it falls back, announces
the fallback (`N accession(s) had no usable ENA metadata and will be downloaded from SRA`), and counts
the Run as delivered: its converted FASTQ is validated, but it cannot be compared with ENA's md5. If every
kept file must match ENA's md5, add `--no-sra-fallback`: such a Run then fails, goes to `fail.log`, and
the exit status is 1; re-run later.

## What does the exit status mean?

`0` when every requested Run was delivered; `1` when any Run failed (named in `fail.log`) or the
command could not run. In a list, one failing accession does not stop the rest.

## Which `--controller` should I use?

Leave the default (`topdown`) unless you have a reason. `greedy` runs every worker and backs off on
HTTP 429/503; `budget` and `knee` hold the fewest connections that give good speed, to load an archive
less; `bottomup` is the original gradient optimizer. See [Adaptive controller](ADAPTIVE_CONTROLLER.md).

## How do I re-download something already in `success.log`?

Remove its line and re-run:

```bash
sed -i -E '/[[:space:]]SRR7706354([^A-Za-z0-9]|$)/d' success.log
```

## Does `-p` work with the default engine?

No. `-p` (axel connection count) applies only to `--engine classic`. The default
segmented engine uses `--max-segments` (per-file ranges) and `-j` (batch pool)
instead.

## Can I use adaptiSeq as a library?

Yes — `from adaptiseq import fetch, resolve, get_metadata`. See the
[Python API](usage/python-api.md).

## Is the output correct?

Resolution, metadata, integrity, logs, and merge are covered by a differential
test suite that checks adaptiSeq's output against stored reference fixtures. The
engine changes only *how* bytes are transferred, never *which* bytes are written.
3-file runs (orphan/barcode + `_1` + `_2`) are downloaded correctly (iSeq 1.9.8 did not
download them; later iSeq releases do).
