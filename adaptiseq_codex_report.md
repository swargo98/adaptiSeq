# adaptiSeq Codex Readiness Report

Date: 2026-06-14 UTC  
Scope reviewed: `adaptiseq/`, `tests/`, `bench/`, `pyproject.toml`, `README.md`, `BENCHMARK.md`, `CHANGES_FROM_ISEQ.md`, `NOTES.md`, `iSeq-main/`, `papers/btae641.pdf`, and `papers/FastBioDL___eScience26 (4).pdf`.

## Executive Verdict

adaptiSeq is a serious implementation, not just a sketch. The codebase has a clean Python package structure, a mostly faithful iSeq port, a segmented HTTP/FTP engine, adaptive batch scheduling, endpoint rate limiters, live progress, and an adaptive Aspera path tested with a fake `ascp`. The offline test suite is healthy: `ADAPTISEQ_NO_NETWORK=1 pytest` passed with `126 passed, 6 skipped`.

It is not ready for package release yet. The core code is close enough that this is mostly a release-hardening and evidence problem, but there are several visible blockers: stale rebrand metadata, contradictory CLI/docs around protocol and fallback behavior, no root `LICENSE`, an incomplete source distribution test payload, missing CI/release automation, no `twine check` validation, and several live paths that have not been exercised.

It is also not yet publication-ready as an iSeq-plus-FastBioDL paper. The current benchmark is useful but too small: 35 small runs totaling about 89 MB on one machine. The iSeq paper used broader database/functionality evidence, and FastBioDL requires multi-testbed, multi-workload, repeated download-only systems benchmarks. A paper should not claim FastBioDL-level adaptive performance until those experiments are run.

## What The Two Papers Contribute

### iSeq Contributions From `btae641.pdf`

The Bioinformatics iSeq paper positions iSeq as an integrated retrieval tool rather than a downloader alone. The required contribution surface is:

- Multi-database retrieval for GSA, SRA, ENA, DDBJ, and GEO-derived accessions.
- Support for Project, Study, BioSample, Sample, Experiment, and Run identifiers, with over 25 accession formats.
- Metadata download from ENA/SRA/GSA with GSA CSV plus project XLSX.
- Source selection among ENA FTP, SRA/AWS HTTPS, GSA FTP, and GSA Huawei Cloud.
- Wget, AXEL, and Aspera modes.
- Direct `.fastq.gz` download when available, SRA download otherwise.
- `fasterq-dump` conversion and `pigz` compression.
- Experiment/Sample/Study FASTQ merge behavior.
- MD5 or `vdb-validate` integrity checks, retry, `success.log`, and `fail.log`.
- Performance evidence across iSeq, SRA Toolkit, pysradb, edgeturbo, Wget, AXEL, Aspera, cloud endpoints, and thread scaling.
- Large stability evidence: 3000 GSA gzip FASTQ files and 3000 INSDC/SRA files with integrity verification.

### FastBioDL Contributions From `FastBioDL___eScience26 (4).pdf`

FastBioDL is a systems contribution focused on repository-object retrieval:

- Byte-range segmented download over standard HTTP(S) and FTP endpoints.
- Per-object resume via segment metadata and atomic progress updates.
- Runtime measurement of aggregate throughput.
- Utility-guided online control of active worker count, with a concurrency penalty `K`.
- Separation of URL resolution from transfer optimization.
- Benchmarks on public SRA workloads across Expanse, FABRIC, and a laboratory server.
- Controlled byte-range-server experiments isolating segmentation, adaptive worker control, and comparison with aria2c/curl.
- Sensitivity analysis for `K`.

## Implementation Status

### Strongly Implemented

