# adaptiSeq Part 2 of 3: The segmented download engine (fixed concurrency)

> This is the second of three build specifications. It assumes **Part 1 is
> complete**: a faithful Python port of `iseq` exists, all parity tests pass, and
> there is a clean engine seam (Part 1, Section 5.1) where exactly one resolved
> URL is downloaded to one output path.
>
> Part 2 adds a multi-segment, range-based, resumable HTTP(S)/FTP download engine
> and wires it into that seam as the new default. Concurrency in Part 2 is
> **fixed**, not adaptive: the gradient controller, batch overlap, and parallel
> resolution all arrive in Part 3. Keep that boundary. Do not implement the
> optimizer here.

---

## 0. Objective and the one thing that must not change

Replace the classic `wget`/`axel` call site from Part 1 with a segmented engine,
and nothing else. The engine is a drop-in transport. It must **not** influence
which URL is selected, which database a file comes from, the metadata, the
integrity policy, the logs, or the merge logic. All of that was settled in Part 1
and stays byte-identical. The Part 1 differential tests (live and fixture modes)
must still pass after Part 2, now exercising the segmented path.

`--engine classic` must remain available and behave exactly as Part 1. Part 2
makes `--engine segmented` the default but keeps classic as the fallback for hosts
that cannot serve ranges.

---

## 1. Inputs you must read first

| File | Why it matters in Part 2 |
|------|--------------------------|
| `fastbiodl_upgrade.py` | Source of the segmented downloader. Extract the `SegmentedDownloader` class (roughly lines 63 to 777): range probing, segment calculation, concurrent segment streaming, `.part`/`.part.meta` resume, single-connection fallback, retry with backoff. See Sections 3 and 4 for exactly what to keep and discard. |
| `search.py`, `utils.py` | Read only to confirm what `fastbiodl_upgrade.py` imports from them. You do **not** port the gradient optimizer (that is Part 3) or the disk-reservation helpers (discarded entirely). |
| Part 1 source (`adaptiseq/`) | The engine seam you are plugging into, and the `resolve.py` output you are downloading. |

Do not assume the contents of these files. Open and read them. In particular,
read the `SegmentedDownloader` methods closely before porting, because the class
is **not self-contained** (Section 2).

---

## 2. The class you are porting is entangled; decouple it first

`SegmentedDownloader` in `fastbiodl_upgrade.py` reaches into module-level globals
and multiprocessing shared state from inside its own methods. For example,
`download_segment_streaming` reads `download_process_status[self.process_id]` to
detect pause, reads the module global `download_dir` for free-space checks, and
calls `available_space_bytes` directly. "Extract the class" therefore is not a
copy-paste; it is surgery. Before porting, make the class self-contained:

- It takes its output directory and an `aiohttp.ClientSession` as constructor
  arguments, not from globals.
- It takes a **pause token**: an awaitable or a cheap callable the streaming loop
  checks to decide whether to keep going, cancel, and re-queue. In Part 2 wire
  this token to a constant "always run" value, because there is no adaptive
  controller yet. Part 3 replaces it with the gradient gate. Designing the seam
  now means Part 3 changes one object, not the streaming loop.
- It reports bytes through an injected counter callback, not through an
  `mp.Value`. Part 2 uses this only for a simple progress display; Part 3 feeds it
  into the throughput meter.

The result must be a self-contained engine module that depends only on `aiohttp`,
`aioftp`, the standard library, and your own code.

---

## 3. Keep (port faithfully into `adaptiseq/engine/segmented.py`)

- **Range-support probing** (`probe_range_support`): a single `Range: bytes=0-0`
  GET. `206` confirms ranges and `Content-Range` gives total size. `200` means no
  ranges; use `Content-Length`. Cache the per-host result for the run.
- **Per-file connection count, decided by file size, not by any optimizer.** Each
  download opens a number of segment connections derived from that file's size:
  `connections = min(max_segments, max(1, file_size // segment_size))`, honouring
  `--segment-size` and `--max-segments`, with the per-host cap of Section 6
  applied on top. `max_segments` is a ceiling: small files open few connections,
  large files are capped at `max_segments`. The last segment takes the remainder
  bytes. This matches the original `calculate_segments`; do not invert it.
- **Concurrent segment streaming** (`download_segment_streaming`): each segment is
  a separate ranged GET written to the correct offset of a single `.part` file via
  `os.pwrite`. Validate that the returned `Content-Range` matches the request and
  that the full expected byte count arrived. Strict `206` enforcement.
- **Resume via `.part` + `.part.meta`**: JSON metadata with `file_size`,
  `segments`, `completed_indices`, and `partial_offsets`, written atomically
  (temp file, `fsync`, `os.rename`). On restart, validate metadata against the
  current file size and segment plan; resume incomplete segments from their
  partial offsets; treat a metadata mismatch as a clean restart.
