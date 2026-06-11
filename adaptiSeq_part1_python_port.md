# adaptiSeq Part 1 of 3: Faithful Python port of `iseq` (classic engine)

> This is the first of three build specifications.
>
> - **Part 1 (this file):** port the `iseq` Bash tool to a tested, importable
>   Python package with identical behaviour, using the classic `wget`/`axel`
>   download path. No new download engine yet.
> - **Part 2:** add the segmented, resumable HTTP(S)/FTP download engine as a
>   drop-in replacement for the classic call site, with fixed (non-adaptive)
>   concurrency.
> - **Part 3:** add the gradient adaptive concurrency controller, batch parallel
>   download, parallel metadata resolution, and the benchmark.
>
> Build them in order. Each part must leave the package installable and its own
> acceptance criteria green before the next part begins. Do not start Part 1 by
> writing engine code; that is deliberately out of scope here.

---

## 0. Role and objective

You are implementing **adaptiSeq**, a Python reimplementation of the `iseq` Bash
tool (BioOmics/iSeq). In this part you reproduce all existing functionality
exactly, with no behavioural change to the user. The download mechanism stays the
classic one (`wget`, `axel`) that `iseq` already uses. The value of Part 1 is not
speed; it is a tested, importable Python package that replaces an untestable Bash
script, and a differential test harness that proves byte-for-byte parity with the
original.

Read every source file in Section 1 before writing any code. Then produce a
written plan and a parity checklist derived from Sections 3 and 4, and confirm it
before implementing.

---

## 1. Inputs you must read first

All paths are relative to the project root that contains `iSeq-main/`,
`fastbiodl_upgrade.py`, `search.py`, and `utils.py`.

| File | Why it matters in Part 1 |
|------|--------------------------|
| `iSeq-main/bin/iseq` | The complete reference implementation and the source of truth for URL resolution, metadata APIs, accession regexes, retry logic, merging, and log behaviour. Port from this, not from memory. |
| `iSeq-main/README.md` | Documents every flag, the accession taxonomy, output files, and database routing. Use it as the behavioural contract. |
| `iSeq-main/iSeq.yml` | The conda environment. You will add only light Python dependencies in Part 1. |
| `iSeq-main/INSTALL.md`, `iSeq-main/docs/` | Secondary context only. |

You will **not** read or port `fastbiodl_upgrade.py`, `search.py`, or `utils.py`
in Part 1. They belong to Parts 2 and 3.

Do not assume the contents of any file. Open and read them.

---

## 2. What adaptiSeq is in Part 1, in one paragraph

adaptiSeq accepts the same accessions `iseq` accepts (Project, Study, BioSample,
Sample, Experiment, Run across GSA, SRA, ENA, DDBJ, GEO), resolves the same
download URLs `iseq` would resolve, fetches the same metadata from the same
endpoints into the same files, downloads each file with the same classic tools
`iseq` uses, verifies integrity with the same policy, writes the same
`success.log`/`fail.log`, and performs the same FASTQ conversion and merge. A user
who replaces `iseq` with `adaptiseq` in Part 1 should observe no difference except
the program name and version string.

### 2.1 Design intent (state this in `README.md`)

The load-bearing justification for Part 1 is **maintainability and an importable
library API** (Section 8.1), not performance. The Bash script cannot be unit
tested, imported, or reused from a Python pipeline; the port fixes that. Do not
claim any speed advantage in Part 1, because there is none: the bytes are still
pulled by `wget`/`axel`. Speed is the concern of Parts 2 and 3, and even there it
is to be proven, not asserted.

---

## 3. Non-negotiable fidelity requirements

These are the things that, if changed, make adaptiSeq wrong rather than
different.

1. **URL resolution is identical.** Whatever host and path `iseq` chooses for a
   given run (ENA vol path, SRA via `srapath`, GSA Huawei Cloud vs ftp, FASTQ
   `.gz` vs `.sra`, the `-d`, `-g`, `-a`, `-r` interactions), adaptiSeq must
   choose the same. Port the decision logic in `downloadSRA`, `downloadGSA`,
   `getSRAMetadata`, `getGSAMetadata`, and `validateQuery` faithfully.
2. **Metadata is fetched from the same endpoints and saved in the same files.**
   ENA `filereport` API to `${accession}.metadata.tsv`; the SRA `eutils` +
   `sra-db-be` fallback that converts commas to tabs; the GSA `getRunInfoByCra` /
   `getRunInfo` CSV plus the `exportExcelFile` XLSX. Same filenames, same formats,
   same columns, same user-agent strings.
3. **Accession validation regexes are identical.** Copy them verbatim from the
   Bash. Do not "improve" them. This is a behavioural contract.
4. **MD5 / integrity policy is identical.** ENA/SRA path validates with
   `vdb-validate` for `.sra` files and md5sum-against-metadata for `.fastq.gz`;
   GSA path validates against the project `md5sum.txt`. Up to three rounds of
   re-download, then record in `fail.log`. Successes go to `success.log`. Same
   line format (`$(date)\t$ID`). `-k`/`--skip-md5` skips the check.
