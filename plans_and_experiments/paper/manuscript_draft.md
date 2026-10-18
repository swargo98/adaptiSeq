# adaptiSeq: complete, parallel download of public sequencing accession lists

*Draft for* Bioinformatics *(Application Note). Target: about 2,000 words, one
figure, one table, four pages.*

**Status of this draft.** The prose, structure, and methods are written. Every
result is a placeholder of the form `[[file:field]]`, to be filled from the
output of `bench/e3/analyze_submission.py` once the 0.1.5 benchmark has run.
No number from the earlier benchmark appears in the main text. Authors,
affiliations, the Zenodo DOI, and the benchmark commit are also placeholders.
The list at the end maps each placeholder to its source.

**Authors.** Rasman Mubtasim Swargo [[co-authors, affiliations, ORCIDs]]

---

## Abstract

**Summary:** Analyses that reuse public sequencing data start from a list of
accessions, often hundreds of runs. Existing download tools process such a list
one run at a time, and some omit runs whose file layout they do not expect.
adaptiSeq is a Python library and command-line tool that resolves a list of
accessions from GSA, SRA, ENA, DDBJ, and GEO concurrently under per-archive
request limits, downloads the files through a pool of workers whose size is
adjusted from measured throughput, and verifies every run against the archive's
checksum. On a 241-run project, adaptiSeq with default settings completed
[[completion.tsv:adaptiseq-default.runs_complete_median]] runs, against
[[completion.tsv:iseq.runs_complete_median]] for iSeq and
[[completion.tsv:kingfisher.runs_complete_median]] for Kingfisher, and its median
verified throughput was [[numbers.json:headline.3r.ratio_median]] times
(95% CI [[numbers.json:headline.3r.ratio_ci95_lo]] to
[[numbers.json:headline.3r.ratio_ci95_hi]]) that of the fastest other tool.
Transfers are segmented and resumable, and the same functions are available from
Python.

**Availability and implementation:** adaptiSeq is implemented in Python (3.10 or
later) and released under the MIT licence. Source: https://github.com/swargo98/adaptiSeq.
Package: https://pypi.org/project/adaptiseq/. The version described here, 0.1.5,
is archived at [[Zenodo DOI]]. Benchmark scripts, accession lists, and checksum
manifests are at [[benchmark repository and commit]].

**Contact:** [[corresponding author email]]

**Supplementary information:** Supplementary data are available at
*Bioinformatics* online.

---

## 1 Introduction

The Sequence Read Archive, the European Nucleotide Archive (ENA), the DDBJ
Sequence Read Archive, and the Genome Sequence Archive (GSA) together hold tens
of millions of sequencing runs, and reanalysis of deposited runs is routine in
transcriptomics, metagenomics, and population genomics. The unit of work in such
studies is rarely one file. A pipeline is given a project or a list of run
accessions and must obtain every run in it, intact, before any analysis starts.

Several tools download sequencing data by accession. iSeq (Chao *et al.*, 2024)
covers five databases with one interface and verifies checksums. Kingfisher
(Woodcroft *et al.*, 2024) tries several sources for each run. fastq-dl (Petit *et
al.*, 2026) retrieves FASTQ files from ENA or SRA. nf-core/fetchngs (Ewels *et al.*,
2020) wraps retrieval in a Nextflow workflow, and pysradb (Choudhary, 2019)
exposes archive metadata and downloads to Python. With the exception of
workflow-level parallelism in fetchngs, these tools handle the runs in a list
sequentially: each run is resolved to URLs and then downloaded before the next
begins. When a project has many small runs, per-run overhead dominates the
elapsed time rather than bandwidth. A second problem is completeness. A run may
have three FASTQ files instead of one or two (two mates plus unpaired or barcode
reads), and a tool that assumes one or two files can fail on it.

We present adaptiSeq, a Python reimplementation and extension of iSeq built for
accession lists. It keeps iSeq's database coverage, command-line options, and
integrity checks, and adds concurrent resolution and download, a transfer engine
ported from FastBioDL (Swargo *et al.*, 2025), correct handling of three-file
runs, and an importable interface.

## 2 Implementation

**Resolution.** For each accession adaptiSeq obtains run metadata and file
locations in the order iSeq does: the ENA Portal API first, then NCBI for runs
ENA does not mirror, and the GSA interfaces for CRA/CRR accessions. For a list,
these lookups run in a thread pool (`--meta-jobs`, default 3). Concurrency is
decoupled from request rate: every request passes a per-endpoint limiter (8
requests per second to ENA, 5 to GSA, and 3 to NCBI, or 10 when an NCBI API key
is set), so enlarging the pool cannot exceed an archive's published limit
(Supplementary Table S3).

**Batch download.** The resolved files form one queue served by an asynchronous
pool of up to `-j` workers (default 20), each holding one file. With the default
`--adaptive` setting, a controller chooses how many workers are active. It
measures aggregate throughput while stepping the worker count down from the cap,
keeps the count that gave the highest throughput, and searches again only if
throughput falls for a sustained period. A paused worker writes its progress to
disk and returns its file to the queue. Repeated refusals or HTTP 429 or 503
responses from a host halve that host's connection limit and trigger exponential
backoff. The controller is a safeguard against a poorly chosen `-j`, not an
optimiser: we do not claim that it outperforms the best fixed value
(Supplementary Table S6).