- The package is importable as `adaptiseq` and exposes `fetch`, `resolve`, and `get_metadata`.
- The CLI mirrors iSeq's main user-facing flags and adds segmented/adaptive flags.
- iSeq accession routing, metadata fetching, URL resolution, integrity, conversion, merge, and logging are split into focused modules.
- Metadata fetching intentionally shells to `wget` for byte-level parity with iSeq.
- Classic Wget/AXEL/Aspera transport exists behind a fetch seam.
- Segmented HTTP(S) supports range probing, strict `206` validation, `.part` and `.part.meta` resume, `os.pwrite`, and single-stream fallback.
- Native segmented FTP is implemented with `aioftp`.
- The default engine is segmented, with HTTPS-first same-host upgrade for ENA FTP URLs.
- A per-host connection cap, circuit breaker, and token-bucket speed limiter exist.
- Batch download uses an asyncio worker pool with adaptive worker gating.
- Parallel metadata/URL resolution exists with per-endpoint rate limiters for ENA, NCBI, and GSA.
- The adaptive optimizer is tested on synthetic throughput curves.
- A progress bar reports file count, instantaneous throughput, and active workers.
- Adaptive Aspera has a file-boundary hysteresis controller and fake-`ascp` tests.
- A live/canary test structure exists, and offline tests skip network-dependent cases cleanly.

### Partially Implemented Or Claim Needs Tightening

- `resolve_all()` supports an `on_task` callback, but `core._batch_download_phase()` first resolves all tasks and only then starts `BatchDownloader`. Current implementation does not overlap resolution and download, despite README/CHANGES text saying tasks stream into the download queue.
- GSA resolution code exists inside `batch._resolve_one()`, but the main batch path explicitly excludes GSA accessions. GSA is sequential today.
- Adaptive control is file-owner concurrency, not a global segment scheduler. This is defensible and documented in places, but publication text must be precise.
- Adaptive Aspera is not validated against real ENA or GSA Aspera service behavior.
- The FastBioDL-style optimizer starts its trajectory at worker count 1 internally while the gate initially activates 2 workers. This may be okay, but it differs from the paper's stated initial count and should be justified or aligned before publication.
- Batch downloader failures are returned from `BatchDownloader.run()` but ignored by `core._batch_download_phase()` except indirectly through the later per-accession verification loop. This may be semantically fine, but benchmark logs should expose those failures explicitly.

## Evidence Collected In This Review

- Offline tests: `ADAPTISEQ_NO_NETWORK=1 pytest` -> `126 passed, 6 skipped in 39.73s`.
- Build check: `python3 -m build --outdir /tmp/adaptiseq-dist` succeeded and produced both `adaptiseq-0.1.0.tar.gz` and `adaptiseq-0.1.0-py3-none-any.whl`.
- Build warning: setuptools warns that `project.license` as a TOML table is deprecated; use an SPDX string and license files.
- `twine` is not installed in the environment, so `twine check` has not been run.
- Git worktree status after review: only `papers/` is untracked.
- Existing benchmark evidence: `bench/results_batch.tsv` reports one 35-run PRJNA916347 subset, about 89 MB, where `adaptiseq --no-adaptive` and `adaptiseq --adaptive` beat stock iSeq and Kingfisher on that small batch. This is useful but not enough for publication claims.

## Release Blockers Before Package Release

### 1. Rebrand And Metadata Cleanup

- Update `pyproject.toml` summary. It still says Part 1/classic behavior even though segmented/adaptive are now default.
- Update `pyproject.toml` Homepage. It still points to `https://github.com/swargo98/adaptiFetch`.
- Decide the canonical spelling everywhere: likely project/display name `adaptiSeq`, package/CLI `adaptiseq`.
- Remove stale `adaptiFetch` references in `PART4_PLAN.md` and `bench/benchmark_batch.sh`.
- Update `iSeq.yml` comments: it says "Parts 1-2" and "light Python additions for Parts 1-2" even though it includes `numpy` for Part 3.
- Remove duplicated "Version mapping" section in `CHANGES_FROM_ISEQ.md`.
- Decide whether plan files belong in a release package or should be archived as development notes.

### 2. License And Attribution

- Add a root `LICENSE` file for adaptiSeq. The package declares MIT, but only `iSeq-main/LICENSE` exists.
- Add explicit derivative attribution to iSeq in package metadata and README.
- Add citation guidance for both Chao et al. iSeq and the FastBioDL paper/manuscript.
- Change `license = { text = "MIT" }` to a modern SPDX form, for example `license = "MIT"`, plus `license-files`.
- Verify whether FastBioDL code contributions have a compatible license or require a separate notice.

### 3. CLI And Documentation Contradictions