5. **Resume / skip-already-downloaded is identical.** If an ID is already in
   `success.log`, skip it with the same message.
6. **External tools are shelled out to, not reimplemented.** Keep using
   `fasterq-dump`, `pigz`, `vdb-validate`, `srapath`, `ascp`, `md5sum`, `wget`,
   `axel`. Port the dependency check (`CheckSoftware`) to a Python preflight
   (`preflight.py`) that prints the same guidance on a missing tool, in the same
   coloured style.
7. **Merging (`-e ex|sa|st`) reproduces the symlink/rename/concatenate logic**
   from `mergeSRArun` and `mergeGSArun`, including the single-run rename case and
   the differing-prefix case.

When in doubt, match the Bash output exactly, including the coloured
`Note` / `Error` / `How to solve?` message style.

---

## 4. CLI parity checklist

adaptiSeq must accept all of the following with identical semantics. Use
`argparse`. Keep both short and long forms.

| Flag | Semantics to preserve |
|------|-----------------------|
| `-i, --input` | Single accession or a file with one accession per line. Same file detection. |
| `-m, --metadata` | Fetch metadata only, no sequence download. |
| `-g, --gzip` | Prefer direct `.fastq.gz`; fall back to `.sra` then convert. |
| `-q, --fastq` | Convert `.sra` to FASTQ with `fasterq-dump`. |
| `-t, --threads` | Threads for `fasterq-dump` / `pigz`. Default 8. |
| `-e, --merge [ex\|sa\|st]` | Merge at Experiment / Sample / Study level, with the same accession-type guards. |
| `-d, --database [ena\|sra]` | Force database. Default auto-detect. |
| `-a, --aspera` | Aspera via `ascp` for GSA/ENA. Same key-file discovery. Huawei Cloud still wins for GSA. |
| `-s, --speed` | Speed cap in MB/s. Default 1000. In Part 1 this maps onto the existing `axel`/`ascp` cap exactly as `iseq` does. |
| `-k, --skip-md5` | Skip integrity check. |
| `-r, --protocol [ftp\|https]` | ENA protocol selection. Default `ftp`. |
| `-Q, --quiet` | Suppress progress output. |
| `-o, --output` | Output directory, created if missing. |
| `-p, --parallel N` | `axel` connection count, exactly as `iseq` uses it. (In Part 2 this becomes an alias for `--max-segments`; keep the flag here with its original meaning.) |
| `-h, --help`, `-v, --version` | Help and version. Version string is `adaptiSeq 0.1.0`. |

### Flag reserved for later parts

Add `--engine [segmented\|classic]` now, but in Part 1 implement **only**
`classic` and make it the default. Part 2 adds `segmented` and flips the default.
Listing the flag now keeps the CLI surface stable across parts. If a user passes
`--engine segmented` in a Part 1 build, print a clear message that the segmented
engine is not yet available and fall back to classic.

The remaining new flags (`--segment-size`, `--max-segments`, `-j/--jobs`,
`--adaptive/--no-adaptive`, `--probe-window`, `--cc-penalty`,
`--max-conns-per-host`, `--meta-jobs`) are introduced in Parts 2 and 3. Do not
add them in Part 1.

---

## 5. Suggested project structure (establish the skeleton now)

Produce an installable package with a console entry point named `adaptiseq`.
Create the full package layout in Part 1, leaving the `engine/` modules as thin
stubs that Parts 2 and 3 will fill.

```
adaptiseq/
  __init__.py       # exports the public API (Section 8.1)
  cli.py            # argparse, dispatch, version, help mirroring iseq
  accession.py      # validateQuery port: regexes + GEO/GSM resolution
  routing.py        # database auto-detect; ENA vs SRA vs GSA selection
  metadata.py       # ENA filereport / SRA eutils+sra-db-be / GSA CSV+XLSX
  resolve.py        # per-run URL resolution (downloadSRA/downloadGSA ports)
  engine/
    classic.py      # wget/axel wrapper (the only engine in Part 1)
    segmented.py    # STUB in Part 1; filled in Part 2
    ftp.py          # STUB in Part 1; filled in Part 2
    optimize.py     # STUB in Part 1; filled in Part 3
    ratelimit.py    # STUB in Part 1; MB/s limiter + per-host cap in Part 2
  convert.py        # fasterq-dump + pigz wrappers
  integrity.py      # vdb-validate and md5sum checks
  merge.py          # mergeSRArun / mergeGSArun ports
  preflight.py      # CheckSoftware port
  logs.py           # success.log / fail.log helpers
pyproject.toml      # entry point: adaptiseq = adaptiseq.cli:main
README.md           # adaptiSeq usage, parity notes
```

Update `iSeq.yml` with only the light dependencies Part 1 needs: `requests` if
you use it for metadata (otherwise keep shelling to `wget` as `iseq` does). Do
**not** add `aiohttp`, `aioftp`, `numpy`, `skopt`, or `scipy` yet. Keep
`sra-tools`, `aspera-cli`, `pigz`, `axel`, `wget` as before.

### 5.1 Engine seam (the most important design decision in Part 1)

