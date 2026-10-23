# Handoff (updated 09:45 PDT 2026-10-23 for a fresh Claude Code session)

Read this, then `plans_and_experiments/remaining_tasks.md` (open items only, short), and
`plans_and_experiments/progress_log.md` section 1 (the current work). `progress_log.md` is the
record of everything done: every job, result row and decision, in dated sections, newest first.

## 1. Setup and standing rules

- Repo `/home/rswargo/adaptiSeq`, branch `app-notes`. **Push only** with
  `git push expanse app-notes:expanse-app-notes` (remote `expanse` =
  `git@github-adaptiseq:swargo98/adaptiSeq.git`). Never push to `origin/app-notes`; never
  push `backup/app-notes-before-log-rewrite` (it holds a 1.46 GB log).
- Commit every committable update, then push. Git identity is set repo-locally
  (swargo98 / rmswargo98@gmail.com). End commit messages with the attribution lines
  the harness gives you.
- Never commit files over 100 MB; for logs over 20 MB commit a `gzip -9 -k` copy and
  leave the raw file untracked (`find -size +20M` before adding; add paths explicitly).
- **Expanse**: builds, installs, tests and benchmarks run through Slurm on compute
  nodes, account `umr115` (memory `expanse-use-compute-nodes.md`). Tests:
  `PYTEST_ARGS=tests sbatch --export=ALL bench/e3/pytest_expanse.sbatch` from
  `plans_and_experiments/` (add `OFFLINE_ONLY=1` for the offline suite only). The login
  node's `python3` is 3.6 and cannot import the package; compute nodes cannot see its `/tmp`.
- Submit benchmark jobs with `--exclude=exp-10-14,exp-3-51` (both failed DNS for the
  archives at the egress check).
- Never edit files a running benchmark job reads in place: `bench/e3/*.sh`,
  `datasets/`, or the conda env it uses. To change `bench/e3/run_e3.sh` while jobs run,
  copy, edit the copy, and `mv` it over (new inode; running bash keeps the old file).
- Conda envs: **`adaptiseq_e3_sub` holds 0.1.12 (wheel `0c5e6a82`)**, used by round 3 and
  next by the paper's 5-rep chain: do not rebuild it until both are finished.
  `adaptiseq_e3_dev` holds 0.1.11 and is free. Build with
  `ENV_NAME=<env> sbatch --export=ALL bench/e3/setup_expanse.sbatch` (builds from the
  checkout's `__version__`, installs, runs both suites and the README examples).
- For a diagnostic run with INFO-level logs (ceiling refusals, splits, controller steps),
  pass `ASEQ_CLI=$PWD/bench/e3/aseq_info.sh` to `bench/e3/e3_expanse.sbatch`.
- Ask before: PyPI/Zenodo release or tags, merging `origin/app-notes` `6ae2fd3` (its
  ENA fix conflicts with ours), deleting anything, cancelling jobs the user did not ask
  about. Making a different controller the default is the user's decision.
- Other Claude sessions on this machine: `rswargo-85` and `rswargo-ba` (idle; message them
  before editing `adaptiseq/` or `tests/`). `rswargo-99` (tmux pane %2) is a second process
  of this same conversation; it was asked to stand down on 10-20 and agreed. Check
  `ListAgents` before starting work, and do not let two sessions record the same rows.

## 2. Current state (09:45 PDT 2026-10-23)

| job | what | results | on finish |
|---|---|---|---|
| `55203207` | round 3 rep 1 on 0.1.12: **done** 01:06 10-23, all 42 arm-cases verified | `e3_round3_expanse/e3_55203207/` (committed) | recorded |
| `55203208` | round 3 rep 2: **running** since 03:23 on `exp-13-11`; 4r and 4b recorded | `e3_round3_expanse/e3_55203208/` | record 4s, 4g, 4h, 4m; move `slurm_e3_55203208.*` into the dir and commit it |
| `55203209` | round 3 rep 3: queued `afterany` | `e3_round3_expanse/e3_55203209/` | same, then score round 3 |

A round 3 rep takes about 11 to 14 h. Then (user's instruction, 10-22): if topdown ranks first
by `bench/e3/score_round2.py`, run the paper's 5-rep chain on 0.1.12 with topdown as the
default; otherwise stop and report. The commands are in `remaining_tasks.md` section 1.

**Per-panel routine.** Watch with `ROOT=e3_round3_expanse MIN_NEW=14 bash tools/watch_rows.sh <jobid>`
(run in the background with an absolute path to the script; it returns on the gate line, on
n new rows or at job end, and appends an ENA portal probe to `ena_portal_status_20261015.tsv`).
For each panel: `bash tools/check_panel.sh e3_round3_expanse/e3_<id> <panel>` prints every arm's
time, runs, connections (mean/max), md5 mismatches, cut-short responses, refusals, SRA fallbacks
and controller summary. Add the rows (ratio = wall / fastest in the case) to the rep's table in
`progress_log.md` section 1 with a python `str.replace` on a unique anchor, commit, push. Record
one or two panels per commit (MIN_NEW=14 = two panels of 7 arms). When a rep's job ends, move
its `slurm_e3_<id>.*` into its result dir and commit the dir.

## 3. Results so far (details in `progress_log.md`)

- **Fixed-j sweep (0.1.7, 3 reps, section 5):** best fixed -j was 32 on many small ENA files
  (271 s median) and 64 on large ones (428 s); topdown at 1.4x to 1.6x of the best.
- **Round 2 (0.1.11, section 2):** no arm qualified (every arm had a panel median above 1.5x);
  topdown had the most wins (8/18). Topdown's 10 losses: 5 its own search (stepped down on a
  stale reading; GSA tails on one connection), 2 the connection cap pinned at the first ENA
  refusal, 3 the source (ENA slow window, md5 re-fetches). Routing panels to controllers did
  not help out of sample (leave-one-rep-out geomean 1.60 vs 1.53 for always-topdown).
- **0.1.12 fixes (section 1, README "0.1.12"):** GSA run missing from the run-info table now
  fails; a lowered host cap recovers 1 per 5 s; spare connections while a controller holds files
  back; topdown measures a count only once the pool has reached it; ENA metadata retries bounded
  by 3 min shared across a list; a segment out of attempts that made progress continues in the
  same pass. Info-level diagnostics confirmed ENA really refuses beyond about 25 connections at
  times, and that the old pin drove GSA tails to one connection.
- **Round 3 so far:** rep 1: topdown the only arm within 1.5x on every panel (worst 1.42x).
  Rep 2: topdown fastest on 4r (626 s); 4b won by greedy (1229 s), topdown 1.31x.

## 4. What is open

See `remaining_tasks.md`: section 1 (round 3, the 5-rep chain, analysis, filling the manuscript
numbers; mine), section 2 (engineering follow-ups), section 3 (the user's decisions and actions:
decisions A and B, the Fabric half, release, Bioconda, publishing the datasets, the merge,
authorship, allocation number, iSeq wording), section 4 (the plan's checklist).