- **Atomic finalize**: `os.rename(part_path, local_path)` only when every segment
  is complete, then remove the `.meta`.
- **Single-connection fallback** (`download_single_connection`) for servers that
  do not support ranges, with its own resume-from logic.
- **Retry with exponential backoff** (`max_retries`, default 3) at the segment
  level, consistent with the existing `2 ** attempt` backoff.
- **Speed limiting**: implement a token-bucket or sleep-based rate cap honouring
  `-s/--speed` (MB/s), shared across a file's segments. The original relied on
  external machinery; you must implement a simple, correct limiter in
  `engine/ratelimit.py`.

---

## 4. Discard (do not port, do not import)

- `config_fastbiodl`, `storage_config`, `get_nvme_device`, tmpfs handling.
- Disk-space reservation: `reserve_disk_space`, `release_disk_space`,
  `disk_reserved_bytes`, `min_pending_conversion_bytes`,
  `disk_safety_margin_bytes`, and the `available_space*` gating inside the
  streaming loop. Replace with a single cheap free-space check before a download
  starts. If you want a guard, keep it minimal and out of the hot loop.
- The multiprocessing plumbing: `download_process_status`, the `mp.Value`
  counters, `report_network_throughput` as written. The pause/byte-count seams in
  Section 2 replace them.
- `converter.SRAConverter` and the in-engine conversion handoff. Conversion stays
  the separate, explicit `convert.py` step from Part 1, invoked after a successful
  download exactly where `iseq` invokes it.
- `ncbi_lookup` as an engine dependency. URL resolution already comes from Part
  1's `resolve.py`.

---

## 5. Transport: segmented FTP as well as HTTP(S), and how to choose

`iseq` defaults to `ftp://` links for ENA and GSA, but FTP can be downloaded in a
segmented, resumable way, so do not confine the engine to HTTP. The only real
constraint is the client library: `aiohttp` does not speak FTP.

- **HTTP/HTTPS path:** the `aiohttp` range engine of Section 3, with `Range`
  headers and strict `206` validation.
- **FTP path** (`engine/ftp.py`): an async FTP client that supports `REST`
  (restart at offset), such as `aioftp`. For each segment open a connection, issue
  `REST <start>` then `RETR <file>`, read exactly `(end - start + 1)` bytes,
  write them at the right offset with `os.pwrite`, then close the connection. FTP
  has no server-side end offset, so the client must bound its own reads and close
  when the segment is full. The same `.part` + `.part.meta` resume metadata
  applies unchanged. FTP differences to handle: there is no `Content-Range` to
  validate against, so validate by byte count and a final size or md5 check, and
  be stricter about short reads.

### 5.1 Transport selection: prefer HTTPS, confirm with a short probe

When `-r/--protocol` is given explicitly, honour it: `-r https` forces the HTTPS
mirror, `-r ftp` forces the native FTP path. That override is final.

When the protocol is left at auto, the recommended default is **the HTTPS
mirror**, for a concrete reason: EBI restricts FTP `REST` and caps concurrent
connections per IP, and segmentation depends on exactly those two things. The HTTPS
mirrors (`https://ftp.sra.ebi.ac.uk/...` for ENA, and the `httpsLink` already
captured by `downloadGSA` for GSA, served from `https://download.cncb.ac.cn/...`)
generally honour `Range` and parallel connections cleanly. So HTTPS is both more
likely to be segmentable and less likely to throttle, which makes it the faster
path in practice for these hosts.

Do not hardcode that assumption blindly. Run a short, cheap, **per-host
(not per-file)** transport probe once per run and cache the verdict:

1. Issue a `Range: bytes=0-0` GET to the HTTPS mirror. A `206` with a valid
   `Content-Range` marks HTTPS as range-capable.
2. Check the FTP host for `REST` support and that a second concurrent data
   connection is accepted (open one at offset 0 alongside a control channel).
3. Decide, in this order:
   - HTTPS is range-capable: use it. (Expected outcome for ENA and GSA.)
   - HTTPS not range-capable but FTP supports `REST` and concurrency: use
     segmented native FTP.
   - Only single-stream works on either: use single-connection download with
     resume.
   - Neither serves ranges at all: fall back to `--engine classic`.
4. Log which transport was chosen and why. Never emit a zero-byte or truncated
   file under any fallback.

This satisfies the requirement to both name a default (HTTPS, for speed and
availability on these hosts) and confirm it cheaply at runtime rather than trust
it. Aspera (`-a`) is unchanged and never goes through this engine.

---

## 6. Connection etiquette and the per-host cap (always on)