Define a single internal interface for "download one resolved URL to one output
path, return success or failure," and route the classic engine through it. Make
the call site that downloads a file go through this seam rather than calling
`wget`/`axel` inline. This seam is what Part 2 replaces with the segmented engine
without touching resolution, integrity, logging, or merge. Get it clean now;
Parts 2 and 3 depend on it being the only place bytes are fetched.

---

## 6. Public library API (a primary reason to do this in Python at all)

A CLI-only port wastes the main advantage of leaving Bash. Expose a small,
documented, importable API so downstream Python pipelines can use adaptiSeq
without shelling out. At minimum:

```python
from adaptiseq import fetch, resolve, get_metadata

meta = get_metadata("SRR7706354")                 # returns parsed records
urls = resolve("SRR7706354", database="ena")      # resolved download URLs
result = fetch("SRR7706354", outdir="data/",       # download + verify
               gzip=True)
```

These functions must not call `sys.exit` or print colour codes. They raise typed
exceptions and return values. `cli.py` is a thin wrapper over them. This
separation is what makes the test suite possible.

---

## 7. Acceptance criteria for Part 1

Part 1 is done when all of the following hold:

1. `adaptiseq --help` lists every Part 1 flag in Section 4 with correct defaults.
2. `adaptiseq --version` prints `adaptiSeq 0.1.0`.
3. `adaptiseq -i <RUN> -m` produces the same metadata file (`.tsv`, `.csv`, or
   `.xlsx`) `iseq` produces for the same accession, with the same columns and row
   set.
4. A small real download over the classic engine produces a byte-identical file
   to what `iseq` produces, passes the MD5/`vdb-validate` check, and writes the ID
   to `success.log`.
5. Re-running an accession already in `success.log` skips it with the same
   message.
6. Merge (`-e ex|sa|st`) reproduces `iseq`'s output for a small multi-run case.
7. The package installs cleanly from a fresh environment built from `iSeq.yml`,
   and the `adaptiseq` entry point works.
8. The library API in Section 6 is importable and `fetch`, `resolve`, and
   `get_metadata` work without invoking the CLI.
9. The differential harness in Section 8 passes against the recorded golden
   fixtures, and (when `iseq` and network are available) against live `iseq`.

---

## 8. Verification

Use deliberately small inputs so tests are fast and cheap. Confirm sizes from
metadata first. Suggested test accessions: one small SRA run (`SRR...`) with
`-m`, one small GSA run (`CRR...`) to exercise the GSA CSV + XLSX + Huawei/ftp
path, and a two-line `.txt` list mixing one SRA and one GSA accession.

### 8.1 Differential testing against `iseq`, with golden fixtures (required)

Parity is asserted, not assumed. Build a harness under `tests/` that, given a
fixed list of test accessions, runs `adaptiseq` and compares against `iseq`
output, diffing:

- metadata files (`.metadata.tsv` / `.csv`): same columns, same row set;
- the md5 of each downloaded data file;
- the contents of `success.log` and `fail.log` as sets of IDs.

Two modes, both required:

- **Live mode.** When `iseq` is installed and the network is up, run stock `iseq`
  and `adaptiseq` into two directories and diff live.
- **Fixture mode (the default in CI).** Capture `iseq`'s metadata output and the
  public md5 set for the fixed test accessions **once**, check those golden
  fixtures into the repository under `tests/fixtures/`, and diff `adaptiseq`
  against the frozen fixtures offline. This is mandatory because live mode skips
  when `iseq` is absent or the network is down, which is exactly when CI runs, and
  a skipped differential test passes vacuously. The fixtures prevent that.

The harness reports any mismatch as a failure with a readable diff. Live mode
skips gracefully and says so when `iseq` is not installed; fixture mode does not
skip.

### 8.2 API-drift canary

The ENA, NCBI, and GSA metadata endpoints change repeatedly (GSA in November
2025, ENA in September 2025). Add a lightweight live test that fetches metadata
for one known-stable accession per database and asserts the expected column
structure is still present. When it fails, the message must say that an upstream
API moved, not that adaptiSeq is broken. Keep it isolated so it runs separately
from the offline tests.

---

## 9. How to work

1. Read all of Section 1's files. Produce a short written plan and a parity
   checklist from Sections 3 and 4. Do not skip this.
2. Build in this order, testing each before moving on: accession validation and
   routing; metadata fetching and parsing for all three databases; per-run URL
   resolution; the classic download seam (Section 5.1); integrity checks and
   logs; conversion; merge; then the simple file-list input path.
3. Commit at each milestone with a clear message.
4. Keep a running `NOTES.md` of any place where you had to make a judgement call
   that diverges from the Bash, with the reason. Divergence must be deliberate and
   documented, never accidental.
5. Write the adaptiSeq `README.md` and a short `CHANGES_FROM_ISEQ.md` stating
   plainly that Part 1 is a behaviour-preserving port on the classic engine, and
   that the segmented and adaptive engines arrive in Parts 2 and 3.

Prioritise correctness and parity over cleverness. A faithful port that downloads
real files and passes MD5 is the entire goal of Part 1.