- `adaptiseq/cli.py` says `--protocol` default is `ftp`; actual behavior defaults to `auto`.
- `adaptiseq/cli.py` says segmented "falls back to classic per-host"; current `engine/seam.py` explicitly does not auto-fall back to classic.
- `adaptiseq/engine/seam.py` and `adaptiseq/engine/classic.py` docstrings still mention classic fallback paths that the current policy removed.
- README says transport selection falls back to `--engine classic` in one place and "never auto-falls-back to classic" in another.
- CHANGES contains old Part 1/Part 2 text that now contradicts Part 4 policy.
- README installation text says Part 1 has no runtime dependencies; current package requires `aiohttp`, `aioftp`, and `numpy`.
- README's parallel-resolution description says GSA participates in the batch resolver, but the main path excludes GSA from batch.

### 4. Source Distribution Contents

- The sdist currently includes `tests/test_*.py`, but does not include all test support files such as `tests/conftest.py`, `tests/harness.py`, `tests/servers.py`, or `tests/fixtures/`.
- Either include the complete test suite and fixtures via `MANIFEST.in`/setuptools config, or exclude tests from sdist entirely.
- Add `MANIFEST.in` or equivalent package-data rules for `LICENSE`, benchmark scripts/data meant for release, and any citation files.
- Regenerate `dist/` after these fixes. The checked-in `dist/` currently contains only an old wheel, not an sdist.

### 5. Preflight And Runtime Dependency Edges

- `-d sra -k` can skip the `srapath` preflight even though `download_sra()` needs `srapath` to resolve SRA HTTPS links.
- `-g` can fall back to downloading SRA and converting, so `fasterq-dump` may be required even when the user did not pass `-q`.
- Direct ENA `.fastq.gz` integrity only needs `md5sum`, but the current preflight can require `srapath` and `vdb-validate`; decide whether this is intentional iSeq parity or should be more needs-based.
- Library API calls do not run preflight. That is desirable for importability, but exceptions for missing external tools should be clear and tested.
- `fasterq-dump` and `pigz` subprocess return codes are not checked in `convert.py`; failed conversion/compression can be silent until downstream checks.

### 6. Live Correctness Must Be Re-run

Before release, run the full live suite without `ADAPTISEQ_NO_NETWORK=1`:

- ENA metadata canary.
- GSA metadata canary.
- Segmented-vs-wget live byte-identity test.
- Live cross-check against stock `iseq -m` where `iseq` is installed.
- Live CRR/GSA data download and md5 verification.
- Live SRA fallback through `srapath` and `vdb-validate`.
- Live `-g`, `-q`, `-q -g`, and merge paths.
- Live three-FASTQ-part run such as the documented `SRR22904269`.

### 7. Real Aspera Validation

- Run real ENA Aspera with `-a`, including key detection and a completed transfer.
- Run real GSA Aspera when Huawei is unavailable or when testing raw FTP/Aspera path.
- Validate adaptive Aspera with at least fixed vs adaptive worker settings.
- If ENA/GSA Aspera is unavailable or blocked, clearly mark Aspera as supported through classic iSeq parity but not part of the adaptive-performance claim.

### 8. CI And Release Automation

- Add GitHub Actions or equivalent CI for Python 3.8, 3.9, 3.10, 3.11, and 3.12.
- Run offline tests in CI by default.
- Add an optional scheduled/manual live canary workflow with secrets/rate-limit protections.
- Add lint/format checks or explicitly document that no formatter is enforced.
- Add type-check smoke if `py.typed` is being shipped.
- Add a release workflow that builds sdist/wheel, runs `twine check`, installs into a clean venv, and smoke-tests `adaptiseq --help`, `--version`, and an offline import.

### 9. Package Index And Conda Readiness

- Install `twine` and run `python3 -m twine check /tmp/adaptiseq-dist/*`.
- Test install from wheel in a clean venv.
- Test install from sdist in a clean venv.
- Test editable install from source.
- Decide whether PyPI package name `adaptiseq` is available and reserve/upload to TestPyPI first.
- Prepare a Bioconda recipe if the goal is parity with iSeq distribution. Include external dependencies: `wget`, `axel`, `pigz`, `aspera-cli ==4.14.0`, `sra-tools >=2.11.0`, `aiohttp`, `aioftp`, `numpy`, and optional `openpyxl`.
- Add classifiers, maintainers, repository URL, issue tracker URL, and Python version classifiers to `pyproject.toml`.

