# Remaining tasks after executing MINIMAL_SUBMISSION_PLAN.md

Written 2026-10-13 on branch `app-notes`. Nothing has been committed, pushed,
tagged, or published; every change is in the working tree for you to review.

The plan has four steps. Steps 1 and 3 are done as far as they can be without
your accounts or the two benchmark machines. Step 2 is prepared and smoke-tested
but not run. Step 4 is drafted with placeholders where results go.

Three things I found along the way change what the paper can claim. They are in
"Decisions needed before the benchmark" and should be read first.

---

## Decisions needed before the benchmark

### A. adaptiSeq did not complete all 241 runs in most earlier repetitions

The plan's one-sentence claim is that adaptiSeq downloads lists "completely". In
the existing 3r data (0.1.3), adaptiSeq arms finished 241/241 in 17 of 42
repetitions and 240/241 (once 239) in the rest, exiting with status 1. The logs
show an md5 mismatch on a single run that survived all three retries, a
different run each time (`SRR22904341_2.fastq.gz`, `SRR22904401.fastq.gz`).
fastq-dl also finished 240/241 in five of its six repetitions, which suggests
the cause was what ENA served at that moment, not adaptiSeq. Both runs download and verify correctly
today (`manual_md5_check.py --runs SRR22904401 SRR22904341` passes).

Why this is yours: I cannot tell from the logs whether this was a transient
mirror problem or a retry weakness in adaptiSeq, and the answer decides the
headline wording. If the rerun again shows 240/241, the claim has to be
"completes the runs other tools drop" with the one failure explained, not
"completely". The manuscript draft has a placeholder sentence for this. One
thing I did not establish and that is worth checking: the first retry in
`check_sra` calls the download again without deleting the file. If the engine
leaves an existing file alone, only one of the three attempts is a fresh
download.

### B. Kingfisher's fallback methods cannot be credited by the md5 verifier

The plan's Kingfisher arm is `-m ena-ftp aws-http prefetch`. When `ena-ftp`
fails for a run, Kingfisher fetches the `.sra` and recompresses FASTQ locally.
That file can be correct but is never byte-identical to ENA's, so
`verify_output.py` scores the run as not completed and excludes its bytes from
MB/s. In the old data Kingfisher's `ena-ftp` left 93 or 153 of the 241 runs
unfinished in five of six repetitions, so with the fallback chain many runs may
land in this category, and
the comparison would understate Kingfisher. A reviewer could object.

What I did: added a diagnostic column, `runs_present_unverified` (runs with a
payload file on disk that did not match the manifest). It is never counted as
success; it tells you how large the problem is after the gate run.

Why this is yours: the fix is a scoring rule, which is a scientific choice.
Options: (1) keep md5-against-ENA as the only criterion and state plainly in the
paper that fallback output is uncounted and how many runs that was; (2) add a
second criterion for such runs (`gzip -t` plus read count equal to ENA's
`read_count`) and report them as a separate category; (3) run Kingfisher with
`ena-ftp` only, as before, and say so. I would do (1) plus the count, and (2)
only if the count is large.

### C. The gate has not been run on the benchmark machines

The plan's gate ("one rep of both panels, then check") needs about 2.7 hours and
34 GB on the benchmark machines. I ran the equivalent on the 3-run smoke dataset
on this laptop instead. See Step 2 below for what that did and did not cover.

---

## Step 1: software

| # | Task | State |
|---|---|---|
| 1 | Licence and credit | Done |
| 2 | README and `CITATION.cff` | Done except author metadata |
| 3 | Exit code 1 on SRA-only runs | Fixed and verified |
| 4 | Release 0.1.4, tag, Zenodo | Prepared; not released |

Done:

- `LICENSE` now reproduces iSeq's MIT notice (`Copyright (c) 2024 BioOmics`, text
  taken from the iSeq repository) and names FastBioDL as the source of the
  transfer engine. README, `docs/README.md`, and `CITATION.cff` say adaptiSeq
  builds on iSeq and ask users to cite iSeq and FastBioDL.
  `adaptiseq/engine/segmented.py` credits FastBioDL in its header.
- README: removed "not yet on PyPI" and the stale badge comment; same in
  `docs/installation.md`.
- Task 3, root cause: with `-g`, a run with no ENA FASTQ mirror is downloaded as
  `.sra`, but `check_sra` then looked for FASTQ md5s, found none, re-downloaded
  twice, wrote the run to `fail.log`, and set exit 1, after which the `.sra` was
  converted correctly. It now validates the `.sra` with `vdb-validate`. Changes:
  `adaptiseq/integrity.py`, `adaptiseq/core.py`, three tests in
  `tests/test_logs_integrity.py`.
  Verified live: released 0.1.3 on `SRR1031060` gives exit 1 and a `fail.log`
  entry; the fixed code gives exit 0, `success.log`, and identical FASTQ, on both
  `SRR1031060` and `SRR1031066`. Test suite: all pass offline and with network.
  This departs from iSeq, which still exits 1 here.
