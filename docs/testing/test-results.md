# adaptiSeq Test Results Report

Last updated: 2026-06-28 15:12 CDT

This is the living execution report for [`test-cases.md`](test-cases.md). Update
it after each test run. The spreadsheet version is maintained in
[`test-results.csv`](test-results.csv), which can be opened in Excel or
LibreOffice.

## Status Legend

- `Passed`: expected result was observed.
- `Failed`: expected result was not observed.
- `Blocked`: test could not run because a prerequisite is missing.
- `Partial`: only part of the case was run.
- `Not Run`: no execution evidence yet.

## Current Summary

| Status | Count |
| --- | ---: |
| Passed | 23 |
| Failed | 0 |
| Blocked | 0 |
| Partial | 1 |
| Not Run | 4 |

## Environment Notes

- Conda environment: `adaptiseq`
- Project virtualenv: `.venv`
- Do not stack Conda and `.venv` during normal test execution.
- Latest offline validation was run from Conda `adaptiseq` only.
- `psutil >=5.9` is required for `sysbench/tests` and is listed in `iSeq.yml`.
- Live feature tests should write to `tmp/feature-tests/`.

## Results

| ID | Test Case | Status | Date | Environment | Evidence / Actual Result | Artifact / Notes |
| --- | --- | --- | --- | --- | --- | --- |
| OFF-01 | CLI, parsing, routing | Passed | 2026-06-27 | Conda `adaptiseq` | `tests/test_cli.py tests/test_routing.py tests/test_accession.py` passed at 100%. | User pressed `Ctrl-C` after `[100%]`; resulting `KeyboardInterrupt` occurred during pytest cleanup and is not counted as failure. |
| OFF-02 | Segmented engine and finalize behavior | Passed | 2026-06-28 | Conda `adaptiseq` | `tests/test_segmented.py tests/test_ftp_segmented.py` passed: 27 passed. | Codex-run pytest output after display-interval changes; local socket tests required sandbox escalation. Earlier finalize coverage remained passed. |
| OFF-03 | Native FTP segmented path | Passed | 2026-06-28 | Conda `adaptiseq` | Included in combined `tests/test_segmented.py tests/test_ftp_segmented.py` rerun: 27 passed. | Codex-run pytest output. |
| OFF-04 | Batch/adaptive primitives | Passed | 2026-06-28 | Conda `adaptiseq` | `tests/test_batch.py tests/test_meter_gate.py tests/test_optimize.py` passed: 23 passed. | Codex-run pytest output; includes worker-cap, display interval, and success-log regression coverage. |
| OFF-05 | Integrity/log behavior | Passed | 2026-06-27 | Conda `adaptiseq` | `tests/test_logs_integrity.py` passed: 4 passed. | User-reported terminal output. |
| OFF-06 | sysbench harness | Passed | 2026-06-27 | Conda `adaptiseq` | `python -m pytest sysbench/tests -q` passed: 4 passed. | User-reported terminal output. |
| OFF-07 | Aspera batch/controller primitives | Passed | 2026-06-28 | Conda `adaptiseq` | `tests/test_aspera.py` passed: 12 passed. | Codex-run pytest output; includes worker-cap, success-log skip, retry, directory meter, and hysteresis coverage. |
| TC-01 | CLI Help and Version | Passed | 2026-06-27 | Conda `adaptiseq` | `adaptiseq --version` printed `adaptiSeq 0.1.3`; `adaptiseq --help` printed expected CLI options. | User-reported terminal output. |
| TC-02 | ENA/SRA Metadata Only | Passed | 2026-06-26 | Conda `adaptiseq` | Metadata file retrieved and validated: 2 lines, 1771 bytes, 51 columns, 1 data row, 0 mismatched rows, `run_accession=SRR7706354`, `fastq_md5` and `fastq_ftp` present. | `tmp/feature-tests/tc02/SRR7706354.metadata.tsv` |
| TC-03 | GSA Metadata Only | Passed | 2026-06-27 | Conda `adaptiseq` | `CRR343031.metadata.csv` and `CRA005440.metadata.xlsx` both present in output directory. GSA CSV + project XLSX match expected output exactly. | `tmp/feature-tests/tc03/CRR343031.metadata.csv`, `tmp/feature-tests/tc03/CRA005440.metadata.xlsx` |
| TC-04 | Python API Metadata and Resolve | Passed | 2026-06-27 | Conda `adaptiseq` | `get_metadata("SRR7706354")` returned 1 row; `resolve(..., gzip=True, protocol="https")` returned 2 URLs. | First URL resolved to `https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR770/004/SRR7706354/SRR7706354_1.fastq.gz`. |
| TC-05 | Default Segmented HTTPS Download | Passed | 2026-06-27 | Conda `adaptiseq` | Small run `SRR22904257` passed; medium run `SRR5017128` downloaded `SRR5017128.fastq.gz` at 4,512,599,441 bytes with segmented HTTPS and md5 success. Exact transfer showed Mbps updates, `1 workers` for the single remaining file, and final `1/1 files ... 0 workers`; post-fix rerun reported `up to 1 worker(s) (configured max 20)` and skipped from `success.log`. | Output is under `tmp/feature-tests/tc05` and `tmp/feature-tests/tc05-medium`; `success.log` contains `SRR5017128`; no `fail.log` exists. `0/1 files` during transfer is expected because progress is file-count based. |
| TC-06 | Resume and Skip Already Successful Files | Passed | 2026-06-27 | Conda `adaptiseq` | Re-run from repository root against `tmp/feature-tests/tc05`; adaptiSeq reused metadata and reported `SRR22904257 has been downloaded successfully`, pointing to `success.log`. | Original `tmp/feature-tests/tc05/success.log` contains `SRR22904257`; no `fail.log` exists. Earlier nested-path attempt is ignored as a procedure issue. |
| TC-07 | Forced Segmented FTP | Passed | 2026-06-27 | Conda `adaptiseq` | Codex rerun after deleted artifacts downloaded `SRR22904257.fastq.gz` by segmented FTP, reported md5 success, and md5 validation matched metadata: `bfa437e8a76bd5aab426eb3e5bef4cb6`. | `tmp/feature-tests/tc07/SRR22904257.fastq.gz` is 50,963 bytes; `success.log` contains `SRR22904257`; no `fail.log` exists. |
| TC-08 | Speed Cap | Passed | 2026-06-27 | Conda `adaptiseq` | Codex ran `SRR22904280` uncapped and capped. Uncapped baseline completed in 44.88s with adaptive trajectory around 23-33 Mbps; `-s 1` capped run completed in 152.07s with trajectory consistently `1w@8Mbps`. Both md5 validations matched `cd5d5d34ff671b3c0e33e11455e149c2`. | Baseline: `tmp/feature-tests/tc08-speed-baseline/SRR22904280.fastq.gz`; capped: `tmp/feature-tests/tc08-speed-cap/SRR22904280.fastq.gz`; each is 156,940,486 bytes, has `success.log`, and has no `fail.log`. |
| TC-09 | Batch Adaptive Download | Passed | 2026-06-27 | Conda `adaptiseq` | 5/5 accessions (SRR22904253–SRR22904257) downloaded and md5-verified. Transport auto-selected as segmented HTTPS for all. Adaptive concurrency started at 2 workers, reached 0 at completion; workers never exceeded unfinished file count. No `fail.log` created. | `tmp/feature-tests/tc09/success.log` lists all 5 accessions; 5 `.fastq.gz` + 5 `.metadata.tsv` files present; no `fail.log`. |
| TC-10 | Batch Fixed Concurrency | Passed | 2026-06-27 | Conda `adaptiseq` | 5/5 accessions (SRR22904253–SRR22904257) downloaded and md5-verified with fixed concurrency. Announced `up to 4 worker(s) (fixed concurrency)` (vs adaptive in TC-09). Transport auto-selected as segmented HTTPS for all 5. Same logical outputs as TC-09; all 5 accessions in `success.log`; no `fail.log`. | `tmp/feature-tests/tc10/success.log` lists all 5 accessions; 5 `.fastq.gz` + 5 `.metadata.tsv` files present; no `fail.log`. |
| TC-11 | Classic Engine With Wget | Passed | 2026-06-28 | Conda `adaptiseq` | Small run `SRR22904257` completed with classic `wget` progress and md5 success. Medium run `SRR5017139` downloaded `SRR5017139.fastq.gz` at 4,682,404,547 bytes in 15m 38s, reported md5 success, and the file size matched metadata. | `tmp/feature-tests/tc11/SRR5017139.fastq.gz`; `success.log` contains `SRR5017139`; no `fail.log` exists. Classic engine behavior is expected to show `wget` per-file progress instead of segmented/adaptive worker output. |
| TC-12 | Classic Engine With Axel Parallelism | Passed | 2026-06-28 | Conda `adaptiseq` | Small `SRR22904257` and medium `SRR5017138` completed through classic `axel -n 4`; medium output reported `Downloaded 4.03918 Gigabyte(s) in 5:30 minute(s)` and md5 success. `SRR5017138.fastq.gz` is 4,337,038,004 bytes, matching metadata. | `tmp/feature-tests/tc12/success.log` contains `SRR22904257` and `SRR5017138`; no `fail.log` exists. Raw repeated `Connection N finished/unexpectedly closed` lines are axel retry/range-slot messages, not final integrity status. Added adaptiSeq wrapper notes so future axel runs explicitly show connection count and completion before md5 validation. |
| TC-13 | Segmented `-p` Alias | Passed | 2026-06-28 | Conda `adaptiseq` | `-p 3` on the segmented engine printed the expected alias note, selected segmented HTTPS, completed `SRR5017137.fastq.gz`, and reported md5 success. Adaptive trajectory stayed at `1w` because this was a single-file run, so the batch worker cap was 1 while internal segment connections were controlled by `--max-segments 3`. File size matched metadata: 4,870,757,739 bytes. | `tmp/feature-tests/tc13/success.log` contains `SRR5017137`; no `fail.log` exists. Segment-level logging and compact adaptive probe-summary logging were added after this observed run; rerun from the updated source should show `Segment plan` / `Segment meter`, live `adaptive probe`, and final `adaptive worker summary` lines. |
| TC-14 | SRA to FASTQ Conversion | Passed | 2026-06-28 | Conda `adaptiseq` | `adaptiseq -i SRR1178105 -q -t 2 -o tmp/feature-tests/tc14` completed successfully. Downloaded `SRR1178105` at 291,744,155 bytes, verified md5, converted with `fasterq-dump -t 2`, and wrote paired FASTQ files. Each FASTQ has 10,044,848 lines, matching 2,511,212 reads per mate. | `tmp/feature-tests/tc14/success.log` contains `SRR1178105`; `SRR1178105_1.fastq` and `SRR1178105_2.fastq` are each 698,694,944 bytes; no `fail.log` exists. Logging behavior is expected: file progress repaints frequently, segment meters log independently, and `adaptive probe` logs only after the probe window measurement. |
| TC-15 | Merge by Experiment | Not Run |  |  |  | Network/download dependent. |
| TC-16 | Merge Guard Negative Case | Passed | 2026-06-28 | Conda `adaptiseq` | `adaptiseq -i SRR7706354 -e ex -o tmp/feature-tests/tc16` exited with the expected guard error: `SRR7706354 is a Run ID, can not use -e option`, followed by the expected solution text. | No download artifacts were created, which is expected because validation stops before download. |
| TC-17 | Skip MD5 | Passed | 2026-06-28 | Conda `adaptiseq` | `adaptiseq -i SRR22904257 -g -r https -k --engine segmented -o tmp/feature-tests/tc17` completed successfully and printed `Skip md5 check for SRR22904257, as -k option is used`. | `SRR22904257.fastq.gz` is 50,963 bytes and metadata is present. No `fail.log` exists. `success.log` is empty because this mode skips verification rather than recording an md5-verified success. |
| TC-18 | ENA Aspera | Partial | 2026-06-28 | Conda `adaptiseq` | Live run reached real `ascp` but failed with `failed to authenticate`; no FASTQ was downloaded and `fail.log` recorded `SRR22904257`. Root cause was ENA `fastq_aspera` metadata in `fasp.sra.ebi.ac.uk:/...` form being passed without the required `era-fasp@` user. | Code now normalizes ENA Aspera links to `era-fasp@fasp.sra.ebi.ac.uk:/...` and focused tests pass. Rerun TC-18 from this revision to confirm live transfer. |
| TC-19 | GSA Aspera / Huawei Preference | Not Run |  |  |  | Requires GSA endpoint availability and possibly real `ascp`. |
| TC-20 | Python API Fetch | Not Run |  |  |  | Run the Python API `fetch()` snippet from `test-cases.md`. |
| TC-21 | Build and Package Smoke | Not Run |  |  |  | Run build, twine check, and wheel smoke install. |

## Update Procedure

After each test:

1. Update the matching row in this file and in `docs/testing/test-results.csv`.
2. Set `Status` to `Passed`, `Failed`, `Blocked`, `Partial`, or `Not Run`.
3. Record the environment used, for example `Conda adaptiseq` or `.venv`.
4. Paste the shortest useful evidence: pass count, failure summary, output file
   path, md5/log check, or blocker.
5. If a test creates files, keep them under `tmp/feature-tests/<test-id>/`.
