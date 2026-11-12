# Changelog

Notable changes to adaptiSeq. The newest release is first. Versions 0.1.4 to 0.1.11 were internal
builds that were never published; their changes are all in 0.1.12 and are listed below under the build that
made them.

## Unreleased: `adaptiseq --install-ascp`
ENA's Aspera server refuses the `ascp` 4.4.2 in conda's `aspera-cli` 4.14.0, and the `ascli` in that package does not
start in a fresh conda environment today (`cannot load such file -- webrick`; Ruby no longer bundles it), so
the advice in 0.1.14 to run `ascli config ascp install` did not work for a conda install.
- **`adaptiseq --install-ascp`** (and `adaptiseq.install_ascp()`) installs the IBM Aspera Transfer SDK 1.1.9
  (`ascp` 4.4.8, the version tested against ENA) and the public bypass key into `~/.aspera/sdk`. It asks first
  (`--yes` confirms; with no terminal and no `--yes` it refuses), shows the source URLs, size, checksums and
  IBM's terms, checks both downloads against pinned sha256 values before writing anything, writes only named
  files, and keeps an older `~/.aspera/sdk` as `sdk.old.<time>`. Linux x86_64 only. Nothing is installed
  automatically.
- A failed ENA Aspera transfer and the missing-`ascp` message now point to it.

