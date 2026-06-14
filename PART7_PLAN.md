# Part 7 plan — system benchmark harness (publication), separate from the package

A **standalone** benchmark that measures, per tool, the **system resource cost** of a
download — average I/O, memory, CPU% — with a **per-second breakdown across the four
task phases**:

1. **send request** (process start → first network byte / first API call issued),
2. **fetch metadata** (resolve accession → metadata rows / URLs),
3. **fetch NGS data** (the actual sequence-file bytes),
4. **MD5 check** (integrity verification).

Tools to compare: **edgeturbo, pysradb, SRA Toolkit (`prefetch`), iseq**, plus
**adaptiSeq** (classic / segmented / adaptive). This is **publication evidence**
(FastBioDL / iSeq Figure-1-style), explicitly **kept out of the `adaptiseq/`
package** — it lives in its own top-level `sysbench/` dir and ships separately (and
is excluded from the sdist).

## Design principles

- **Separate from the package.** Nothing in `sysbench/` imports private package
  internals beyond the public `adaptiseq` CLI/API; it treats every tool, including
  adaptiSeq, as an external command. So it can be released/cited independently and
  never affects package tests or the sdist.
- **Per-process + children sampling.** A psutil sampler walks the tool's process
  tree at a fixed cadence (default 1 Hz). `ascp`, `wget`, `prefetch`, `pigz`,
  `fasterq-dump` are children/subprocesses, so tree-walking is mandatory.
- **Phase tagging by wall-clock windows.** Each adapter emits phase-boundary
  timestamps; the sampler tags every 1 s sample with the phase active at that
  instant. Phases that a given tool fuses (e.g. a tool that streams data while
  still resolving) are marked `overlapped` rather than forced apart.
- **Fairness.** Same accession set, same machine, files deleted between methods,
  N≥3 repeats, randomized method order, cold-cache note, record bytes+format so
  CPU/mem/IO are comparable. Mirror the report's §D reproducibility rules.

## Components

### 1. The sampler — `sysbench/sampler.py`
- Wrap `psutil.Process(pid)`; each tick collect, summed over the process + all
  `children(recursive=True)`:
  - `cpu_percent` (per-core normalized + absolute),
  - `memory_info().rss` (sum and peak),
  - `io_counters().read_bytes / write_bytes` (delta/s → read & write rate),
  - system-wide `net_io_counters` delta/s (bytes recv/sent) as the network proxy
    (per-process net isn't portable without root; document this).
- Emit one row per second: `t, phase, cpu_pct, rss_mb, read_mbps, write_mbps,
  net_recv_mbps, net_sent_mbps`.
- Handle short-lived children (catch `NoSuchProcess`), and processes that exit
  between ticks (accumulate last-seen IO so totals don't drop).

### 2. Phase harness — `sysbench/phases.py`
- A `Run` context that records `phase_start(name)` markers into a shared timeline
  the sampler reads. Phases: `request`, `metadata`, `data`, `md5`.
- For tools that expose discrete steps, drive each phase as its own subprocess and
  time it exactly. For monolithic tools, derive phase windows from the tool's own
  stdout/stderr log markers (best-effort) and label uncertainty honestly.

### 3. Tool adapters — `sysbench/adapters/`
One adapter per tool, each returning a list of `(phase, argv)` steps + a parser:
- **adaptiseq** — `get_metadata`/`resolve` for metadata phase, `fetch` for data,
  built-in md5 for the md5 phase (or `--skip-md5` toggled to isolate it).
- **iseq** — needs stock `iseq` installed (currently MISSING). Install it (it is a
  Bash script; vendor `iSeq-main/bin/iseq` onto PATH). Real `ascp` from Part 6.
- **sra-toolkit** — `prefetch` (request+data), `vdb-validate` (md5);
  metadata via `srapath`/`vdb-dump` or pysradb as a stand-in if needed.
- **pysradb** — `pysradb metadata`/`pysradb download` (metadata + data); MISSING,
  `pip install pysradb`.
- **edgeturbo** — ✅ located + installed (NGDC GSA accelerator v1.3.3, GSA-only,
  daemon-based, driven under a pty). Provision: `bench/setup_edgeturbo.sh`.
  **Transport stalls at 0% from the US sandbox** (NGDC accelerated UDP transport
  unreachable here; ENA Aspera to EBI works) — adapter reports the stall honestly;
  run from an NGDC-reachable network for real numbers. The iSeq paper uses edgeturbo
  for **GSA** (it gave 11.30 MB/s there); confirmed via `papers/btae641.pdf` Fig. 1D,
  whose phases (Send request / Fetch metadata / Fetch NGS data / MD5 check) and
  metrics (%CPU, Memory, Average I/O) this harness reproduces.

### 4. Runner + reporting — `sysbench/run_bench.py`, `sysbench/report.py`
- CLI: `python -m sysbench.run_bench --tools ... --accessions list.txt --repeats 3
  --out runs/`.
- Per run: launch adapter steps under the sampler, write raw per-second CSV
  (`runs/<tool>/<acc>/<rep>/trace.csv`) + a `meta.json` (versions, host, bytes,
  format, exit code, phase boundaries).
- `report.py` aggregates: mean/peak CPU, mean/peak RSS, mean read/write MB/s, total
  bytes, and a **per-phase, per-second** breakdown table + matplotlib plots
  (stacked phase timeline, CPU/mem/IO bars). Emit `sysbench/RESULTS.md`.

### 5. Environment capture — `sysbench/envinfo.py`
- Record tool versions, CPU/mem/NIC/disk, OS, Python + lib versions, and an
  optional `iperf3`/disk-write probe, per report §D.

## Validation (so the harness itself is trustworthy)
- Sampler unit tests against a synthetic workload (a script that burns known CPU,
  allocates known RSS, writes known bytes) → assert measured ≈ expected within
  tolerance.
- Phase-tagging test: a fake adapter with scripted sleeps per phase → assert each
  second is tagged to the right phase.
- A dry-run mode that uses tiny accessions so the whole matrix runs in minutes.

## Deliverables
- `sysbench/` (excluded from package sdist via MANIFEST/pyproject).
- Raw per-second traces + `sysbench/RESULTS.md` + plots.
- A short methods paragraph for the paper describing the sampler and phase model.

## Build order
1. Plan (this file). 2. `sampler.py` + unit tests. 3. `phases.py` + tagging test.
4. adaptiseq + sra-toolkit adapters (both installed) → first real traces.
5. Install + add pysradb adapter. 6. Install stock iseq (+ real ascp) adapter.
7. edgeturbo adapter or documented exclusion. 8. runner + report + plots.
9. envinfo + reproducibility wrapper. 10. RESULTS.md + paper methods paragraph.