**Transfer.** Each file is fetched over HTTPS where the host supports byte
ranges, and otherwise over FTP or a single stream. A file is split into one
ranged request per 512 MB, up to eight, each written at its offset into a
`.part` file, with progress recorded in a sidecar file. An interrupted transfer therefore resumes from the recorded offsets, and a
`.part` file is renamed to its final name only when every byte is present. This
engine is ported from FastBioDL. Aspera is available for ENA and GSA.

**Integrity.** After download, every FASTQ file is compared with the MD5 that
ENA publishes, and `.sra` files are checked with `vdb-validate`. A failed run is
downloaded again, up to three times, and then recorded in `fail.log`; verified
runs are recorded in `success.log` and skipped when the command is repeated.
The exit status is non-zero if any run failed. Runs with three or more FASTQ
files are downloaded and verified in full.

**Interface.** The command line follows iSeq's
(`adaptiseq -i accessions.txt -g`), so existing commands carry over. The same
operations are importable, return values, and raise typed exceptions:

```python
from adaptiseq import fetch, resolve, get_metadata

rows = get_metadata("PRJNA916347")             # parsed run metadata
urls = resolve("SRR22904482")                  # download URLs, nothing fetched
result = fetch("accessions.txt", outdir="data", gzip=True)
if result.failed:
    print("incomplete:", result.fail_ids)
```

Table 1 compares these features with those of the other tools.

## 3 Results

**Design.** We compared adaptiSeq 0.1.5 with iSeq 1.9.9, Kingfisher 0.5.0, and
fastq-dl 4.0.1 on two public datasets chosen to stress different costs:
BioProject PRJNA916347 (241 runs, 7.6 GB, of which 40 runs have three FASTQ
files), where per-run overhead dominates, and eight runs of PRJNA762469
(25.9 GB), where bandwidth dominates. Each tool was asked for gzip-compressed
FASTQ with checksum verification on. adaptiSeq ran with no tuning options
(`adaptiseq -i LIST -g`), and once with `--no-adaptive -j 20` to show what the
controller contributes. iSeq ran with defaults and with `-p 8`. Kingfisher ran
with `-m ena-ftp aws-http prefetch --check-md5sums -f fastq.gz`. fastq-dl, which
takes one accession per call, was called once per run. Exact commands are in the
Supplementary Methods.

Each dataset was downloaded [[n reps]] times by every arm on two machines: an
exclusive 128-core node of SDSC Expanse and a 4-core virtual machine on the
FABRIC testbed. Arms ran strictly one after another, in an order drawn afresh
for every repetition, and all output was deleted between arms. A run counted as
completed only if every one of its files matched the MD5 in a manifest taken
from ENA, whatever the tool's exit status; throughput is verified megabytes
divided by elapsed seconds, which includes resolution and verification time. We
report medians with interquartile ranges, and for speed the median over
repetitions of the ratio between adaptiSeq and another arm within the same
repetition, with a percentile-bootstrap 95% confidence interval.