### 10. Benchmark Harness Hardening

- Replace ad hoc benchmark scripts with reproducible runners that emit raw CSV/JSON.
- Record command, tool version, accession list, resolved URLs, bytes, file count, format, exit code, start/end times, host, CPU, memory, disk, network, and retry/failure events.
- Randomize method order and include cold/warm cache controls.
- Keep downloaded-byte accounting separate from metadata/log/transient files.
- Separate download-only benchmarks from end-to-end conversion/compression benchmarks.
- Persist adaptive worker trajectories and per-second throughput traces.

## Benchmarks Needed For An iSeq-Worthy Publication

The current `BENCHMARK.md` is a good sandbox smoke benchmark, but an iSeq-style publication needs both feature breadth and systems-level performance evidence. The following matrix is the recommended benchmark plan.

### A. iSeq Feature And Parity Benchmarks

1. Accession coverage matrix:
   - Test BioProject, Study, BioSample, Sample, Experiment, and Run inputs.
   - Cover GSA, SRA, ENA, DDBJ, and GEO-derived GSE/GSM.
   - Include all supported prefixes: PRJEB, PRJNA, PRJDB, PRJC, GSE, ERP, DRP, SRP, CRA, SAMD, SAME, SAMN, SAMC, ERS, DRS, SRS, GSM, ERX, DRX, SRX, CRX, ERR, DRR, SRR, CRR.
   - Report metadata success rate, run expansion count, and URL resolution count.

2. Metadata parity:
   - Compare adaptiSeq vs stock iSeq metadata-only output for representative ENA, SRA fallback, GSA, and GEO cases.
   - Verify ENA TSV columns, SRA fallback TSV conversion, GSA CSV, and GSA XLSX creation.
   - Include API drift canaries for ENA and GSA.

3. Download correctness:
   - Verify `.fastq.gz` md5 checks against metadata.
   - Verify `.sra` files with `vdb-validate`.
   - Verify GSA md5 via `CRA.md5sum.txt`.
   - Exercise retry, failure continuation, `success.log`, `fail.log`, skip-already-successful, and rerun behavior.
   - Include interrupted downloads and resume from `.part`/`.part.meta`.

4. Format handling:
   - Direct `.fastq.gz` via `-g`.
   - SRA download then FASTQ via `-q`.
   - SRA download then FASTQ plus gzip via `-q -g`.
   - GSA `.gz`, `.bam`, `.tar`, and `.bz2` where available.
   - SRA Lite avoidance or explicit exclusion behavior.

5. Merge correctness:
   - `-e ex`, `-e sa`, and `-e st`.
   - Single-end and paired-end runs.
   - Single-run rename/symlink cases.
   - Multi-run concatenation order.
   - GSA differing-prefix merge cases.

6. Robustness cases from iSeq updates:
   - Mixed accession file input.
   - `-a` and `-p` together, with Aspera priority.
   - `-d sra -g` with integrity still checked.
   - Recent ENA/GSA API changes.
   - Three-FASTQ-link run, where stock iSeq is known to fail.

### B. Reproduce And Extend iSeq Paper Benchmarks

1. Large stability download:
   - 3000 gzip-formatted FASTQ files from GSA, approximately matching the iSeq paper's GSA stability experiment.
   - 3000 SRA/INSDC files, approximately matching the iSeq paper's INSDC stability experiment.
   - Report success rate, md5/vdb validation pass rate, retry count, failure causes, total bytes, total time, and throughput.

2. Tool comparison for GSA and SRA:
   - Reproduce the iSeq Figure 1D comparison against edgeturbo for GSA and SRA Toolkit/pysradb for SRA.
   - Add Kingfisher, ffq/fastq-dl where applicable, and adaptiSeq classic/segmented/adaptive.
   - Report wall time, downloaded bytes, MB/s or Mbps, CPU, memory, average I/O, and exit status.

3. ENA FTP channel:
   - Workloads around the iSeq benchmark sizes: SRX3662754-style 540 Mbp single-end and SRX1663467-style 2 Gbp paired-end, or modern stable replacements.
   - Compare Wget, AXEL, Aspera, stock iSeq, adaptiSeq classic, adaptiSeq segmented, and adaptiSeq adaptive.
   - Include `-r ftp`, `-r https`, and default auto behavior.

