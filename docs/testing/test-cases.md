# adaptiSeq Feature Test Cases

This document defines practical test cases for the core methods described in
[`methods.md`](../methods.md). Record each execution in
[`test-results.md`](test-results.md) and the spreadsheet versions
[`test-results.csv`](test-results.csv) / [`test-results.xlsx`](test-results.xlsx).

## Test Environment

Run commands from the repository root:

```bash
cd /home/nn3bd/Downloads/Falcon-Projects/AdaptiSeq/adaptiSeq
conda activate adaptiseq
adaptiseq --version
```

Use exactly one Python environment at a time. If your prompt shows
`(.venv) (adaptiseq)`, run `deactivate` once to return to Conda. Keep live test
outputs under `tmp/feature-tests/<test-id>/`.

Before live tests, check optional external tools:

```bash
for t in wget md5sum pigz srapath fasterq-dump vdb-validate axel ascp; do
  command -v "$t" >/dev/null && echo "$t: ok" || echo "$t: missing"
done
```

## Offline Automated Coverage

| ID | Area | Command | Expected Result |
| --- | --- | --- | --- |
| OFF-01 | CLI, parsing, routing | `ADAPTISEQ_NO_NETWORK=1 python -m pytest tests/test_cli.py tests/test_routing.py tests/test_accession.py -q` | All tests pass. |
| OFF-02 | Segmented engine and finalize behavior | `ADAPTISEQ_NO_NETWORK=1 python -m pytest tests/test_segmented.py tests/test_segmented_finalize.py -q` | Local HTTP/range tests pass; final files are not corrupt. |
| OFF-03 | Native FTP segmented path | `ADAPTISEQ_NO_NETWORK=1 python -m pytest tests/test_ftp_segmented.py -q` | Local FTP tests pass. |
| OFF-04 | Batch/adaptive primitives | `ADAPTISEQ_NO_NETWORK=1 python -m pytest tests/test_batch.py tests/test_meter_gate.py tests/test_optimize.py -q` | Worker gate, meter, optimizer, and batch tests pass. |
| OFF-05 | Integrity/log behavior | `ADAPTISEQ_NO_NETWORK=1 python -m pytest tests/test_logs_integrity.py -q` | Retry and success/fail log semantics pass. |
| OFF-06 | sysbench harness | `ADAPTISEQ_NO_NETWORK=1 python -m pytest sysbench/tests -q` | Sampler and phase tests pass. |
| OFF-07 | Aspera batch/controller primitives | `ADAPTISEQ_NO_NETWORK=1 python -m pytest tests/test_aspera.py -q` | Hysteresis controller, directory meter, retries, success-log skip, and worker-cap tests pass. |

OFF commands run with the currently active `python`; they should not activate
another environment. If pytest prints `[100%]` and then a traceback only after
you press `Ctrl-C`, treat the test run as passed and avoid interrupting pytest
shutdown cleanup.

## Live Feature Test Cases

Public endpoints can change or throttle. If a live case fails, rerun once in a
clean output directory, then inspect `fail.log`, metadata files, and the exact
endpoint error.

### TC-01: CLI Help and Version

```bash
adaptiseq --version
adaptiseq --help
```

Expected: version prints `adaptiSeq 0.1.3`; help lists segmented/default engine,
batch, adaptive, Aspera, metadata, merge, and transport flags.

### TC-02: ENA/SRA Metadata Only

```bash
adaptiseq -i SRR7706354 -m -o tmp/feature-tests/tc02
```

Expected: writes `SRR7706354.metadata.tsv`; no sequence data or success/fail log
is required for metadata-only mode.

### TC-03: GSA Metadata Only

```bash
adaptiseq -i CRR343031 -m -o tmp/feature-tests/tc03
```

Expected: writes `CRR343031.metadata.csv`; when project XLSX metadata is
available, a `CRA*.metadata.xlsx` file is also written.

### TC-04: Python API Metadata and Resolve

```bash
python - <<'PY'
from adaptiseq import get_metadata, resolve

rows = get_metadata("SRR7706354")
urls = resolve("SRR7706354", gzip=True, protocol="https")
print(len(rows), len(urls), urls[:1])
assert rows
assert urls
PY
```

Expected: API returns parsed row dictionaries and resolved URLs without printing
CLI color output or exiting the interpreter.

### TC-05: Default Segmented HTTPS Download

```bash
adaptiseq -i SRR22904257 -g -r https \
  --engine segmented --max-segments 2 --max-conns-per-host 2 \
  -o tmp/feature-tests/tc05
```

Expected: exits 0, downloads one or more `*.fastq.gz` files, verifies md5, and
records the run/file in `success.log`. No zero-byte outputs should exist. For a
single-file download, the progress worker count should start at 1 and stay
bounded by unfinished files.

Medium-size stress variant:

```bash
adaptiseq -i SRR5017128 -g -r https \
  --engine segmented --max-segments 4 --max-conns-per-host 4 \
  -o tmp/feature-tests/tc05-medium
```

Expected: downloads `SRR5017128.fastq.gz`, records `SRR5017128` in
`success.log`, and does not create `fail.log`. `--max-segments` controls per-file
segment connections, not batch worker count.

### TC-06: Resume and Skip Already Successful Files

Run from the repository root; `-o` is relative to the current directory.

```bash
adaptiseq -i SRR22904257 -g -r https \
  --engine segmented --max-segments 2 \
  -o tmp/feature-tests/tc05
```

Expected: reuses metadata and skips files already recorded in `success.log`.

### TC-07: Forced Segmented FTP