- Version set to 0.1.4 (`adaptiseq/__init__.py`, `CITATION.cff`, README update
  notes). sdist and wheel build, pass `twine check`, and the wheel runs the
  README's CLI and Python examples in a clean virtual environment.

Remaining:

1. **Author metadata in `CITATION.cff`.** I entered "Swargo, Rasman Mubtasim" from
   the FastBioDL author list and your GitHub handle. Please confirm it, and add
   co-authors, ORCIDs, and affiliations. I do not have them. The same applies to
   `authors` in `pyproject.toml`, which still says `swargo98`.
2. **FastBioDL's licence.** I credited it by citation. If FastBioDL is published
   under a licence that requires its notice to be reproduced, add that notice to
   `LICENSE` next to iSeq's. I could not find its repository to check.
3. **Release (plan task 4).** Needs your PyPI token, push rights, and your
   Zenodo login, and publishing is not reversible, so I did not attempt it.
   Order matters, because Zenodo only archives releases created after the
   repository is switched on:
   1. Review and commit the working tree; merge to `main`.
   2. In Zenodo, enable the GitHub integration for `swargo98/adaptiSeq`.
   3. `python -m build && twine check dist/* && twine upload dist/*`
   4. Tag `v0.1.4`, push the tag, and create a GitHub release from it.
   5. Put the DOI and release date into `CITATION.cff` (two commented lines are
      ready), the README, and the manuscript.
4. **README comparison table.** `paper/table1_features.md` lists three cells that
   disagree with the tools' current versions (Kingfisher has a Python API and
   experimental GSA support; pysradb downloads in parallel). The iSeq and
   Kingfisher authors may review this paper, so the table should be corrected in
   the same release. I left it because how you define the columns is your call.

---

## Step 2: benchmark rerun

Done, in `plans_and_experiments/bench/e3/`:

- `run_e3.sh`: arm order is now a real seeded permutation per repetition, logged
  to `logs/arm_order.tsv`. (Confirmed the old problem: in the existing Expanse 3r
  rows, positions 3, 4, 5, 7, and 10 hold the same arm in every repetition.) The default arm
  set is the plan's six arms; the eleven original arms remain under
  `ARM_SET=legacy`. Panel 3r now defaults to 5 repetitions.
- Every row records `aseq_version` and `aseq_sha256`. `aseq_fingerprint.py`
  checks that the installed package is byte-identical to the wheel named in
  `E3_ASEQ_WHEEL` and reports that wheel's sha256. Panels 3r and 3b refuse to
  start without it.
- `verify_output.py` and the TSV gain `runs_complete_3file`,
  `runs_expected_3file` (needed for Figure 1c), and `runs_present_unverified`.
  The harness refuses to append to a TSV with the old header.
- `manual_md5_check.py`: the gate's by-hand check. Downloads three runs with
  curl, compares md5 with ENA and the manifest, and requires `verify_output.py`
  to agree. Passes today on `D1_full`.
- `check_run.py`: after a run, confirms every arm, panel, and repetition has one
  row, one adaptiSeq build throughout, and a varying arm order.
- `e3_expanse.sbatch` (defaults to 3r + 3b, 5 reps, runs the md5 gate first),
  `run_submission.sh` (the same for Fabric, without Slurm: `gate` or `full`),
  `setup_env.sh` (installs the release wheel instead of an editable checkout).
- Kingfisher flags checked against `kingfisher get --full-help` (0.5.0): all
  five are valid.

Smoke-tested here: two repetitions of the six arms on `SMOKE_D1`. adaptiSeq
(both arms) and fastq-dl verified 3/3 runs; rows, columns, order log, and
version file were written correctly.

Not covered by that test, because this is a macOS laptop:

- iSeq could not be installed (its `axel` dependency has no macOS arm64 build),
  so both iSeq arms exited 127. Their commands are unchanged from the earlier
  campaign.
- `aria2c` was missing, so Kingfisher fell through to `prefetch` on every run.
  That is how I noticed issue B; it is not what will happen on the benchmark
  machines.
- The Slurm path (`e3_expanse.sbatch`) was syntax-checked only.

Remaining:

1. **Run the gate, then the full benchmark, on Expanse and Fabric.** I have no
   access to either machine, and the run needs about 14 hours per machine. After
   0.1.4 is on PyPI, from `plans_and_experiments/` on each machine:
   ```bash
   bash bench/e3/setup_env.sh                      # prints: export E3_ASEQ_WHEEL=...
   export E3_ASEQ_WHEEL=...                        # the same wheel file on both machines
   # Expanse
   REPS=1 sbatch --export=ALL bench/e3/e3_expanse.sbatch     # gate
   sbatch --export=ALL bench/e3/e3_expanse.sbatch            # full
   # Fabric
   bash bench/e3/run_submission.sh gate
   nohup bash bench/e3/run_submission.sh full > run_submission.log 2>&1 &
   ```
   After the gate, read `check_run.txt` and `manual_md5_check.txt`, and look at
   `runs_present_unverified` for Kingfisher (issue B) before starting the full
   run. Compare the wheel sha256 in `versions_e3.txt` between machines.
