# Part 4 plan — batch-USP benchmark + segmented+adaptive as the true default

Self-directed follow-up (no separate spec). Three goals from the user:

1. **adaptiFetch's USP is batch download** — benchmark on the uploaded accession
   lists, which are real multi-run projects.
2. **The competitors are dedicated SRA fetchers (iseq, Kingfisher), not aria2c** —
   the speedup is from *parallel URL resolution + batch concurrent download*,
   which sequential tools lack. Benchmark against the real tools; **delete the
   downloaded files between runs**.
3. **Default = segmented + adaptive.** If segmentation isn't possible, fall back to
   *adaptive single-connection* (still the multi-worker async pool), **never auto
   to classic**. `wget`/`axel`/`aspera` (classic) remain available but only when
   the user selects `--engine classic` explicitly.

## Workload sizing (measured live)

| List | Project | Runs | Total | Per-file |
|------|---------|------|-------|----------|
| small | PRJNA916347 | 243 | 7.6 GB | many tiny (median ~0 MB, max 404 MB) |
| medium | PRJNA353374 | 12 | 55 GB | ~3.6–5.2 GB each |
| large | PRJNA251383 | 4 | 49 GB | ~12 GB each |

The **small** list (many files) is the USP case: sequential tools pay per-run
overhead (resolve + connect) × 243, which adaptiFetch parallelizes. medium/large
are too big to download repeatedly for a fair multi-method benchmark in this
sandbox, so the headline benchmark uses a **byte-bounded subset of the small
list** (many files, modest bytes) and we document the size cap. Files are removed
between every method.

## Work items

1. **Default-fallback change (`engine/seam.py`).** Auto transport order becomes
   segmented-HTTPS → segmented-FTP → HTTP-single → FTP-single, with **no classic
   verdict**. The universal last resort is single-stream within the async engine
   (so it stays in the adaptive batch pool, multi-worker, single-connection per
   file). `get_engine` already returns `ClassicEngine` only for `--engine classic`,
   so classic is manual-only once the auto-classic verdict is removed.
   - Reason for the user's "not a single worker": segmentation failing must not
     collapse concurrency across files — the pool stays adaptive/parallel; only
     the per-file transport degrades to one connection.

2. **Competitor install (benchmark only).** `axel` (apt) + a no-op `ascp` stub on
   PATH (iseq's startup `CheckSoftware` gates on `ascp`/sra-tools even on the
   wget/axel ENA path; the stub lets *stock* iseq run its real ENA pipeline) +
   `sra-toolkit` (apt) for `srapath`/`vdb-validate`. `kingfisher` via pip, run with
   `-m ena-ftp` (aria2c/curl, no sra-tools needed for the download).

3. **Benchmark harness (`bench/benchmark_batch.py`).** Time, on the same subset,
   files deleted between each: stock `iseq`, `iseq -p 8`, `kingfisher -m ena-ftp`,
   `adaptiseq --no-adaptive`, `adaptiseq --adaptive`. Record wall time, throughput,
   and the adaptive worker trajectory. Write results + caveats to `BENCHMARK.md`.

4. **Tests + docs.** Tests asserting auto transport never yields `classic` and that
   the default engine/scheduler is segmented+adaptive. Update README/CHANGES/NOTES.

Stop-on-budget: commit at each step so progress is durable.
