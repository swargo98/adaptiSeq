# Table 1: feature comparison

Compiled 2026-10-13 from each tool's own `--help` output, source, or current
documentation, at the versions listed. The "Evidence" section says where every
cell comes from. Cells marked `?` could not be confirmed from a primary source
and must be checked before submission (see `../remaining_tasks.md`).

| Tool (version) | Databases | Accession list in one call | Parallel across accessions | Parallel, rate-limited resolution | md5 check | Resume partial file | Merge runs | Python API | pip / conda |
|---|---|---|---|---|---|---|---|---|---|
| **adaptiSeq** (0.1.4) | GSA, SRA, ENA, DDBJ, GEO | yes | yes (`-j`, adaptive) | yes (`--meta-jobs`) | yes | yes | yes (`-e`) | yes | pip |
| iSeq (1.9.8) | GSA, SRA, ENA, DDBJ, GEO | yes | no (one run at a time) | no | yes | yes (`wget -c`) | yes (`-e`) | no | conda |
| Kingfisher (0.5.0) | SRA, ENA, DDBJ; GSA experimental | yes | no (one run at a time) | no | optional (`--check-md5sums`) | ? | no | yes | pip, conda |
| fastq-dl (4.0.1) | SRA, ENA, DDBJ | no (one accession per call) | no | no | yes | no (`wget -O`) | yes (`--group-by-*`) | no | pip, conda |
| nf-core/fetchngs (1.12.0) | SRA, ENA, DDBJ, GEO | yes | yes (Nextflow tasks) | ? | yes | task-level (`-resume`) | no | no | neither (Nextflow) |
| pysradb (2.5.1) | SRA, ENA, GEO | by project/experiment | yes (`--threads`) | no | ? | yes (`.part`) | no | yes | pip, conda |

Column definitions, to print under the table:

- **Accession list in one call**: the tool accepts a file or list of run
  accessions in a single invocation.
- **Parallel across accessions**: more than one run is downloaded at the same
  time. Several connections to one file (iSeq `-p`, Kingfisher
  `--download-threads`, fastq-dl `--connections`) do not count.
- **Parallel, rate-limited resolution**: accession-to-URL lookups run
  concurrently under a per-endpoint request-rate cap.
- **Resume partial file**: an interrupted file continues from its byte offset
  instead of restarting.

## Evidence

**adaptiSeq 0.1.4.** `adaptiseq --help`; `adaptiseq/batch.py` (worker pool,
`resolve_all`), `adaptiseq/ratelimits.py` (ENA 8, GSA 5, NCBI 3 or 10 requests/s),
`adaptiseq/engine/segmented.py` (`.part` + `.part.meta`), `adaptiseq/__init__.py`
(`fetch`, `resolve`, `get_metadata`). On PyPI; not on Bioconda.

**iSeq 1.9.8** (the version benchmarked; Bioconda now carries 1.9.9).
`bin/iseq` usage text: `-i` takes "a file containing multiple accessions",
`-p` is "the number of connections" for one file, `-k` skips the md5 check,
`-e` merges, `-d ena|sra`. It is a Bash script with no importable interface.
Resume from offset was observed in E7b (Supplementary Table S1). Bioconda:
`iseq`. The PyPI project named `iseq` is unrelated.

**Kingfisher 0.5.0.** `kingfisher get --full-help`: `--run-identifiers-list`,
`-p/--bioprojects`; methods `ena-ftp`, `ena-ascp`, `aws-http`, `prefetch`,
`aws-cp`, `gcp-cp`, and `ngdc-ascp` / `ngdc-http` marked "[Experimental] ... For
CRR accessions"; `--check-md5sums` is "only implemented for ena-ftp, ena-ascp and
aws-http" and is off by default; `--download-threads` is connections per file
(aria2c). Runs are processed in a loop (`kingfisher/__init__.py`,
`download_and_extract` calls `download_and_extract_one_run` per run), and the
same functions are importable. It skips runs whose output already exists
(`_check_for_existing_files`); whether a *partial* file is resumed depends on
aria2c's control file and is not documented: `?`.

**fastq-dl 4.0.1.** `fastq-dl --help`: `--accession` takes one Study, Sample,
Experiment, or Run accession; `--provider ena|sra`; `--ignore` skips md5;
`--group-by-experiment` / `--group-by-sample`; `--connections` is "HTTP
connections per file for SRA downloads". ENA files are fetched with
`wget --quiet -O` (`fastq_dl/providers/ena.py`), which restarts the file.

**nf-core/fetchngs 1.12.0** (the latest release; the repository's dev branch
reports 1.13.0). From the pipeline documentation: ids from SRA, ENA, DDBJ, GEO
(and Synapse), md5 check on downloaded FASTQ, `--download_method ftp|aspera|sratools`.
Not run here. Whether id resolution is rate-limited is not stated: `?`.

**pysradb 2.5.1.** `pysradb download --help`: `--srp`, `--srx`, `--geo`,
`--threads`, `--use_ascp`. `pysradb/download.py`: downloads to `<file>.part` and
appends from the existing size; `download_file(..., md5_hash=None)` validates
only when a hash is passed, and whether the `download` command passes one was
not traced: `?`.

## Differences from the README comparison table

The README's table (written earlier) disagrees with the above in three places.
It should be updated in the same release so the paper and the repository agree:

1. Kingfisher is listed without a Python API. 0.5.0 exposes
   `kingfisher.download_and_extract`.
2. Kingfisher is listed as "All except GSA/GEO". 0.5.0 has experimental
   `ngdc-ascp` / `ngdc-http` methods for CRR accessions.
3. fetchngs is listed with "Batch ✔" but pysradb is not, although
   `pysradb download --threads` downloads several files at once.