2. **`setup_env.sh` reinstalls adaptiSeq into an existing `adaptiseq_e3`
   environment** with `--force-reinstall --no-deps`. That is intended, but the
   competitors in that environment are whatever was installed in July (iSeq
   1.9.8; Bioconda now has 1.9.9). Decide whether to keep the July versions or
   rebuild the environment, and use the same choice on both machines.
3. **Paths.** The harness expects to be run from the directory containing
   `bench/` and `datasets/`, which is now `plans_and_experiments/`. The old
   `submit_e3.sh` and `status.sh` are untouched and still assume the six-panel
   layout.

---

## Step 3: analysis

Done: `bench/e3/analyze_submission.py` reads one TSV per machine and writes
`summary.tsv` (median, IQR), `ratios.tsv` (per-repetition ratio against
`adaptiseq-default`, median, bootstrap 95% CI), `completion.tsv` (3r, split into
1/2-file and 3-file runs), `numbers.json`, and `fig1.pdf` / `fig1.png` with the
three panels and both machines. It refuses TSVs from the old harness and TSVs
that mix adaptiSeq builds. `paper/table1_features.md` is Table 1 with a source
for every cell. `paper/supplement.md` assembles E7b/c/d, E10c, E8, and the old
E3 adaptive arms, each under its caveat.

I tested the script and the figure layout on a stand-in built from the old TSVs.
Those outputs were discarded and none of their numbers are in the paper files.

Remaining:

1. **Produce the real numbers and figure**, once Step 2 has run:
   ```bash
   python bench/e3/analyze_submission.py \
       --tsv Expanse=<expanse run dir>/e3_results.tsv \
       --tsv Fabric=<fabric run dir>/e3_results.tsv --outdir paper/numbers
   ```
2. **Three cells in Table 1 are marked `?`** (Kingfisher partial-file resume,
   fetchngs rate limiting, pysradb md5 on download). I could not confirm them
   from `--help` or a quick read of the source.
   fetchngs was not installed or run; its row comes from its documentation.
3. **With five repetitions the bootstrap interval is coarse**: it can only fall
   on observed ratios, so it will often equal the minimum and maximum. The
   Limitations section says so. If a reviewer is likely to press on this, more
   repetitions are the only real remedy.

---

## Step 4: manuscript

Done: `paper/manuscript_draft.md` (abstract, introduction, implementation,
results, limitations, availability, figure legend; about 1,300 words of main
text) and `paper/cover_letter.md`. The implementation section was checked
against the code (rate limits, segment sizing, host backoff, transport
selection, the Python example).

Remaining:

1. **Fill the result placeholders** (`[[...]]`) from `paper/numbers/`. The table
   at the end of the draft maps each one to a file and field.
2. **References.** Four entries are marked "(verify)": I wrote the Kingfisher,
   fastq-dl, pysradb, and nf-core citations from memory. The archive references
   (SRA, ENA, DDBJ, GSA) still need adding.
3. **Things only you know:** co-authors and affiliations, funding, the
   acknowledgement wording that ACCESS/Expanse and FABRIC require, the
   corresponding author, and the description of the two machines (I wrote "128-core
   Expanse node" and "8-core FABRIC virtual machine" from the result files).
4. **Two factual statements in the Introduction** should be checked against a
   source: that the archives hold "tens of millions" of runs, and that fetchngs
   is the only listed tool with parallelism across runs (pysradb's `--threads`
   may also qualify; see Table 1).
5. **Convert to the journal's format** (OUP template, 4 pages) once the numbers
   are in. The draft is Markdown.

---

## Checklist from the plan

- [x] iSeq and FastBioDL credited in `LICENSE` and README. In the paper: drafted.
- [ ] `pip install adaptiseq==0.1.4` in a fresh environment runs the README
      example. Verified with the locally built wheel; repeat from PyPI after
      release.
- [ ] Every number in the text comes from the new TSVs via the script. The
      script and placeholders are in place; the TSVs do not exist yet.
- [ ] Zenodo DOI resolves. Needs the release.
- [ ] Accession lists and md5 manifests are public. They are in
      `plans_and_experiments/datasets/` on this branch and on `e8`; nothing has
      been pushed. Decide between the `e8` branch and a small separate
      repository, then put the URL and commit into the manuscript.

## Housekeeping

- `.DS_Store` files are untracked at the repository root and in
  `plans_and_experiments/`. They were there before I started; `.gitignore` does
  not exclude them.
- To reproduce the SRA-only check or the smoke run locally you need `wget`,
  `sra-tools`, and `pigz` on `PATH`; this machine has none of them outside a
  temporary environment I created in the session scratch directory.
