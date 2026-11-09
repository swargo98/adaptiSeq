# Comparison with other tools

adaptiSeq sits among other downloaders for public sequencing data:
[iSeq](https://github.com/BioOmics/iSeq), [Kingfisher](https://github.com/wwood/kingfisher-download),
[fastq-dl](https://github.com/rpetit3/fastq-dl), [fetchngs](https://github.com/nf-core/fetchngs) and
[pysradb](https://github.com/saketkc/pysradb). The first table is the one in the adaptiSeq manuscripts;
the cells were read from each tool's help output, source and documentation at the versions shown.

**Features compared in the paper** (Table I of the manuscript; versions as benchmarked, read from each
tool's help output, source and documentation):

| Feature | adaptiSeq 0.1.12 | iSeq 1.9.9 | Kingfisher 0.5.0 | fastq-dl 4.0.1 | fetchngs 1.13.0 | pysradb 2.5.1 |
| ------- | :--------------: | :--------: | :--------------: | :------------: | :-------------: | :-----------: |
| Accession list in one call | ✔ | ✔ | ✔ | – | ✔ | project |
| Several runs at once | **✔** | – | – | – | ✔ | ✔ |
| Rate-limited parallel resolution | **✔** | – | – | – | no cap | – |
| MD5 check | ✔ | ✔ | optional | ✔ | ✔ | – |
| Resume partial file | ✔ | ✔ | – | – | per task | ✔ |
| Merge runs | ✔ | ✔ | – | ✔ | – | – |
| Python API | **✔** | – | ✔ | – | – | ✔ |
| GSA | ✔ | ✔† | experimental | – | – | – |
| GEO | ✔ | ✔† | – | – | ✔ | ✔ |
| Installation | pip, conda | conda | pip, conda | pip, conda | Nextflow | pip, conda |

† iSeq 1.9.9 lists GSA and GEO, but in our tests on 2026-10-19 its GSA run ended with exit status 0 and no data
file, and its GEO accession was rejected, after both archives added browser checks to the pages iSeq reads.
adaptiSeq reads GSA's run-info table and resolves GEO through NCBI E-utilities instead.

**More detail** (not in the paper's table):

| Software | Language | Databases | Accessions | Formats | Methods | Metadata | Several connections per file | Adaptive | Skip done |
| -------- | -------- | --------- | ---------- | ------- | ------- | :------: | :--------------------------: | :------: | :-------: |
| **adaptiSeq** | Python | GSA, SRA, ENA, DDBJ, GEO | All | fq, fq.gz, sra, bam | segmented http(s)/ftp, aspera, wget/axel | ✔ | ✔ | **✔** | ✔ |
| [iSeq](https://github.com/BioOmics/iSeq) | Shell | GSA†, SRA, ENA, DDBJ, GEO† | All | fq, fq.gz, sra, bam | wget, axel, aspera | ✔ | ✔ (`-p`) | – | ✔ |
| [Kingfisher](https://github.com/wwood/kingfisher-download) | Python | SRA, ENA, DDBJ, GSA (experimental) | All except GEO | fq, fq.gz, sra | curl, aria2c, aspera | ✔ | ✔ (`--download-threads`) | – | ✔ |
| [fastq-dl](https://github.com/rpetit3/fastq-dl) | Python | SRA, ENA, DDBJ | All except GSA/GEO | fq, fq.gz, sra | wget | ✔ | SRA only (`--connections`) | – | ✔ |
| [fetchngs](https://github.com/nf-core/fetchngs) | Nextflow | SRA, ENA, DDBJ, GEO | All except GSA | fq, fq.gz | wget, aspera, prefetch | ✔ | – | – | ✔ |
| [pysradb](https://github.com/saketkc/pysradb) | Python | SRA, ENA, GEO | Study, Experiment, GEO | fq, fq.gz, sra, bam | requests, aspera | ✔ | – | – | ✔ |

> **Several runs at once** = many accessions downloaded in parallel in one run, not one after another ·
> **Rate-limited parallel resolution** = accession-to-URL lookups run concurrently under a per-endpoint
> request-rate cap · **Adaptive** = a controller that tunes the number of concurrent downloads from measured
> throughput · **Python API** = an importable library (`fetch`/`resolve`/`get_metadata`), not only a command-line tool.
> The SRA Toolkit and enaBrowserTools are not compared here.

In this comparison no other tool combines batch download, adaptive concurrency and a Python API. For
measurements on a list of 241 runs and one of 8 large runs (speed, completeness and exit status against
iSeq, Kingfisher and fastq-dl), see the manuscripts and the benchmark record in the repository's
`combined-exp-data` branch.
