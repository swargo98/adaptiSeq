# Part 6 plan — real Aspera (proper `ascp`) + adaptive-Aspera validation

The Part 5 adaptive-Aspera path was only ever exercised against a **no-op `ascp`
stub** and synthetic throughput curves (HANDOFF "Honest limitations" #2). The user
wants the real thing: download with a **genuine IBM `ascp` binary, configured like
`iseq`**, and prove the hysteresis controller works on real bytes.

Good news from the environment probe:
- `fasp.sra.ebi.ac.uk:33001` (ENA Aspera) is **reachable/OPEN** from the sandbox.
- The IBM **Aspera Transfer SDK** (`https://ibm.biz/aspera_sdk` → `sdk.zip`, ~167 MB)
  is downloadable and ships a real `ascp` + the ENA public key
  (`asperaweb_id_dsa.openssh`).

So unlike Part 5, a real end-to-end ENA Aspera run is actually possible here.

Commit at each milestone so a usage-limit pause resumes cleanly.

## Item 1 — acquire a real `ascp` (replace the stub)

- Download the IBM Aspera Transfer SDK and extract the Linux `ascp` binary +
  bundled keys into a stable prefix, e.g. `~/.aspera/sdk/` with `bin/ascp` and
  `etc/<keys>`.
- Put real `ascp` first on `PATH` (move/disable the `~/.local/bin/ascp` no-op stub;
  keep a copy as `ascp.stub` for the iseq-benchmark startup-check use case, and
  note in HANDOFF that the stub is gone from the live-Aspera path).
- Verify: `ascp --version` prints a real IBM build.

## Item 2 — key discovery faithful to `iseq`, with an ENA fallback

`iseq` (and our `find_ena_aspera_key`) look for, relative to `$(dirname ascp)/..`:
`etc/aspera/aspera_bypass_rsa.pem` then `etc/aspera_tokenauth_id_rsa`. The SDK ships
the ENA-documented key under a different name (`asperaweb_id_dsa.openssh`).

- First try to satisfy the iseq paths exactly (symlink/copy the SDK key into
  `<prefix>/etc/aspera/aspera_bypass_rsa.pem`) so behaviour is byte-identical to
  `iseq` key resolution.
- Add `asperaweb_id_dsa.openssh` to `ena_aspera_key_candidates()` as a documented
  fallback (it is the public key ENA actually publishes), so real ENA transfers work
  out-of-the-box with a stock SDK. Keep the iseq paths first for parity.
- Unit test the candidate list + discovery against a temp prefix.

## Item 3 — single-file real `ascp` sanity transfer

- Resolve one small ENA `.fastq.gz` URL (reuse `resolve()` / the small subset list),
  rewrite to `era-fasp@fasp.sra.ebi.ac.uk:<path>`, and run the **exact** command our
  `ClassicEngine.fetch_aspera` builds:
  `ascp -QT -P 33001 -i <key> -l <speed>M -k1 -d <link> .`
- Confirm the file lands, then md5-check it via the existing `integrity` path.
- This validates link rewriting, key, port, and return-code handling on real `ascp`
  before involving the pool.

## Item 4 — real adaptive-Aspera batch run (the actual deliverable)

- Run `AsperaBatchDownloader` over a handful of real ENA fastq.gz files
  (`-a`, segmented engine off for the aspera path), once **`--no-adaptive`** (fixed
  `-j`) and once **adaptive** (hysteresis).
- Capture for each: wall time, bytes, MB/s, the **worker trajectory** (`controller
  .trajectory`), the per-second `DirGrowthMeter` trace, and md5 pass/fail.
- This replaces synthetic curves with a real saturation curve and shows whether the
  efficiency-hysteresis controller settles sensibly against EBI's per-session caps.
- Record results in `BENCHMARK.md` (new "Real Aspera" subsection) + raw trace files.

## Item 5 — code fixes only where real `ascp` exposes gaps

Anticipated, to confirm/fix against real behaviour:
- Return-code semantics (`ascp` non-zero on partial), `-k1` resume correctness.
- `DirGrowthMeter` counting the `.aspx`/partial temp files `ascp` writes (it may use
  a different in-progress filename than our segmented `.part`).
- Speed cap `-l` units and whether EBI honours them.
Keep changes minimal and behind the existing seam; do not disturb non-aspera paths.

## Item 6 — tests + honesty update

- Keep all Part 5 fake-`ascp` unit tests (offline, never skip).
- Add an **opt-in live test** gated by `ADAPTISEQ_LIVE_ASPERA=1` (skips by default and
  when offline) that does the single-file real transfer + md5.
- Update HANDOFF limitation #2 and NOTES §P5.x from "real ENA Aspera was never run"
  to the measured reality, with the trajectory/throughput numbers.

## Build order

1. Plan (this file). 2. Fetch SDK + real `ascp` on PATH. 3. Key discovery + ENA
fallback + unit test. 4. Single-file real transfer + md5. 5. Adaptive vs fixed real
batch run + traces. 6. Any code fixes the real binary forces. 7. Live opt-in test.
8. Docs/HANDOFF/NOTES + full suite.