**Completeness.** On the 241-run project, adaptiSeq completed
[[completion.tsv:adaptiseq-default.runs_complete_median]] runs (median; range
[[completion.tsv:adaptiseq-default.runs_complete_min]] to
[[completion.tsv:adaptiseq-default.runs_complete_max]]) on Expanse and
[[same, Fabric]] on FABRIC (Fig. 1c). iSeq completed
[[completion.tsv:iseq.runs_complete_median]] and none of the 40 three-file runs
([[completion.tsv:iseq.three_file_median]] of 40), because it passes the three
URLs to `wget` as a single string. Kingfisher completed
[[completion.tsv:kingfisher.runs_complete_median]]; [[describe from
runs_present_unverified whether the shortfall is failed downloads or runs
obtained from SRA and recompressed, which cannot match ENA's checksum]].
fastq-dl completed [[completion.tsv:fastq-dl.runs_complete_median]].
[[If adaptiSeq's median is below 241, state which run failed and why.]]

**Speed.** On the 241-run project, adaptiSeq's median verified throughput was
[[summary.tsv:Expanse.3r.adaptiseq-default.MBps_median]] MB/s on Expanse and
[[summary.tsv:Fabric.3r.adaptiseq-default.MBps_median]] MB/s on FABRIC (Fig. 1a).
The fastest other arm was [[numbers.json:headline.3r.fastest_competitor]]; the
median ratio was [[numbers.json:headline.3r.ratio_median]] (95% CI
[[lo]] to [[hi]]) on Expanse and [[same, Fabric]] on FABRIC. On the eight large
runs (Fig. 1b) the corresponding ratios were
[[numbers.json:headline.3b.ratio_median]] ([[lo]] to [[hi]]) and [[same,
Fabric]], against [[numbers.json:headline.3b.fastest_competitor]]. The gain is
larger where files are small, as expected when the saving comes from
overlapping per-run overhead. The default configuration and the fixed
20-worker configuration differed by a ratio of
[[ratios.tsv:adaptiseq-fixed-j20.ratio_median]] ([[lo]] to [[hi]]).

**Reliability.** In separate tests (Supplementary Tables S1 and S2), a transfer
killed at 25%, 50%, or 75% resumed without re-downloading completed bytes, a
connection dropped mid-file never produced a truncated output file, and a
corrupted byte was detected and repaired. iSeq also resumed correctly.

## 4 Limitations

Both test machines are in the United States, and throughput from the archives
varies with location and time of day; the ratios above describe these two
vantage points. Five repetitions give wide confidence intervals. The comparison
concerns accession lists: for a single large file, a multi-connection downloader
such as aria2c is as fast or faster. The adaptive controller prevents the
throughput collapse we observed with an oversized fixed worker count, but it does
not exceed a well-chosen fixed setting. The completeness test covers one
project of 241 runs. adaptiSeq is distributed through PyPI and not yet through
Bioconda, and it relies on external programs (`wget`, and sra-tools and `pigz`
when conversion is needed).

## Acknowledgements

adaptiSeq is derived from iSeq (Chao *et al.*, 2024), whose behaviour it
reproduces, and its transfer engine from FastBioDL. [[Compute acknowledgements:
ACCESS/Expanse allocation and FABRIC, with their required wording.]]

## Funding

[[Funding statement.]]

## Data availability

The accession lists, checksum manifests, benchmark scripts, raw result tables,
and analysis script are available at [[benchmark repository and commit]]. All
sequencing data are public in ENA and SRA under the accessions listed there.

## References

Kingfisher, fastq-dl, pysradb, nf-core, and iSeq entries were checked on
2026-10-13 against Crossref, Zenodo, and each project's citation file. The
FastBioDL author order and the archive references still need checking.

- Chao H, Li Z, Chen D, Chen M. iSeq: an integrated tool to fetch public
  sequencing data. *Bioinformatics* 2024;40(11):btae641.
  doi:10.1093/bioinformatics/btae641
- Choudhary S. pysradb: a Python package to query next-generation sequencing
  metadata and data from NCBI Sequence Read Archive. *F1000Research* 2019;8:532.
  doi:10.12688/f1000research.18676.1
- Ewels PA, Peltzer A, Fillinger S *et al.* The nf-core framework for
  community-curated bioinformatics pipelines. *Nat Biotechnol* 2020;38:276-8.
  doi:10.1038/s41587-020-0439-x
- nf-core/fetchngs v1.12.0. Zenodo, 2024. doi:10.5281/zenodo.10728509
  (author list: take from the Zenodo record)
- Petit RA III, Hall MB, Tonkin-Hill G *et al.* fastq-dl: efficiently download
  FASTQ files from SRA or ENA repositories. v4.0.1. Zenodo, 2026.
  doi:10.5281/zenodo.8051230
- Swargo RM, Arslan E, Arifuzzaman M. Adaptive parallel downloader for large
  genomic datasets. arXiv:2508.05511, 2025. (verify author order)
- Woodcroft BJ, Cunningham M, Gans JD, Bolduc BB, Hodgkins SB. Kingfisher: a
  utility for procurement of public sequencing data. Zenodo, 2024.
  doi:10.5281/zenodo.10525085
- Archive references for SRA, ENA, DDBJ, and GSA (the current *Nucleic Acids
  Research* database-issue papers). (add)

---

## Table 1

See `table1_features.md`.

## Figure 1 legend

**Fig. 1.** Download of accession lists by adaptiSeq 0.1.5 and three other tools
on two machines (circles, SDSC Expanse; squares, FABRIC). **(a)** Verified
throughput on 241 runs totalling 7.6 GB. **(b)** Verified throughput on 8 runs
totalling 25.9 GB. Large markers are medians over [[n reps]] repetitions, bars
are interquartile ranges, small markers are individual repetitions; the
horizontal axis is logarithmic. Throughput counts only bytes whose MD5 matched
ENA's. **(c)** Median number of the 241 runs completed with every file verified;
the lighter segment is the 40 runs that have three FASTQ files, and the vertical
line marks 241.

---

## Placeholder map

| Placeholder | Source |
|---|---|
| `[[completion.tsv:ARM.field]]` | `completion.tsv`, row for that arm and machine |
| `[[summary.tsv:MACHINE.PANEL.ARM.field]]` | `summary.tsv` |
| `[[ratios.tsv:ARM.field]]` | `ratios.tsv`, reference arm `adaptiseq-default` |
| `[[numbers.json:headline.PANEL.field]]` | `numbers.json`, `headline_vs_fastest_competitor` |
| `[[n reps]]` | `n_reps` in any of the tables (planned: 5) |
| `[[Zenodo DOI]]` | created when the 0.1.5 tag is archived |
| `[[benchmark repository and commit]]` | chosen when the benchmark files are published |

Panel `3r` is the 241-run project and `3b` is the eight large runs.

## Word count

Main text (Introduction to Limitations, without the code block) is about 1,300
words with placeholders unfilled; the abstract is about 200. The plan's budget is
about 2,000 words, so roughly 600 words remain for the filled-in results and for
anything the data make necessary to explain.
