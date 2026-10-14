# Table 1: feature comparison

Compiled 2026-10-13 from each tool's own `--help` output, source, or current
documentation, at the versions listed. The "Evidence" section says where every
cell comes from. No cell is unresolved.

| Tool (version) | Databases | Accession list in one call | Parallel across accessions | Parallel, rate-limited resolution | md5 check | Resume partial file | Merge runs | Python API | pip / conda |
|---|---|---|---|---|---|---|---|---|---|
| **adaptiSeq** (0.1.4) | GSA, SRA, ENA, DDBJ, GEO | yes | yes (`-j`, adaptive) | yes (`--meta-jobs`) | yes | yes | yes (`-e`) | yes | pip |
| iSeq (1.9.9) | GSA, SRA, ENA, DDBJ, GEO | yes | no (one run at a time) | no | yes | yes (`wget -c`) | yes (`-e`) | no | conda |
| Kingfisher (0.5.0) | SRA, ENA, DDBJ; GSA experimental | yes | no (one run at a time) | no | optional (`--check-md5sums`) | no | no | yes | pip, conda |
| fastq-dl (4.0.1) | SRA, ENA, DDBJ | no (one accession per call) | no | no | yes | no (`wget -O`) | yes (`--group-by-*`) | no | pip, conda |
| nf-core/fetchngs (1.13.0) | SRA, ENA, DDBJ, GEO | yes | yes (Nextflow tasks) | parallel; no rate cap (waits after HTTP 429) | yes | task-level (`-resume`) | no | no | neither (Nextflow) |
| pysradb (2.5.1) | SRA, ENA, GEO | by project/experiment | yes (`--threads`) | no | no | yes (`.part`) | no | yes | pip, conda |

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

**iSeq 1.9.9** (the version in the submission benchmark env
`adaptiseq_e3_sub`; the July runs and the supplement used 1.9.8). The usage text
of 1.9.8 and 1.9.9 is identical, so no cell changes. The scripts differ in three
places: run metadata comes from NCBI E-utilities instead of the Trace back end,
the BioSample accession pattern (`SAM[EDN]...`) is widened, and for ENA gzip downloads 1.9.9 loops over every
`fastq.gz` link of a run (1.9.8 handled exactly one or two links, so runs with
three files failed). `bin/iseq` usage text: `-i` takes "a file containing multiple accessions",
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
(`_check_for_existing_files`). A partial file is not resumed: `kingfisher/ena.py`
runs `aria2c -x N -o FILE` (or `curl -L`) without a continue flag, and on a
failed download or md5 mismatch `_clean_incomplete_files` deletes the file and
its mate (checked in the installed 0.5.0 source, 2026-10-13). Also seen in the
2026-10-13 gate run: when the ENA file-report query for one run fails (curl exit
35), Kingfisher logs the error and exits, so the rest of the list is not
attempted.

**fastq-dl 4.0.1.** `fastq-dl --help`: `--accession` takes one Study, Sample,
Experiment, or Run accession; `--provider ena|sra`; `--ignore` skips md5;
`--group-by-experiment` / `--group-by-sample`; `--connections` is "HTTP
connections per file for SRA downloads". ENA files are fetched with
`wget --quiet -O` (`fastq_dl/providers/ena.py`), which restarts the file.

**nf-core/fetchngs 1.13.0** (2026-09-15, Zenodo 10.5281/zenodo.22764959; the
rate-limit cell was checked in 1.12.0 as well, Zenodo 10.5281/zenodo.10728509,
and is the same). Not run here; read from the source at the release tags on
2026-10-13. README and `docs/usage.md`: ids from SRA, ENA, DDBJ, and GEO; FASTQ
fetched "in parallel via `wget`" with an `md5sum` check;
`--download_method ftp|aspera|sratools|fastq-dl` (`fastq-dl` is new in 1.13.0,
and Synapse ids are no longer listed). Resolution is one Nextflow task per id
(`SRA_IDS_TO_RUNINFO`, called on the id channel in `workflows/fetchngs.nf`), so
lookups run concurrently, as many at once as the executor allows. Nothing caps
the request rate: no `maxForks`, `queueSize`, or `submitRateLimit` appears in
any `.nf` or `.config` file of the pipeline. The lookup script
(`bin/sra_ids_to_runinfo.py`, `fetch_url`) reacts after the fact: on HTTP 429 it
sleeps for the server's `Retry-After`, or 5 s doubling, and retries; on HTTP 500
it retries with the same backoff. The task also carries the `error_retry` label
(two Nextflow retries). By the column's definition this is parallel resolution
without a request-rate cap.

**pysradb 2.5.1.** `pysradb download --help`: `--srp`, `--srx`, `--geo`,
`--threads`, `--use_ascp`. `pysradb/download.py`: downloads to `<file>.part` and
appends from the existing size; `download_file(..., md5_hash=None)` validates
only when a hash is passed, and no caller in 2.5.1 passes one (`sradb.py` and
`geoweb.py` call it without `md5_hash`; checked in the installed source,
2026-10-13), so downloads are not md5-checked.

## The README comparison table

The README's table (written earlier) disagreed with the above in three places.
It was corrected on 2026-10-13, before the 0.1.4 wheel was rebuilt, so the paper
and the repository agree:

1. Kingfisher now has "Python API ✔" (0.5.0 exposes
   `kingfisher.download_and_extract`).
2. Kingfisher's databases now read "SRA, ENA, DDBJ, GSA (experimental)" and its
   accessions "All except GEO" (0.5.0 has experimental `ngdc-ascp` /
   `ngdc-http` methods for CRR accessions).
3. pysradb now has "Batch ✔": `pysradb download --threads N` maps the file list
   over N threads (`sradb.py`, `thread_map(..., max_workers=threads)`; the
   default is 1).
