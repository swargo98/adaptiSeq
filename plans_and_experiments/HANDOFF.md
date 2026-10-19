# Handoff (written 2026-10-19 for a fresh Claude Code session)

Read this, then `plans_and_experiments/remaining_tasks.md` (the running log: every
job, result row and decision, newest material near the top of each section).

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
  `plans_and_experiments/`. Compute nodes cannot see the login node's `/tmp`.
- Never edit files a running benchmark job reads in place: `bench/e3/*.sh`,
  `datasets/`, or the conda env it uses. To change `bench/e3/run_e3.sh` while jobs run,
  copy, edit the copy, and `mv` it over (new inode; running bash keeps the old file).
- Two conda envs: `adaptiseq_e3_sub` holds the 0.1.7 wheel the **sweep** uses (do not
  reinstall it until the sweep ends); `adaptiseq_e3_dev` holds the newest build (0.1.9
  now; the tournament uses it). Build a wheel with
  `ENV_NAME=adaptiseq_e3_dev sbatch --export=ALL bench/e3/setup_expanse.sbatch`
  (builds from the checkout's `__version__`, installs into that env, runs both test
  suites and the README examples). Only rebuild the dev env when no tournament job is
  running in it.
- Ask before: PyPI/Zenodo release or tags, merging `origin/app-notes` `6ae2fd3` (its
  ENA fix conflicts with ours), deleting anything, cancelling jobs the user did not ask
  about. A safety check blocked `rm -rf /home/rswargo/adaptiseq_oldtree_check`; the user
  may delete it.
- Other Claude sessions on this machine: `rswargo-85` (stopped doing E3 rows; idle) and
  `rswargo-ba` (did `--no-sra-fallback`; waits before editing `adaptiseq/`/`tests/`).
  Check `ListAgents` and message them before editing shared files.

## 2. What happened (short)

- 0.1.4 full benchmark: rep 1 hit an ENA portal outage; reps 2 and 3 done; rep 4 and the
  rest cancelled at the user's request (the paper should benchmark the fixed tool).
- Robustness work, each with tests (`README.md` "0.1.5" to "0.1.9" notes): in-pool md5
  check and re-fetch of corrupt transfers (corruption is ENA's/the path's: plain curl FTP
  got a full-length bad copy); refused connects held at the host's ceiling; finer splits
  for late files; segments split while a file downloads; a range probe with no answer
  retried instead of going single-stream; GSA links from the run-info table (the browse
  page now shows a JS browser check); GEO via NCBI E-utilities (the GEO page now shows a
  reCAPTCHA); GSA md5 list retried; progress-aware batch retries; lone files split.
- **iSeq 1.9.9 can no longer download from GSA (exits 0 with no data) or GEO**; the
  paper's Table 1 needs a dated note.
- 0.1.7 on panel 3b: fixed -j 20 288 to 379 s, default 378 to 529 s (0.1.4: 1515 to 10586).

## 3. Running and queued (as of writing)

| job | what | results | on finish |
|---|---|---|---|
| `55064912` | fixed-j sweep rep 2 (0.1.7, env `_sub`), panels 3jr, 3jb | `e3_jsweep_expanse/e3_55064912/` | record rows, move `slurm_e3_<id>.*` into the dir, commit the dir (exclude >20 MB raw logs) |
| `55064913` | sweep rep 3, `afterany:55064912` | `e3_jsweep_expanse/e3_55064913/` | same; check gate + wheel sha `2fa62d66` at start |
| tournament round 2 | see section 5; submit after the knee tests pass, chained `afterany:55064913` | `e3_round2_expanse/` | record rows, score |

Watch a job with `ROOT=<results root> MIN_NEW=<n> bash tools/watch_rows.sh <jobid>`
(run_in_background). Per-row routine: inspect the arm's log
(`sed 's/\x1b\[[0-9;]*m//g'`, grep for `MD5 mismatch|probe attempt|Single-conn|failed
after|ContentLengthError|adaptive worker summary`) and its `conc_*.tsv` (column 4 =
archive connections), add a row to the right table in `remaining_tasks.md` (python
`str.replace` on a unique anchor), commit, push.

## 4. Results so far

Sweep (0.1.7, all arms complete and md5-verified):

| -j | 3r rep 1 | 3r rep 2 | 3b rep 1 |
|---|---|---|---|
| 1 | 4197 | 10554 | 9708 |
| 2 | 3264 | 3104 | 3291 |
| 4 | 1250 | 2176 | 1627 |
| 8 | 505 | 639 | 731 |
| 16 | 440 | 723 | 469 |
| 32 | 163 | 593 | 859 |
| 64 | 235 | 298 | 428 |
| default (topdown) | 363 | 556 | 581 |