4. SRA/AWS HTTPS channel:
   - Compare Wget, AXEL, SRA Toolkit `prefetch`, pysradb, Kingfisher, stock iSeq, and adaptiSeq modes.
   - Use the same resolved SRA object paths and record bytes.

5. GSA FTP channel:
   - Compare Wget, AXEL, Aspera, stock iSeq, adaptiSeq classic, and adaptiSeq segmented where FTP REST is available.
   - Include md5 validation.

6. GSA Huawei Cloud channel:
   - Compare Wget, AXEL, stock iSeq, adaptiSeq classic, and adaptiSeq segmented HTTPS.
   - Verify the Huawei-priority rule and the `-a` interaction where Huawei wins over Aspera.

7. Direct gzip versus conversion:
   - Compare `--fastq`, `--fastq --gzip`, and `--gzip` on single-end and paired-end examples.
   - Report download-only, conversion-only, compression-only, and end-to-end times separately.

8. Thread scaling:
   - Repeat the iSeq `fasterq-dump`/`pigz` thread sweep, for example 2 through 40 threads.
   - Report conversion time, compression time, CPU utilization, memory, and diminishing-return point.

9. Batch CLI behavior:
   - Mixed database accession file.
   - Continue-past-failure behavior.
   - Output directory behavior.
   - Quiet/logging behavior.

### C. FastBioDL-Style Systems Benchmarks

1. Public SRA workload matrix:
   - Large: PRJNA251383, 4 selected runs, few large objects.
   - Medium: PRJNA353374, 12 selected runs, moderate medium objects.
   - Small: PRJNA916347, 243 selected runs, many small objects.
   - Run on at least three environments analogous to FastBioDL: HPC/Lustre, research-cloud or FABRIC/NVMe, and laboratory/NVMe.
   - Minimum three replicates per method.
   - Baselines: `prefetch`, pysradb, Kingfisher, stock iSeq, `iseq -p`, aria2c, curl/wget, adaptiSeq classic, adaptiSeq segmented fixed, adaptiSeq adaptive.
   - Metrics: aggregate throughput, elapsed download-only time, bytes, mean active workers/connections, retry/failure count, CPU, memory, disk write rate.

2. Segmentation isolation:
   - Use a multi-GB SRA object such as `SRR1313069.sralite.1` or a stable replacement.
   - Test segment counts 1, 2, 4, 8, 16, and 32 where polite and allowed.
   - Run on a controlled byte-range server with per-request throughput caps.
   - Run on real NCBI/ENA HTTPS.
   - Report when segmentation helps, when it is neutral, and when it hurts.

3. Adaptive worker control:
   - Use a controlled 500 GB mixed-size workload similar to the FastBioDL TCGA-BRCA subset.
   - Compare fixed worker counts 1, 2, 4, 8, 16, and 20 against adaptive.
   - Keep maximum resource allowance equal across methods.
   - Report per-second throughput traces, active worker traces, mean throughput, and convergence behavior.

4. General downloader comparison:
   - Compare adaptiSeq adaptive to aria2c with multiple `-x/-s` settings, not only `-x8 -s8`.
   - Include curl, wget, and AXEL.
   - Use both controlled and public-repository paths.
   - State clearly whether adaptiSeq wins by better operating-point selection, metadata integration, batching, or raw per-connection efficiency.

5. `K` sensitivity:
   - Test `K` values such as 1.001, 1.005, 1.01, 1.02, and 1.05.
   - Use random or representative 1 GB object sets.
   - Report throughput and active workers, with mean and standard deviation.

6. Resume and interruption:
   - Kill downloads at fixed progress points, restart, and verify exact bytes/md5.
   - Test mid-segment interruption, complete segment interruption, stale metadata, and corrupted `.part.meta`.
   - Compare resume behavior with wget, aria2c, prefetch, and stock iSeq where applicable.

7. Server-friendliness:
   - Controlled 429/503/refused-connection server tests.
   - Verify per-host cap enforcement.
   - Verify circuit breaker backoff and recovery.
   - Report maximum concurrent connections and total request rate.

8. Speed limit correctness:
   - Test `-s` at 10, 50, 100, and 1000 MB/s.
   - Verify aggregate capped throughput across segments and workers.
   - Test classic, segmented, and Aspera paths separately.

