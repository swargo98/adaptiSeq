# Changes from `iseq`

adaptiSeq is a Python reimplementation of the [`iseq`](https://github.com/BioOmics/iSeq)
Bash tool (ported from `iSeq-main/bin/iseq`, version 1.9.8, dated 2025-11-20).

## Part 1 is a behaviour-preserving port on the classic engine

**Part 1 changes nothing a user can observe except the program name and version
string.** It reproduces all existing `iseq` functionality on the same classic
download path (`wget`, `axel`, `ascp`):

- the same accepted accessions (Project / Study / BioSample / Sample / Experiment
  / Run across GSA, SRA, ENA, DDBJ, GEO);
- the same resolved download URLs (ENA vol path, `srapath`, GSA Huawei Cloud vs
  ftp, `.fastq.gz` vs `.sra`, and the `-d`/`-g`/`-a`/`-r` interactions);
- the same metadata endpoints, filenames, formats, columns, and user-agents
  (ENA `filereport` TSV; SRA `eutils` + `sra-db-be` runinfo with comma→tab; GSA
  `getRunInfoByCra`/`getRunInfo` CSV + `exportExcelFile` XLSX);
- the same accession-validation regexes (copied verbatim);
- the same MD5 / `vdb-validate` integrity policy, up to three rounds of
  re-download, then `fail.log`; successes to `success.log`; `-k` skips;
- the same resume/skip-already-downloaded behaviour;
- the same FASTQ conversion (`fasterq-dump` + `pigz`) and the same merge
  (`mergeSRArun` / `mergeGSArun`) symlink/rename/concatenate logic;
- the same coloured `Note` / `Error` / `How to solve?` message style.

**Part 1 makes no speed claim.** The bytes are still pulled by `wget`/`axel`.

### What Part 1 *adds* (without changing behaviour)

- An installable package and the `adaptiseq` console entry point.
- A small importable library API (`fetch`, `resolve`, `get_metadata`) that returns
  values and raises typed exceptions instead of exiting or printing colour.
- A single **engine seam** (`engine/classic.py::ClassicEngine.fetch`) — the only
  place sequence bytes are fetched — so Part 2 can drop in the segmented engine.
- A differential test harness with golden fixtures.
- Reserved CLI surface for later parts: `--engine [segmented|classic]` (Part 1
  implements only `classic`; `segmented` prints a notice and falls back).

## Part 2 — the segmented download engine (now the default)

Part 2 replaces the classic `wget`/`axel` call site with a **segmented,
resumable HTTP(S)/FTP engine** at the single Part 1 seam, and makes it the
default (`--engine segmented`). The engine changes only *how* bytes arrive, never
*which* bytes: URL resolution, database choice, metadata, integrity policy, logs,
and merge are untouched, and all Part 1 differential tests still pass on the
segmented default.

What it adds:

- **Range-segmented HTTP(S)** download: per-file connection count derived from
  size (`min(--max-segments, max(1, size // --segment-size))`), concurrent ranged
  GETs with strict `206` validation written via `os.pwrite`, atomic `.part` +
  `.part.meta` resume, single-connection fallback, and per-segment retry with
  exponential backoff. Verified live against ENA: a small real fastq downloaded
  in multiple segments is byte-identical to `wget`.
- **Native segmented FTP** (`REST`/`RETR` via `aioftp`) with the same `.part.meta`
  resume and strict byte-count accounting.
- **Transport selection (`--engine segmented`, protocol `auto`):** prefer the
  HTTPS mirror, confirmed by a cheap per-host probe; fall back to native segmented
  FTP, then single-stream, then `--engine classic`. An explicit `-r https` / `-r
  ftp` overrides and is final. A corrupt or zero-byte file is never produced.
- **Connection etiquette:** a global per-host connection cap
  (`--max-conns-per-host`) plus a reactive circuit breaker (429/503/refused →
  exponential global backoff + temporarily lowered cap, slow recovery).
- **Engine-applied speed cap:** `-s/--speed` MB/s now via a token-bucket limiter
  shared across a file's segments (still applied to `ascp`).

New/changed flags: `--engine [segmented|classic]` (default segmented),
`--segment-size` (MB, default 512), `--max-segments` (default 8),
`--max-conns-per-host` (default 8). `-p/--parallel N` becomes an alias for
`--max-segments N` on the segmented engine (keeps its `axel` meaning on classic).
`-r/--protocol` gains an implicit `auto` default (HTTPS-first); explicit
`ftp`/`https` still force the transport.

### Transport selection rule (summary)

1. `-r https` → HTTPS (upgrade a same-host `ftp://` link to `https://`).
2. `-r ftp` → native segmented FTP.
3. `auto` (default) for an `ftp://` link: same-host HTTPS range probe → segmented
   HTTPS; else FTP `REST`+concurrency probe → segmented FTP; else single-stream;
   else classic.

### Known constraint: EBI FTP `REST`

EBI restricts FTP `REST` and caps concurrent connections per IP — the two things
segmentation needs — which is why `auto` prefers the ENA **HTTPS** mirror
(`https://ftp.sra.ebi.ac.uk/...`, same host, range-capable). The native FTP path
is exercised against hosts that do allow `REST` + concurrency.

## What is *not* in Part 2 (coming in Part 3)

- The gradient adaptive concurrency controller, batch parallel download, parallel
  metadata resolution (`-j/--jobs`, `--meta-jobs`, `--adaptive/--no-adaptive`,
  `--probe-window`, `--cc-penalty`), and the benchmark. Concurrency across files
  in Part 2 is fixed/uncontrolled; these flags are intentionally **not** present.

## Version mapping

| | Version string |
|---|---|
| upstream `iseq` ported from | `Version 1.9.8` |
| adaptiSeq | `adaptiSeq 0.1.0` |

## Deliberate divergences

Every place where adaptiSeq deliberately differs from the Bash is documented, with
its rationale, in [`NOTES.md`](NOTES.md) §5. In brief:

1. **Preflight runs after `--help`/`--version`** so those work without all seven
   external tools installed (the Bash checks tools before anything else).
2. **The retry counter resets per Run** (the documented "three rounds per Run"
   intent), rather than the Bash's process-global counter that can send later Runs
   straight to `fail.log` after one earlier hard failure.
3. **Input file detection** uses "path exists and is a regular file" instead of
   `file ... | grep text` + `sed -i` CRLF stripping (equivalent for the documented
   one-accession-per-line format; no libmagic dependency).
4. **Needs-based tool preflight:** metadata-only (`-m`) needs only `wget`; real
   downloads require the full tool set as the Bash does. Strictly more permissive,
   never more restrictive.
5. **GSA md5 retry** is a per-file loop (re-fetching only the failing file) rather
   than the Bash's recursive re-fetch of every file of the run; identical observable
   `success.log`/`fail.log` ID sets.
6. **The Bash `$$SaveName` quirk is corrected** in the "already downloaded" hint
   message (cosmetic stdout only).
7. **`adaptiseq.resolve`** (the public function) shadows the internal `resolve.py`
   submodule at the package namespace — a naming note for maintainers, not a
   behavioural change.

All divergences are cosmetic, strictly-more-permissive, or only observable after a
hard download failure; none affect the byte-for-byte metadata files, the resolved
URLs, or the success/fail ID sets on the common path.