## 0.1.14: Aspera works with ENA again, and a repeated accession is processed once
Checked against the recent issues of iSeq (BioOmics/iSeq #56 to #70): three applied to adaptiSeq and are fixed
below; the others did not reproduce (GSA metadata for the reported accessions, metadata beyond 5,000 records, runs with
more than two FASTQ links, the sample-ID pattern of the merge step, the input file's timestamp, CRLF lists).

### A repeated accession is processed once (iSeq #65)
A list that names the same accession twice (lists from several projects overlap) printed `The sequencing
file of run_accession is not available in all databases`, wrote the Run to `fail.log` and exited 1, although the
Run had downloaded and verified: both copies were resolved at the same time and wrote the same
`SRR….metadata.tsv`, and one read it half written. Each accession is now processed once, in order, with a note
that says how many repeats were ignored.

### A current `ascp` for ENA Aspera (iSeq #66 and #70)
ENA's Aspera server (OpenSSH 9.9) refuses the `ascp` 4.4.2 that the conda package `aspera-cli` 4.14.0
ships (`ascp: failed to authenticate`; original iSeq 2.0.0 fails the same way), so `-a` against ENA
did not work from a standard conda install. `ascp` 4.4.8 (IBM Aspera Transfer SDK 1.1.9, installed by
`ascli config ascp install`) works, and the live Aspera test passes with it.
- adaptiSeq runs the newer of the `ascp` on `PATH` and the one in `~/.aspera/sdk`, and looks for the
  ENA key next to it, so no `PATH` editing is needed after `ascli config ascp install`.
- A failed ENA Aspera transfer prints which `ascp` ran and how to get a current one.
- The documentation says which `ascp` versions were tested.

## 0.1.13: a Run whose ID starts another ID is no longer skipped
Fixes [issue #2](https://github.com/swargo98/adaptiSeq/issues/2), reported by skhakim. `success.log` and
`fail.log` matched IDs by substring (a port of iSeq's `grep -c $ID` and `sed -i "/$ID/d"`), so an ID that is
the beginning of another one collided with it:
- **A Run was skipped as already downloaded.** After `SRR1234` succeeded, `SRR123` was reported as
  downloaded and never fetched, with exit status 0.
- **A failure was erased.** When `SRR123` succeeded, the line of `SRR1234` was removed from `fail.log`.
- **The `sed` hint** printed for forcing a re-download would also delete the longer ID's line.

An ID now matches an entry only when the entry is that ID or a file name that starts with it and continues
with `_` or `.` (`SRR123_1.fastq.gz`, `SRR123.sra`), so `SRR123` no longer finds `SRR1234`. The hint, and the
examples in the documentation, use `sed -i -E '/[[:space:]]ID([^A-Za-z0-9]|$)/d' success.log`, which removes
the ID and its files and nothing else. `success.log` is also read once per run and refreshed when the file
changes, instead of being read again for every Run (10,000 lookups over a 10,000-line log took 12 s). Nothing
in the transfer engine changed; benchmarks of 0.1.12 apply.

## 0.1.12: first release since 0.1.3
This is the build the benchmarks in the accompanying manuscripts ran. In short:
- **Delivered means verified, and the exit status says so.** Each file is checked against the
  archive's md5 as it lands, and a bad copy is deleted and fetched again inside the pool. A Run that
  cannot be verified is written to `fail.log` and the exit status is 1. A Run that ENA cannot serve
  is fetched from NCBI SRA by default: the fallback is announced, and `--no-sra-fallback`
  refuses it (SRA copies cannot be checked against ENA's md5).
- **Metadata failures are not read as answers.** A failed or empty ENA query is retried (up to three
  minutes of failure, shared by a list) before a Run is declared absent.
- **Connections stay busy.** Files are split into ranges that idle connections take over, the
  per-host guard reads a refused connect as a ceiling to wait at, and spare connections are used in
  the tail of a list. GSA runs join the same parallel pool.
- **Five adaptive controllers** (`--controller topdown|bottomup|budget|greedy|knee`, or
  `fetch(controller=...)`); `topdown` stays the default. See
  [docs/ADAPTIVE_CONTROLLER.md](https://swargo98.github.io/adaptiSeq/ADAPTIVE_CONTROLLER/).
- **GSA and GEO work again** after both archives put browser checks on their pages.

### Details of the 0.1.12 build

- A GSA Run that GSA's run-info table leaves out is no longer skipped with exit 0.
  The table for a project sometimes comes back without one of its Runs; the
  Run's metadata CSV then held only a header, nothing was downloaded, and the
  tool printed "download finished". The run-info query is now retried (4 tries,
  2/4/8 s apart); if the Run is still missing, the accession fails, goes to
  `fail.log`, and the exit status is non-zero. A header-only CSV left on disk is
  fetched again instead of trusted.
- A per-host connection cap lowered by a refused connect or by pushback now
  climbs back by one connection every 5 s without a new refusal. It used to climb
  only on a clean new response, and on large files none comes while the cap is
  held at the open count: in the 0.1.11 controller tournament, runs that met an
  early refusal from ENA stayed at 25 connections where others reached 50, and
  GSA tails sank to one connection.
- When a controller holds files back in the queue and every active worker is
  busy, the running files may use the spare connection budget (as they already
  did once the queue was empty). Fixed `-j` runs are unchanged.
- `topdown` (the default controller) measures a worker count only once the files
  in flight have come down (or up) to it, waits 5 s after a step up for the new
  files to connect, keeps the higher count when large files do not drain within
  60 s, and steps down only when the lower count wins over two windows. It used
  to read the higher count's throughput right after a step down, and step down
  on it (many small ENA files: 2-5 workers where 20-50 connections were faster).
- ENA metadata retries are bounded by time rather than a count: a run waits up
  to 3 minutes of portal failure before it falls back to SRA, and the 3 minutes
  are shared by all accessions of a list (one outage costs a list about 3
  minutes, not 3 minutes per run). An empty answer that took more than 5 s is
  retried as a failure, not read as "not in ENA". With 0.1.11 the portal's slow
  hours sent runs to SRA, whose files cannot be checked against ENA's md5.
- A segment that runs out of its attempts but made progress continues on a new
  connection in the same pass; only one that keeps failing without progress ends
  the pass. On GSA, which cuts streams at any load, each segment that ran out of
  attempts used to stop its file from splitting for the rest of the pass, and the
  last minutes of a GSA download ran on a few connections.

### Details of the internal builds 0.1.4 to 0.1.11

#### 0.1.11 (internal build)
- A connect that times out is now handled like a refused connect: while other
  connections to the host are open it marks the host's connection ceiling and
  the segment waits for a free slot; with nothing open it is pushback, as
  before. It used to count as pushback every time, halving the host's
  connection cap and blocking the host for a backoff. GSA times connects out
  now and then at any load, so each timeout cut the `knee` and `budget`
  controllers' connection budget by 30 %.

#### 0.1.10 (internal build)
- **New controller candidate** `--controller knee`: keeps every worker active and
  finds the fewest connections that give near-full speed. It starts at 4,
  doubles while each doubling still earns at least half its proportional gain,
  settles on the smallest budget that paid, then holds and re-tests a quarter
  up or down now and then. Server pushback (429/503, refused connects with
  nothing else open, dropped connections) cuts it by 30 %; responses cut short
  of their length do not (GSA cuts streams at any load). With `-j` not given,
  it may use up to 64 workers, since it limits connections, not workers.
- A raised connection budget is filled at once: in-flight files split onto all
  the spare connections in one step instead of one per poll.

#### 0.1.9 (internal build)
- **Batch mode**: a download that fails but moves its resume point on (the
  bytes are kept) no longer uses up one of the file's three retries (capped
  at 20 such passes). Under a storm of cut-short responses, as GSA served at
  about 40 connections, large files used to run out of retries and fall back
  to the slow per-Run retry after the batch.
- A file downloaded on its own (the per-Run retry, single runs) may now split
  onto spare connections, like a batch file once the queue is empty.
- Responses cut short of their length are now recorded for the controllers;
  `budget` treats 3 or more in one window as distress. `budget` also keeps
  adjusting when every file started at once (the queue empty from the start);
  it only stops in the tail, when its budget is not filled.

#### 0.1.8 (internal build, superseded by 0.1.9)
- **New** `--controller NAME` (and `fetch(controller=...)`) picks the adaptive
  controller: `topdown` (the default, unchanged), `bottomup` (the original
  gradient optimizer), and two candidates under evaluation: `budget`, which
  keeps every worker active and steers a per-host connection budget (raise
  while it pays, cut when it does not or on server pushback), and `greedy`,
  which runs every worker and backs off only on HTTP 429/503. The default will
  be chosen from a benchmark on every archive adaptiSeq supports.
- **Fix (GSA)**: GSA's browse page now answers scripts with a browser check and
  no links, so GSA runs had nothing to download. Links now come from the
  run-info table GSA's API returns, fetched from `download.cncb.ac.cn` over
  HTTPS (`-r ftp` keeps `download.big.ac.cn` FTP; Aspera unchanged).
- **GSA in batch mode**: GSA runs now join the parallel pool with the other
  archives (they downloaded one file at a time), with md5 checks in the pool
  from the project's `md5sum.txt`.
- **Fix (GEO)**: GEO's accession page now answers scripts with a reCAPTCHA
  page, so every GSE/GSM was rejected as invalid. GSE now resolves to its
  BioProject through NCBI E-utilities (GEO DataSets), GSM to its BioSample
  (BioSample lists the GSM), within NCBI's request rate; GEO's plain-text
  record and the page remain as fallbacks.
- **Fix (GSA)**: the project's `md5sum.txt` is fetched with retries, and an empty
  one (left by a refused connection) is fetched again. Previously a failed fetch
  meant every file of the project was recorded as downloaded without an md5
  check. Without an md5 list the file's size must match the run-info table, and
  the note says the file is not md5-verified.
- **Fix (GSA)**: after an md5 mismatch the bad file is deleted before the first
  retry, so the retry downloads again instead of re-checking the same bytes.

#### 0.1.7 (internal build, used for the benchmark)
- **Fix**: a range probe that gets no answer (refused, reset, timed out) is
  retried, and waits at the host's connection limit like a segment does.
  Previously it was read as "the server has no ranges" and the whole file
  went over one connection; when ENA refused a few probes, 1.5 to 2 GB files
  downloaded single-stream for 15 to 30 min each. A probe that never gets an
  answer now fails the file (the batch retries it); transport selection still
  falls back to FTP when HTTPS never answers.

#### 0.1.6 (internal build, used for the benchmark)
- **Segmented HTTPS** keeps a file's connections busy to the end: when a
  segment finishes, its connection takes over half of the largest remaining
  piece of the same file, and once the batch queue is empty, unused per-host
  connection budget splits in-flight files further (up to `--max-segments`).
  Previously the last bytes of each file arrived on one connection; on a
  16-file, 26 GB list that tail took 15 of 26 minutes.

#### 0.1.5 (internal build, used for the benchmark)
- **Fix**: an ENA metadata query that fails (HTTP 500, timeout, network error)
  or comes back with no rows is no longer read as "not in ENA". Previously such
  a Run went to the SRA fallback, and the converted FASTQ could not be checked
  against ENA's md5; during an ENA portal outage this hit whole lists. A failed
  query is now retried like the error body (4 tries, 2/4/8 s apart); an empty
  answer is retried once, so a Run that is really SRA-only costs one extra query.
- **Batch mode** (`-j`) now says which accessions are downloaded from SRA
  instead of ENA ("N accession(s) had no usable ENA metadata and will be
  downloaded from SRA: ..."). Previously that fallback was silent until each
  Run's verification note.
- **New** `--no-sra-fallback`: a Run with no usable ENA metadata or file fails
  (exit 1; in a list it goes to `fail.log` and the rest continue) instead of
  being fetched from NCBI SRA, so every file that is kept was checked against
  ENA's md5. A cached SRA runinfo file from an earlier run is queried again on
  ENA. Cannot be combined with `-d sra`.
- **Batch mode** checks each `.fastq.gz` against ENA's md5 as soon as it lands.
  A corrupt transfer is deleted and downloaded again inside the pool, in
  parallel with the other files, instead of after the batch, one file at a
  time. The per-Run check reuses the digest rather than hashing the file twice.
  On a 26 GB, 16-file list with several corrupt transfers, the serial retries
  had taken 1.5 to 2.5 h of a 2 to 3 h run.
- **Fix**: a refused connect while other connections to the same host are open
  is treated as the host's connection limit (ENA refuses some connects once a
  client has many open). The per-host cap is held at the number of open connections
  and the segment waits for a slot. Previously each refusal halved the cap,
  blocked the host for a backoff, and used up one of the segment's three
  attempts, so a few refusals could fail a whole file.
- **Batch mode**: a file that starts near the end of a batch (or is fetched
  again after an md5 mismatch) shares the per-host connection budget with the
  files still to do, so it may use up to `--max-segments` segments of at least
  64 MiB. Previously its split was fixed at `size // --segment-size` (three for
  a 1.6 GB file), and the last files of a batch ran on one to three
  connections. A resumed download keeps the split it started with.

#### 0.1.4 (internal build)
- **Fix**: `-g` on a Run with no ENA FASTQ mirror (SRA-only, e.g. `SRR1031066`)
  no longer exits with code 1 and a `fail.log` entry after producing complete
  FASTQ. The `.sra` is now validated with `vdb-validate`, recorded in
  `success.log`, and not re-downloaded.
- **Fix**: after an MD5 mismatch, the mismatching file is deleted before the
  first retry, so every retry is a fresh download. Previously the first retry
  found the full-size file, treated it as already complete, and re-checked the
  same bytes.
- **Fix**: ENA's portal sometimes answers a metadata query with an in-band
  error (`ERROR occurred. Not all results may have been written...`). adaptiSeq
  took that line for a Run, cached it as the accession's `.metadata.tsv`, and
  lost the accession. The error body is now retried (4 tries, 2/4/8 s apart,
  then the SRA fallback) and a cached error body is fetched again.
- **Fix**: in an accession list, one accession that cannot be resolved or
  downloaded no longer stops the rest. It is reported, written to `fail.log`,
  and the run continues (exit status 1 at the end). Previously
  the verification pass after a batch download stopped at that accession, so
  later Runs were neither md5-checked nor retried. A single accession still
  raises as before.
- **Fix**: resume state left without its data (`.part.meta` present, `.part`
  gone) is discarded instead of resumed. Previously a re-download after an MD5
  mismatch could fetch only the segments that state listed as unfinished and
  leave the rest of the file as zeros; segmented FTP could also report success
  with no file written. A single-connection download now also clears the resume
  state of an earlier segmented attempt.
- **Docs**: the `LICENSE` file reproduces the MIT notices of the two earlier tools
  this code descends from (see [Acknowledgements](#acknowledgements)). Comparison
  table updated for Kingfisher 0.5.0 (Python API, experimental GSA) and pysradb
  2.5.1 (`--threads`).

## 0.1.3
- **Fix**: a segmented download whose `.part` file is missing at finalize (e.g.
  every segment's connection was refused) now fails cleanly and retries, instead
  of raising a confusing `FileNotFoundError` from an unguarded `.part` rename.

## 0.1.2
- **Fix**: the notebook event-loop handling from 0.1.1 now also works when
  `nest_asyncio` is active (it previously hung/errored on batch downloads). The
  API detects a re-entrant loop and drives the coroutine on it directly; plain
  Jupyter still uses a worker thread. Works with or without `nest_asyncio`.

## 0.1.1
- **Fix**: the Python API (`fetch`/`resolve`) now works inside a running asyncio
  event loop (Jupyter / Google Colab / IPython), where it previously raised
  `asyncio.run() cannot be called from a running event loop`. The CLI was
  unaffected.

## 0.1.0 (initial release)
- First public release: segmented engine + adaptive batch pool + parallel
  metadata resolution + adaptive Aspera + Python API.
- Validated against the **real ENA Aspera** endpoint with a genuine IBM `ascp`.
- Offline test suite (fixtures, engine, batch, adaptive) green; CI on Python
  3.10–3.12.
