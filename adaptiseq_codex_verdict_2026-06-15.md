# adaptiSeq Codex Verdict - 2026-06-15

## Bottom line

adaptiSeq is much closer to a releasable package than in the earlier audit. The
core package builds, the offline test suite passes, the source distribution now
contains the package tests and license, `python -m adaptiseq` works, and the new
real ENA Aspera validation is a major credibility upgrade.

My verdict is still **no package release today** and **not publication-ready yet**.
The remaining problems are no longer "is this project real?" problems. They are
release-quality problems: stale user-facing claims, one important claimed feature
that is not actually wired into the main path, dependency preflight edge cases,
missing CI/release checks, and insufficient benchmark breadth for an iSeq-level or
Bioinformatics Application Note submission.

## What improved since the earlier report

- Root package hygiene is substantially better: `LICENSE`, `MANIFEST.in`, richer
  `pyproject.toml` metadata, dynamic versioning, project URLs, classifiers, and
  `adaptiseq/__main__.py` are present.
- `README.md` is much stronger and now explains scope, supported accessions,
  usage, testing, known limits, and iSeq attribution.
- `tests/test_aspera_live.py` adds an opt-in live ENA Aspera test.
- `BENCHMARK.md` now includes real ENA Aspera evidence using actual IBM `ascp`,
  including a single-file md5 sanity test and a 32-file / 2.2 GB adaptive batch.
- `sysbench/` adds a useful system-level benchmark harness with adapters,
  per-phase sampling, plots, and tests.
- The package build succeeds and the sdist includes `LICENSE`, `README.md`,
  `pyproject.toml`, `adaptiseq/__main__.py`, and the test suite.
- Regenerable benchmark outputs under `sysbench/runs/` are ignored and are not in
  the sdist. `bench/` and `sysbench/` are excluded from the package artifact, which
  is reasonable for PyPI if the repo remains the benchmark source.

## Evidence from this re-check

- `ADAPTISEQ_NO_NETWORK=1 pytest`: **126 passed, 7 skipped**.
- `python3 -m pytest sysbench/tests`: **4 passed**.
- `python3 -m build --outdir /tmp/adaptiseq-dist2`: succeeded and produced
  `adaptiseq-0.1.0.tar.gz` and `adaptiseq-0.1.0-py3-none-any.whl`.
- `python3 -m adaptiseq --version`: reported `adaptiSeq 0.1.0`.
- `twine check` could not be run because `twine` is not installed in this
  environment.
- Build warning: setuptools now warns that `project.license` as a TOML table and
  license classifiers are deprecated. This is not fatal today, but it should be
  fixed before release.

## Package release blockers

1. **Main-path streaming overlap is still not implemented.** `batch.resolve_all`
   supports `on_task` and its docstring says resolved tasks can stream into the
   downloader, but `core._batch_download_phase` and `_aspera_download_phase` first
   wait for all resolution to finish and only then start download. Meanwhile
   `README.md` and `CHANGES_FROM_ISEQ.md` claim "streams resolved files into the
   download queue" and that downloading overlaps resolution. Either wire true
   producer/consumer streaming into the batch downloader, or remove the claim.

2. **CLI help is stale in user-visible ways.** `--protocol` help says the ENA
   default is FTP, while the code defaults to protocol `auto`. `--engine` help says
   segmented falls back to classic per-host, while `engine/seam.py` explicitly says
   auto transport never falls back to classic and degrades inside the segmented
   engine instead.

3. **Internal docs are stale and partially contradictory.** `HANDOFF.md` still
   says `adaptiSeq / adaptiFetch`, mentions an old `adaptiFetch` remote, and still
   lists real Aspera validation as a possible next step even though Part 6 did it.
   `PART6_PLAN.md` describes a DSA fallback plan that is not what happened.
   `iSeq.yml` still says numpy was not added even though it is present.
   `CHANGES_FROM_ISEQ.md` still contains outdated fallback and streaming claims.

4. **Dependency preflight has edge cases.** With `--skip-md5 -d sra`, preflight can
   avoid checking `srapath` even though SRA URL resolution/download can still need
   it. With `-g`, the code can fall back to SRA conversion paths, but preflight only
   checks `pigz` unless `-q` or merge is requested. These should be tightened before
   users hit confusing runtime failures.

5. **Packaging metadata needs one more cleanup pass.** Change the license metadata
   to the current SPDX-style form, add `license-files`, and remove/adjust deprecated
   license classifiers. Then run `python -m build` and `twine check dist/*` in a
   clean environment.

6. **There is no visible CI/release automation.** Before release, add GitHub
   Actions or equivalent for offline pytest, sysbench unit tests, build, twine
   metadata check, and a wheel install smoke test. Keep live network tests opt-in.

7. **Publication metadata is absent.** Add `CITATION.cff`, optionally `codemeta.json`,
   and set up Zenodo/GitHub release archiving if the goal is citation potential.

8. **GSA Aspera remains under-validated.** ENA Aspera is now credible. GSA/Huawei
   behavior should be tested or explicitly scoped as inherited/best-effort before
   release claims imply equal support.

9. **A fresh wheel install smoke test is still needed.** Build artifacts exist, but
   the release gate should include a clean venv install from the wheel and smoke
   commands for `adaptiseq --version`, `python -m adaptiseq --version`, metadata-only
   mode, local fixture resolution, and a skipped/no-network path.

