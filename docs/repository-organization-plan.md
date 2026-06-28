# Repository Organization Plan

This plan is documentation only. Do not execute any file moves from this plan
without explicit approval for the specific phase. The previous organization
attempt showed that broad moves create too much churn and can obscure active
testing work, so this plan favors small, reversible phases and compatibility
paths.

## Current Layout

- `adaptiseq/`: shipped Python package and CLI implementation.
- `tests/`: package pytest suite.
- `sysbench/`: importable standalone benchmark harness; keep top-level unless
  all `python -m sysbench...` commands and CI are updated together.
- `bench/`: benchmark scripts, accession input lists, and checked-in benchmark
  result summaries.
- `docs/`: user documentation; `docs/testing/` already holds feature test cases,
  Markdown/CSV/XLSX test reports.
- Root docs: `HANDOFF.md`, `NOTES.md`, `CHANGES_FROM_ISEQ.md`, `PART*_PLAN.md`,
  `adaptiSeq_part*.md`, `BENCHMARK.md`, and codex reports.
- Root project files: `README.md`, `pyproject.toml`, `MANIFEST.in`, `iSeq.yml`,
  `LICENSE`, `CITATION.cff`, `.github/`, `AGENTS.md`.
- `tmp/feature-tests/`: generated local test artifacts; should stay ignored.

## Guiding Rules

1. Move one category at a time.
2. Keep compatibility wrappers or aliases for one transition phase when commands
   are user-facing.
3. Update references in docs, tests, scripts, and CI in the same phase as a move.
4. Do not move package, CI, or importable module roots without targeted tests.
5. Keep generated test/download outputs out of source-controlled directories.

## Proposed Target Layout

```text
.
├── adaptiseq/
├── tests/
├── sysbench/
├── bench/
│   ├── inputs/
│   ├── results/
│   └── scripts/
├── docs/
│   ├── usage/
│   ├── testing/
│   ├── development/
│   ├── plans/
│   ├── reports/
│   └── img/
├── env/
│   └── conda/
└── tmp/
```

This is a possible end state, not a command sequence.

## Phase 1: Documentation Only Cleanup

Goal: reduce root doc clutter without changing runtime behavior.

Candidate moves:

| Current Path | Candidate Path |
| --- | --- |
| `HANDOFF.md`, `NOTES.md`, `CHANGES_FROM_ISEQ.md` | `docs/development/` |
| `PART4_PLAN.md` ... `PART7_PLAN.md` | `docs/plans/` |
| `adaptiSeq_part1_python_port.md` ... `adaptiSeq_part3_adaptive_and_batch.md` | `docs/plans/` |
| `adaptiseq_codex_report.md`, `adaptiseq_codex_verdict_2026-06-15.md` | `docs/reports/` |
| `BENCHMARK.md` | `docs/reports/BENCHMARK.md` |
| `COLAB_TESTING.md` | `docs/testing/colab.md` |

Approval decision before execution: move all root docs in one phase, or move
only historical reports/plans and keep active docs such as `HANDOFF.md`,
`NOTES.md`, and `BENCHMARK.md` at root.

Required reference updates:

- `README.md`
- `docs/README.md`
- `docs/usage/*.md`
- `HANDOFF.md`, `NOTES.md`, plan docs
- code comments that reference `NOTES.md` or `BENCHMARK.md`
- tests/docstrings that reference moved docs

Validation:

```bash
grep -RIn "old/path-or-name" README.md docs adaptiseq tests sysbench bench
python -m pytest tests/test_cli.py tests/test_routing.py tests/test_accession.py -q
```

## Phase 2: Benchmark Directory Cleanup

Goal: organize `bench/` without breaking existing commands.

Preferred conservative option:

```text
bench/
├── inputs/
├── results/
└── scripts/
```

Candidate moves:

| Current Path | Candidate Path |
| --- | --- |
| `bench/benchmark.py`, `bench/benchmark_batch.sh` | `bench/scripts/` |
| `bench/_run_all.sh`, `bench/_run_one.py` | `bench/scripts/` |
| `bench/setup_real_ascp.sh`, `bench/setup_edgeturbo.sh` | `bench/scripts/setup/` |
| `bench/results_batch.tsv` | `bench/results/results_batch.tsv` |
| `bench/subset_small.txt` | `bench/inputs/subset_small.txt` |

Compatibility requirement: keep root-level wrapper scripts in `bench/` for at
least one transition phase, for example `bench/benchmark_batch.sh` should still
work and call `bench/scripts/benchmark_batch.sh`.

Do not introduce a new top-level `benchmarks/` directory unless explicitly
approved; the prior attempt showed that it produced too much path churn.

Validation:

```bash
bash -n bench/*.sh bench/scripts/*.sh
python -m py_compile bench/*.py bench/scripts/*.py
python bench/benchmark.py --help
```

## Phase 3: Environment Files

Goal: make environment definitions clearer.

Candidate target:

```text
env/conda/adaptiseq.yml
```

Compatibility requirement: keep root `iSeq.yml` as the canonical file unless the
team explicitly accepts either a wrapper/symlink or duplicated copy. If both
files exist, document how they are kept in sync.

Required updates:

- `README.md`
- `docs/installation.md`
- `AGENTS.md`
- any setup/test instructions mentioning `iSeq.yml`

Validation:

```bash
conda env create -f iSeq.yml --dry-run
```

Run this only in an environment where Conda dry-run is available.

## Phase 4: Generated Artifacts and Test Outputs

Goal: keep large downloads and local test artifacts out of tracked source paths.

Rules:

- Keep `tmp/feature-tests/` ignored.
- Keep large FASTQ files only under `tmp/feature-tests/<case-id>/`.
- Do not commit `*.fastq`, `*.fastq.gz`, nested test rerun directories, or
  generated `__pycache__/`.
- Preserve `docs/testing/test-results.*` as the source of test evidence.

Potential cleanup command after explicit approval:

```bash
find tmp/feature-tests -maxdepth 5 -type d -path "*/tmp/feature-tests/*" -print
```

Do not delete generated artifacts until the test report has recorded any needed
evidence.

## Phase 5: Optional Test Layout

Recommendation: do not move `tests/`. Keeping it at the root matches pytest,
packaging, and contributor expectations.

Moving `tests/` would require updates to:

- `pyproject.toml`
- `MANIFEST.in`
- `.github/workflows/ci.yml`
- docs and contributor instructions

## Approval Gates

Before executing any phase, answer these questions:

1. Should compatibility wrappers be real files, symlinks, or omitted?
2. Should active root docs stay at root while only historical material moves?
3. Should `iSeq.yml` remain canonical?
4. Should `bench/` be reorganized internally, or left as-is for reproducibility?
5. What validation suite must pass before the phase is considered complete?

## Recommended First Step

Start with Phase 1 only, and choose the minimal variant: move historical reports
and old implementation plans, but keep `HANDOFF.md`, `NOTES.md`, `BENCHMARK.md`,
and `iSeq.yml` at the root. This gives most of the cleanup benefit with the
least disruption to active testing and user commands.