```bash
adaptiseq -i SRR22904257 -g -r ftp \
  --engine segmented --max-segments 2 \
  -o tmp/feature-tests/tc07
```

Expected: if the public FTP endpoint supports REST/range from the current
network, exits 0, downloads/verifies the same logical data as TC-05, and leaves
no corrupt final output files.

### TC-08: Speed Cap

Use a file large enough to observe throttling. `SRR22904280` is about 157 MB.
Run an uncapped baseline and a capped run in separate directories:

```bash
adaptiseq -i SRR22904280 -g -r https \
  --engine segmented --max-segments 2 \
  -o tmp/feature-tests/tc08-speed-baseline

adaptiseq -i SRR22904280 -g -r https -s 1 \
  --engine segmented --max-segments 2 \
  -o tmp/feature-tests/tc08-speed-cap
```

Expected: both runs exit 0 and md5-check successfully. The capped run should be
noticeably slower and report around `8 Mbps`, because `-s 1` means 1 MB/s.

### TC-09: Batch Adaptive Download

```bash
head -5 bench/inputs/accessions_small_PRJNA916347.txt > tmp/feature-tests/batch5.txt
adaptiseq -i tmp/feature-tests/batch5.txt -g -r https \
  --engine segmented -j 4 --adaptive --meta-jobs 2 \
  -o tmp/feature-tests/tc09
```

Expected: all resolved files complete or explicit failures are logged; displayed
workers never exceed unfinished files.

### TC-10: Batch Fixed Concurrency

```bash
adaptiseq -i tmp/feature-tests/batch5.txt -g -r https \
  --engine segmented -j 4 --no-adaptive --meta-jobs 2 \
  -o tmp/feature-tests/tc10
```

Expected: logical outputs match TC-09 while using fixed concurrency.

### TC-11: Classic Engine With Wget

```bash
adaptiseq -i SRR22904257 -g -r https --engine classic -o tmp/feature-tests/tc11
```

Expected: classic `wget` path downloads/verifies the same logical output.

### TC-12: Classic Engine With Axel Parallelism

```bash
adaptiseq -i SRR22904257 -g --engine classic -p 4 -o tmp/feature-tests/tc12
```

Expected: uses `axel -n 4` when installed; mark Blocked if `axel` is
unavailable. The classic engine should print an adaptiSeq note before axel starts
showing the connection count, resume mode, speed cap, and output path. Axel may
print repeated `Connection N finished` or `unexpectedly closed` messages while it
retries byte ranges; the run passes only when the final md5 validation succeeds.

### TC-13: Segmented `-p` Alias

```bash
adaptiseq -i SRR22904257 -g -r https --engine segmented -p 3 -o tmp/feature-tests/tc13
```

Expected: maps `-p` to segmented max-segment behavior and completes successfully.
For segmented HTTPS/FTP, output should include segment-level lines such as
`Segment plan for <file>: segmented HTTPS, 3 segment(s), ...` and final
`Segment meter for <file>: 3/3 complete | active 0 | 100.0% ...`. The batch
worker count can still be `1` for a one-file run; segment logs show the internal
per-file connections. Adaptive mode should log probe lines during the run and a
compact `adaptive worker summary` at the end, not a long full trajectory.

### TC-14: SRA to FASTQ Conversion

```bash
adaptiseq -i SRR1178105 -q -t 2 -o tmp/feature-tests/tc14
```

Expected: requires `srapath`, `fasterq-dump`, `vdb-validate`, and `pigz`; mark
Blocked if those tools are missing. The run should download the SRA file, md5
validate it, convert it with `fasterq-dump`, and write paired FASTQ files. During
download, file progress and segment meter lines can appear before the first
`adaptive probe`; this is expected because progress display, segment logging, and
adaptive probing use separate intervals. Default display intervals are centralized
in `adaptiseq/options.py`: file progress every 2 seconds and segment meter lines
every 10 seconds.

### TC-15: Merge by Experiment

```bash
adaptiseq -i SRX003906 -g -e ex -o tmp/feature-tests/tc15
```

Expected: downloads runs for the experiment and writes the expected merged file.

### TC-16: Merge Guard Negative Case

```bash
adaptiseq -i SRR7706354 -e ex -o tmp/feature-tests/tc16
```

Expected: exits non-zero before download because merge mode requires a higher
level accession than a Run ID.

### TC-17: Skip MD5

```bash
adaptiseq -i SRR22904257 -g -r https -k --engine segmented -o tmp/feature-tests/tc17
```

Expected: download completes and output explicitly notes md5 checking was skipped.

### TC-18: ENA Aspera

```bash
adaptiseq -i SRR22904257 -a -g --aspera-efficiency 0.70 -o tmp/feature-tests/tc18
```

Expected: requires real IBM `ascp`; mark Blocked if unavailable.

### TC-19: GSA Aspera / Huawei Preference

```bash
adaptiseq -i CRR343031 -a -g -o tmp/feature-tests/tc19
```

Expected: validates GSA endpoint selection; mark Blocked if required endpoint or
`ascp` is unavailable.

### TC-20: Python API Fetch

```bash
python - <<'PY'
from adaptiseq import fetch

ctx = fetch("SRR22904257", gzip=True, protocol="https", outdir="tmp/feature-tests/tc20")
assert not ctx.failed
PY
```

Expected: API completes without `sys.exit` and writes outputs under `tc20`.

### TC-21: Build and Package Smoke

```bash
python -m build
python -m twine check dist/*
```

Expected: source distribution and wheel build successfully and pass metadata
checks.
