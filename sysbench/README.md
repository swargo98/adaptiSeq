# sysbench — adaptiSeq system benchmark (publication harness)

A **standalone** benchmark, deliberately kept **out of the `adaptiseq` package**
(`pyproject.toml`'s `packages.find` only includes `adaptiseq*`, so this dir never
ships in the wheel/sdist). It measures the **system-resource cost** of a download —
average/peak **CPU%, memory (RSS), disk I/O**, and network — with a **per-second
breakdown across the four task phases**:

1. **request**  — process launch → first network byte / first API call
2. **metadata** — accession resolution → metadata rows / resolved URLs
3. **data**     — transfer of the actual NGS sequence-file bytes
4. **md5**      — integrity verification

It treats every tool — including adaptiSeq — as an external command, so results are
comparable and the harness can be released/cited independently of the package.

## Layout

```
sysbench/
  sampler.py      # 1 Hz process-tree sampler (CPU/RSS/IO + system net), phase-tagged
  phases.py       # PhaseTimeline shared between adapter and sampler
  run_bench.py    # runner: per tool×accession×repeat under the sampler → raw traces
  report.py       # aggregate traces → per-phase table + RESULTS.md (stdlib only)
  adapters/       # one per tool (adaptiseq, sra-toolkit, pysradb; iseq/edgeturbo TODO)
  runs/           # output: <tool>/<acc>/repN/{trace.csv,meta.json} + RESULTS.md
```

## Usage

```bash
# from the repo root
python -m sysbench.run_bench \
    --tools adaptiseq adaptiseq-classic sra-toolkit pysradb \
    --accessions ERR16961540 SRR22904257 \
    --repeats 3 --shuffle --out sysbench/runs
python -m sysbench.report --runs sysbench/runs   # writes sysbench/runs/RESULTS.md
python -m sysbench.plot   --runs sysbench/runs   # writes sysbench/runs/plots/*.png
```

`plot.py` reproduces the iSeq paper's **Fig. 1D** style: a per-second phase-banded
timeline per run (request/metadata/data/md5 shaded, with net/disk/CPU/RSS overlaid)
plus grouped summary bars (wall time, peak CPU, peak RSS, data-phase throughput).
Sample artifacts from a real 4-tool run are in `sysbench/sample_plots/` +
`sysbench/RESULTS.sample.md`.

`--shuffle` randomizes method order per repeat (cache fairness). Files are deleted
between runs. Each `meta.json` records bytes + format + exit codes + phase durations,
so wall-clock/CPU/IO stay comparable across tools that fetch different payloads
(adaptiSeq/iSeq fetch `.fastq.gz`; `prefetch` fetches `.sra` — different bytes).

## Metrics & caveats

- `*_mbps` columns are **megabytes/s** (decimal, 10⁶ B), matching download-tool
  reporting — not megabits.
- **Network is system-wide** (`net_io_counters` deltas). Per-process net counters
  need root and aren't portable; for a quiet benchmark host the system delta is a
  good proxy. For `data`-phase throughput, prefer `net_recv_mbps`/`write_mbps`.
- **CPU/RSS/IO are summed over the process tree** (`ascp`/`wget`/`prefetch`/`pigz`/
  `fasterq-dump` are children). Short-lived children are handled; a child exiting
  mid-tick can briefly undercount cumulative IO (rates are clamped ≥ 0).
- Meaningful per-phase traces need a `data` phase spanning several seconds; for
  tiny files the whole run fits in ~1 sample. Use mid/large accessions.
- Phase boundaries are marked by each adapter. Tools that fuse phases (stream data
  while resolving) should mark `overlapped` rather than force a split.
- **md5-phase isolation** uses a "re-run the tool over already-present files" trick.
  adaptiSeq recognises complete files and only md5-checks (md5-phase write ≈ 0), but
  **stock iSeq and `adaptiseq --engine classic` re-download** on the second pass, so
  their md5-phase write rate reflects a re-fetch, not pure verification. This is
  itself an informative difference (resume/skip behaviour); for a strict md5-only
  number use the data-phase-with/without-`-k` delta instead.

## Tool status

| tool | adapter | status |
|---|---|---|
| adaptiseq (adaptive/classic/segmented) | ✅ | runs (fastq.gz via ENA) |
| sra-toolkit (`prefetch` + `vdb-validate`) | ✅ | runs (.sra) |
| pysradb | ✅ | metadata runs; `download` needs a **study** accession (run-level fails — reported honestly), no md5 phase |
| iseq | ✅ | runs (.fastq.gz); `iSeq-main/bin/iseq` symlinked onto PATH + real `ascp` |
| edgeturbo | ⚠️ | **installed & runnable** (NGDC GSA accelerator v1.3.3); GSA-only, daemon-based, driven under a pty. Transport **stalls at 0% from this US host** (NGDC UDP-accelerated transport unreachable here — ENA Aspera to EBI works). Run from an NGDC-reachable network for real numbers. Provision: `bench/setup_edgeturbo.sh`. |

EdgeTurbo takes a **GSA remote path** as its "accession", e.g.
`python -m sysbench.run_bench --tools edgeturbo --accessions /gsa/CRA004720/CRR311238/CRR311238.fq.gz`.

## Validation

The sampler is unit-validated against synthetic workloads: a CPU-burn child reads
~100% for one core; a known-byte writer integrates to the written total; phase tags
follow scripted sleeps. See `tests/` (added with the harness).