## Package release verdict

Target next state: **release candidate**, not final release. The release candidate
is reasonable after fixing the stale claims/help, preflight edges, packaging
warnings, CI, citation files, and clean-wheel smoke tests. If true resolution-to-
download streaming is not implemented, the docs must stop claiming it.

## Publication readiness verdict

The current benchmark story is stronger, but still not enough for an iSeq-grade
paper or a Bioinformatics Application Note. The existing evidence shows promise:

- 35-run / 89 MB batch benchmark versus iSeq and Kingfisher.
- Real ENA Aspera single-file md5 validation.
- Real ENA Aspera 32-file / 2.2 GB adaptive run.
- System benchmark harness with phase-level CPU/RSS/disk/network sampling.

That is not yet a publication matrix. It is a good pilot.

For citation potential, the best target remains **Bioinformatics Applications
Note** if the final work can show a crisp, reproducible advantage over iSeq,
Kingfisher, SRA Toolkit, and related fetchers. If the contribution is mostly a
software engineering extension with modest novelty, a more software-focused venue
or preprint plus PyPI/GitHub/Zenodo release may be safer.

## Benchmarks still needed for a publication-worthy submission

Run all benchmarks with deleted outputs between runs, identical requested formats,
reported bytes, wall time, throughput, failures, retries, md5/validation status,
CPU, peak RSS, disk IO, network IO, tool versions, host region, date/time, and at
least 5 repeats where feasible. Report median, IQR, and full raw tables.

1. **iSeq parity matrix.** Cover the accession and mode surface iSeq supports:
   Run, Experiment, Sample, BioSample, Study/Project, GEO indirection, ENA, SRA,
   DDBJ where possible, GSA/CRA/CRR, metadata-only, direct `.fastq.gz`, SRA
   download, FASTQ conversion, md5/vdb validation, and merge by experiment/sample/
   study.

2. **Dedicated-tool comparison.** Compare against stock iSeq, iSeq parallel mode,
   Kingfisher, SRA Toolkit (`prefetch` / `fasterq-dump`), pysradb, ENA Browser
   Tools where relevant, and optionally aria2c/wget/curl only as raw-transfer
   baselines.

3. **Batch-overhead benchmark.** Repeat and expand the current 35-run / 89 MB
   workload. Include cold/warm order reversal, randomized tool order, and at least
   5 repeats.

4. **Medium transfer benchmark.** Use the prepared medium list or equivalent
   multi-run project, aiming for tens of GB total. This tests whether the batch
   advantage survives once bytes dominate metadata overhead.

5. **Large transfer benchmark.** Use the prepared large list or equivalent fewer,
   larger runs. This tests segmented transfer, resume, disk pressure, and sustained
   throughput.

6. **Single-file microbenchmark.** Keep the aria2c/wget/curl comparison, but frame
   it as raw transport only. Include range-supported and range-limited endpoints.

7. **Adaptive concurrency sweep.** Compare `--adaptive` against fixed `-j 1,2,4,8,
   16,20` across small, medium, and large workloads. Also sweep `--meta-jobs`.

8. **Real ENA Aspera sweep.** Run fixed `-j 1,2,4,8` versus adaptive on real ENA
   Aspera. The current 2-worker collapse is an excellent story, but it needs repeats
   and fixed-concurrency baselines.

9. **Real GSA Aspera validation.** If GSA support is claimed, run CRR/CRA workloads
   over the real GSA/Huawei path, including md5 validation and failure behavior.

10. **Robustness and correctness cases.** Include multi-part FASTQ runs where iSeq
    fails, orphan/barcode files, missing md5, broken range support, transient HTTP/
    FTP failures, interrupted downloads with resume, and duplicate/already-successful
    files.

11. **Resource profiling.** Use `sysbench` for phase-level request/metadata/data/
    md5 breakdowns across every major tool and workload. Include plots, but publish
    raw CSV/JSON too.

12. **Environment diversity.** Run from at least two network locations, ideally a
    US cloud host and an EU host close to ENA. Add a China/Asia path if GSA/Huawei
    performance is part of the claim.

13. **Installability/reproducibility benchmark.** Time and document install steps
    for pip/conda dependencies, external tools (`ascp`, SRA Toolkit, pigz, axel),
    and failure modes. This matters for adoption and citations.

14. **Ablation study.** Quantify the individual contribution of parallel metadata
    resolution, segmented transport, adaptive batch scheduling, adaptive Aspera,
    and md5/validation handling.

15. **End-to-end biological-user workflow.** Pick one real public project and show
    "from accession list to verified FASTQ plus metadata/logs" with exact commands,
    outputs, and restart behavior.

## Final verdict

adaptiSeq now looks like a credible iSeq successor in active development, not just
a renamed fork. The strongest new evidence is the real ENA Aspera validation and
the sysbench harness. The biggest risk is overclaiming: the docs currently promise
streamed resolution/download overlap and fallback behavior that the main code path
does not provide.

Fix those mismatches first. Then cut a release candidate, run the expanded
benchmark matrix, and only then aim for Bioinformatics Applications Note or a
similar high-visibility software venue.