Tournament round 1 (0.1.9, frozen candidates, 3 reps, `e3_tournament_expanse/`,
`python bench/e3/score_tournament.py e3_tournament_expanse/e3_*/e3_results.tsv`):
NCBI (`.sra`, link-limited, all within 13 %) and GSA (3-4x noise between reps). Score
(median / best median; worst over panels): bottomup 1.045, greedy 1.351, fixed-j20 1.868,
topdown 1.885, budget 2.318. `budget` lost GSA partly to my mistake (its 0.1.9
"3 cut-short responses = distress" rule; GSA cuts streams at any load). ENA panels of
round 1 were never run: they are folded into round 2.

Source speeds (`diag_sources/out_55066512/`): NCBI AWS 32 MB/s per connection (link-
limited near 16 connections), GSA 9.5 on 1 / 30 on 8 (saturates), ENA about 2 per
connection.

## 5. The current task: a controller that wins most cases with few connections

User, 2026-10-19: "I want a controller that beat others in most of the cases for every
experiment. maintaining as low connection as possible."

- New controller `knee` (uncommitted when this was written; see `git status`):
  `adaptiseq/batch.py` `_run_knee`, `--controller knee`. Starts at 4 connections, doubles
  while each doubling earns half its proportional gain (3 s windows), tries the midpoint,
  settles on the smallest budget that paid, then holds and re-tests +-25 % every third
  8 s window; distress = 429/503/refused-with-nothing-open/dropped (not cut-short); no
  judging in the tail. With `-j` unset it may use a pool of 64 workers
  (`Options.jobs_explicit`, `KNEE_POOL`). `segmented._run_segments` now fills spare
  budget at once. Tests: `tests/test_controllers.py` (knee section). Suite job
  `55082561`; mixed dataset job `55082563` (`datasets/M1_mixed.*`).
- Next steps:
  1. If `55082561` passes: commit (bump `__version__` to 0.1.10, README "0.1.10" notes),
     push, build 0.1.10 in `adaptiseq_e3_dev`.
  2. Optional quick smoke of knee alone on 4s and 4g (non-ENA, can run beside the
     sweep): `E3_CONTROLLERS=knee E3_CTRL_FIXED= PANELS="4s 4g" REPS=1 ...`.
  3. Round 2, 3 reps, one job per rep, chained `afterany:55064913` (after the sweep),
     `ENV_NAME=adaptiseq_e3_dev E3_ASEQ_WHEEL=<0.1.10 wheel> E3_TIMEOUT_CTRL=7200
     RESULTS_ROOT=$PWD/e3_round2_expanse PANELS="4r 4b 4s 4g 4h 4m" E3_REP_FIRST=r REPS=1
     E3_CTRL_FIXED="20 64" sbatch --export=ALL --exclude=exp-10-14 bench/e3/e3_expanse.sbatch`.
     Arms: knee, topdown, bottomup, budget, greedy + fixed-j20, fixed-j64. About 5 h per rep.
     4h = held-out ENA panel (D3_seg, 2 x 11.5 GB), 4m = mixed ENA + GSA list.
  4. Score with the user's criterion (write it into `remaining_tasks.md` before the data):
     a case = (panel, rep); an arm wins a case if within 10 % of the fastest arm in it;
     rank by cases won, ties by lower mean archive connections (`conc_*.tsv` column 4);
     disqualify an arm more than 1.5x the fastest in any case, or with any run not
     md5-verified. Extend `bench/e3/score_tournament.py` for this.
  5. The winner becomes the default, then the paper's 5-rep chain (3r + 3b, all tools)
     runs on that build.
- Caveat to keep in the paper: knee was designed on the round-1 panels; round 2 uses
  fresh reps, a held-out panel and a mixed list.

## 6. Open items for the user (not yours to decide)

Decision A (completion claim wording), B (report md5-verified separately; recommended),
the Fabric half of the paper, co-authors/ORCIDs/funding, allocation number
(TG-CIS250262 vs CIS250262), PyPI release (PyPI has only 0.1.3; 0.1.4 to 0.1.9 are local
wheels), Zenodo, Bioconda (task written in `remaining_tasks.md`; needs PyPI first),
merging `origin/app-notes` `6ae2fd3`, the iSeq GSA/GEO note for Table 1, `-r ftp` stalls
at ENA (docs note or HTTPS fallback), optional block-by-block corruption diagnostic
(`diag_batch` with `METHODS=curl-ftp,curl-https,aseq-https ROUNDS=1`).