Even with fixed concurrency in Part 2, a single large file can open up to
`--max-segments` connections to one host, and Part 3 will multiply that across
active workers. Implement a **global per-host connection cap** now, in
`engine/ratelimit.py`, that bounds total in-flight connections to any one host
across the entire run, independent of the per-file count. Default range 8 to 16,
configurable via `--max-conns-per-host`. The segmenter must acquire from this cap
before opening a segment connection and release on close. Build it now because
Part 3's worker pool relies on it as the binding safety bound.

Add a **reactive circuit breaker** alongside the static cap: if a host returns
`429`, `503`, or refuses connections, back off that host globally with
exponential delay and temporarily lower its effective cap, then recover slowly.
The static cap alone does not respond to a server that starts pushing back under
load; the breaker does. Log every trip and recovery.

---

## 7. New flags introduced in Part 2

| Flag | Default | Semantics |
|------|---------|-----------|
| `--engine [segmented\|classic]` | `segmented` | `segmented` uses the new engine (now the default). `classic` is the Part 1 `wget`/`axel` path, used automatically when a host cannot serve ranges. |
| `--segment-size` | `512` | Target segment size in **MB**; with `--max-segments` it sets each file's connection count (Section 3). |
| `--max-segments` | `8` | Ceiling on connections per file: `min(max_segments, max(1, size // segment_size))`. |
| `--max-conns-per-host` | `8` to `16` | Global cap on concurrent connections to any one host (Section 6). |
| `-s, --speed` | `1000` | Speed cap in MB/s, now applied by the engine's token-bucket limiter (and still to `ascp`). |

`-p, --parallel N` from `iseq` becomes an **alias that sets `--max-segments N`**
for backward-compatible command lines, with a one-line note printed when used.
Document this in `--help`. (In Part 1 it kept its original `axel` meaning; on the
segmented default it now maps to segment count.)

`-j/--jobs` and the adaptive flags are still **not** added in Part 2. Part 2
downloads files one at a time through the seam, or with a small fixed pool if you
already have batch input from Part 1; either way concurrency across files is fixed
and uncontrolled. Do not add `--adaptive`, `--probe-window`, `--cc-penalty`, or
`--meta-jobs` here.

Update `iSeq.yml` to add `aiohttp` and `aioftp`. Do not add `numpy`, `skopt`, or
`scipy` yet.

---

## 8. Acceptance criteria for Part 2

1. A small real download over the segmented engine produces a **byte-identical**
   file to what `iseq` and the Part 1 classic engine produce, passes the
   MD5/`vdb-validate` check, and writes the ID to `success.log`.
2. All Part 1 differential tests (live and fixture modes) still pass with the
   segmented engine as default.
3. Interrupting a download mid-file and rerunning resumes from `.part.meta` rather
   than restarting, and produces a byte-identical final file.
4. An `https://` mirror link downloads segmented with strict `206` validation.
5. An `ftp://` ENA link is handled by the transport probe of Section 5.1: it
   either downloads segmented over native FTP, or the probe selects the HTTPS
   mirror, or it falls back to single-stream or classic. In no case is a corrupt
   or zero-byte file produced. The chosen transport and reason are logged.
6. A server that refuses `REST` or extra connections degrades to single-stream or
   classic without corruption.
7. The per-host cap is respected: total in-flight connections to one host never
   exceed `--max-conns-per-host`, verified by a test with a small cap.
8. The reactive circuit breaker trips on a simulated `429`/refused host and
   recovers, verified by a unit test against a mocked server.
9. The engine module is self-contained: importable with only `aiohttp`, `aioftp`,
   and the standard library, with no reference to `fastbiodl` globals,
   multiprocessing, or tmpfs.

Where the sandbox is offline, exercise the deterministic parts as unit tests: the
segment calculation, the `.part.meta` resume bookkeeping, the FTP `REST`/segment
accounting against a local or mocked server, the per-host cap, and the circuit
breaker. State clearly which paths were exercised live and which were only
unit-tested. Do not claim a download path works if you could not execute it.

---

## 9. How to work

1. Read the `SegmentedDownloader` source and confirm exactly what it imports and
   which globals it touches. Write the decoupling plan (Section 2) first.
2. Build in this order, testing each before the next: range probing in isolation
   against a known public test URL; the HTTP segmented path with resume; the
   token-bucket limiter; the per-host cap and circuit breaker; the transport probe
   and HTTPS-vs-FTP selection; the native FTP segmented path; then wire the engine
   into the Part 1 seam and rerun the Part 1 differential tests.
3. Commit at each milestone.
4. Record in `NOTES.md` any divergence from the Bash transport behaviour, the
   transport-probe verdicts you observed per host, and any host that refused
   segmentation.
5. Update `CHANGES_FROM_ISEQ.md` with the segmented engine, the transport
   selection rule, and the known FTP `REST` constraint on EBI.

Correctness and parity over speed. The segmented engine is the only place novelty
is wanted in Part 2, and it is novelty in *how* bytes arrive, never in *which*
bytes.