9. Metadata resolution scaling:
   - Compare `--meta-jobs 1, 3, 8, 20`.
   - Measure resolution-only time, download-only time, and end-to-end time.
   - If streaming overlap is implemented, report overlap benefits; if not, do not claim it.
   - Confirm NCBI rate limits with and without `NCBI_API_KEY`.

10. Adaptive Aspera:
   - Real ENA and GSA Aspera runs where service access permits.
   - Fixed workers versus hysteresis adaptive workers.
   - Report aggregate throughput, worker trajectory, failures, and whether Aspera is bottlenecked by server policy.

11. FTP behavior:
   - Native FTP REST segmentation on a controlled server.
   - Real ENA/GSA FTP behavior where allowed.
   - Compare FTP segmented, FTP single-stream, HTTPS mirror, and classic Wget/AXEL.

12. Mixed workload realism:
   - Combine small, medium, and large files.
   - Combine direct `.fastq.gz` and `.sra`.
   - Include paired-end and three-link runs.
   - Include mixed databases in one accession list.

### D. Publication Reproducibility Requirements

- Run each configuration at least three times, preferably five for noisy public endpoints.
- Randomize method order and include reversed-order cache controls.
- Delete files between methods unless testing resume/cache behavior.
- Record exact tool versions: adaptiSeq, iSeq, sra-tools, fasterq-dump, pigz, wget, axel, ascp, aria2c, curl, Kingfisher, pysradb, Python, aiohttp, aioftp, numpy.
- Record hardware: CPU, memory, NIC, storage type, filesystem, OS, cloud/HPC site.
- Record network/storage context: iperf3 path capacity where possible, disk write benchmark, and background load notes.
- Publish accession lists, resolved URL lists, command lines, raw logs, per-file timing, per-second throughput traces, and plotting notebooks/scripts.
- Report bytes and file formats for every method so wall-clock comparisons are fair.
- Separate download-only from end-to-end download+convert+compress claims.
- Report failures and exclusions, not only successful runs.
- Use mean plus standard deviation or confidence intervals.

## Minimum Claim-Safe Benchmark Set

If time is limited, this is the smallest benchmark set I would trust for a first adaptiSeq manuscript:

- Full iSeq feature parity table across databases and accession types.
- Live byte-identity segmented-vs-wget ENA test on multiple files, including resume.
- Full 243-run PRJNA916347 small-file batch benchmark, not just the 35-run subset.
- Medium and large public SRA workloads from FastBioDL, each with at least three repeats.
- Controlled segmentation test varying segment count on a multi-GB object.
- Controlled adaptive-vs-fixed worker-count test with at least 100 GB, preferably 500 GB.
- Baselines: stock iSeq, `iseq -p`, prefetch, pysradb, Kingfisher, aria2c, wget/curl, adaptiSeq fixed, adaptiSeq adaptive.
- GSA-specific Huawei/FTP benchmark and metadata/XLSX validation.
- Direct gzip versus conversion/compression benchmark with thread scaling.
- Real Aspera validation or an explicit statement that Aspera performance is out of scope.

## Suggested Positioning

The safest paper story is not "adaptiSeq beats every downloader." The stronger and more defensible story is:

adaptiSeq preserves iSeq's multi-database, metadata-aware acquisition workflow while adding an importable Python API, segmented resumable transfers, and adaptive batch scheduling. It improves the batch accession workflow that iSeq and similar repository tools handle sequentially, while retaining integrity checks, merge/conversion behavior, and GSA/SRA/ENA/DDBJ/GEO coverage.

That story still needs large, repeated, public and controlled benchmarks before it is publication-grade.

## Immediate Priority Order

1. Fix release-facing metadata, license, docs, and rebrand drift.
2. Fix or reword the resolution/download streaming claim.
3. Decide whether GSA should be batched now or explicitly listed as sequential.
4. Add complete sdist manifest rules and a clean release workflow.
5. Run the full live correctness suite.
6. Validate real Aspera or mark adaptive Aspera experimental.
7. Build a reproducible benchmark harness that emits raw data.
8. Run iSeq parity benchmarks.
9. Run FastBioDL-scale systems benchmarks.
10. Only then draft publication claims and figures.
