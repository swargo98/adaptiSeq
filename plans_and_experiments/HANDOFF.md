# Handoff (updated 01:00 PDT 2026-10-20 for a fresh Claude Code session)

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
  reinstall it until the sweep ends); `adaptiseq_e3_dev` holds the newest build
  (0.1.11 `1b9ce128`; the knee smoke and round 2 use it: do not rebuild it until round 2 ends). Build a wheel with
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

## 3. Running and queued (as of 18:50 PDT 2026-10-19)

| job | what | env / wheel | results | on finish |
|---|---|---|---|---|
| `55064913` | fixed-j sweep **rep 3** (last): **done** 03:48 10-20; summary in `remaining_tasks.md` | `adaptiseq_e3_sub`, 0.1.7 | `e3_jsweep_expanse/e3_55064913/` | done (the sweep env may now be rebuilt) |
| `55090015` | knee smoke on 0.1.10 (done): 4s 8/8 94 s at 16 connections; 4g 6/6 1408 s, fell to 2-5 connections because GSA connect timeouts counted as pushback. Fixed in 0.1.11 (`011a314`); old round 2 `55090016`-`18` cancelled before starting | `adaptiseq_e3_dev`, 0.1.10 | `e3_knee_smoke/e3_55090015/` | done |
| `55096326` | **knee smoke on 0.1.11**: knee alone on 4s and 4g, beside the sweep | `adaptiseq_e3_dev`, 0.1.11 `1b9ce128` | `e3_knee_smoke/e3_55096326/` | **done, passed**: 4s 8/8 87 s at 16; 4g 6/6 331 s, budget 64, 26 mean / 48 max connections |
| `55096327`, `55096328`, `55096329` | **round 2** reps 1-3 on 0.1.11, chained, first `afterany:55064913` and the smoke | `adaptiseq_e3_dev`, 0.1.11 | `e3_round2_expanse/e3_<id>/` | record rows per panel, then score (section 5) |

Sweep reps take 8 to 11.5 h (ENA was half as fast on 10-19); round 2 is about 5 to 6 h per rep (6 panels x 7 arms).
Expect sweep rep 3 to end around 06:00 to 09:00 PDT 10-20 and round 2 around 01:00 to 03:00 PDT 10-21.

Watch a job with `ROOT=<results root> MIN_NEW=<n> bash tools/watch_rows.sh <jobid>`
(run_in_background; it returns on a gate line, on n new rows, or at job end, and appends
an ENA portal probe to `ena_portal_status_20261015.tsv` every 5 min). Per-row routine:
inspect the arm's log (`sed 's/\x1b\[[0-9;]*m//g'`, grep `MD5 mismatch|probe attempt|Single-conn|failed
after|ContentLengthError|attempt 3/3 failed|adaptive worker summary`) and its `conc_*.tsv`
(column 4 = archive connections; mean/max), add rows to the right table in
`remaining_tasks.md` (python `str.replace` on a unique anchor), commit, push. Batch rows
(e.g. MIN_NEW=4 or a whole panel) rather than one commit per row.

## 4. Results so far

Sweep (0.1.7, every arm complete and md5-verified; seconds):

| -j | 3r rep 1 | 3r rep 2 | 3b rep 1 | 3b rep 2 |
|---|---|---|---|---|
| 1 | 4197 | 10554 | 9708 | 11112 |
| 2 | 3264 | 3104 | 3291 | 3922 |
| 4 | 1250 | 2176 | 1627 | 2301 |
| 8 | 505 | 639 | 731 | 939 |
| 16 | 440 | 723 | 469 | 1106 |
| 32 | 163 | 593 | 859 | 805 |
| 64 | 235 | 298 | 428 | 1105 |
| default (topdown) | 363 | 556 | 581 | 1126 |

Tournament round 1 (0.1.9, NCBI + GSA only, 3 reps, `e3_tournament_expanse/`): NCBI is
link-limited (all arms within 13 %); GSA swings 3-4x between reps. By the round-2 rule
(`python bench/e3/score_round2.py e3_tournament_expanse/e3_*/e3_results.tsv`): bottomup 3
wins of 6 and the only one qualifying, topdown 4 wins (GSA panel median 1.89x), greedy 3,
budget 2, fixed-j20 2. `budget` lost GSA partly to my mistake (its "3 cut-short responses =
distress" rule; GSA cuts streams at any load). An exploratory 0.1.8 rep is in
`e3_ctrl_expanse/` (does not count).

Source speeds (`diag_sources/out_55066512/`): NCBI AWS 32 MB/s per connection (link-
limited near 16), GSA 9.5 on 1 / 30 on 8 (saturates), ENA about 2 per connection.

## 5. The current task: a controller that wins most cases with few connections

User, 2026-10-19: "I want a controller that beat others in most of the cases for every
experiment. maintaining as low connection as possible."

- `knee` controller, 0.1.10 (`9eb5bca`; `adaptiseq/batch.py` `_run_knee`,
  `--controller knee`): starts at 4 connections, doubles while each doubling earns half its
  proportional gain (3 s windows), tries the midpoint, settles on the smallest budget that
  paid, then holds and re-tests +-25 % every third 8 s window; distress = 429/503 /
  refused-with-nothing-open / dropped (not cut-short); no judging in the tail; with `-j`
  unset the pool may grow to 64 (`Options.jobs_explicit`, `KNEE_POOL`). Not the default.
- Round 2 (submitted): arms knee, topdown, bottomup, budget, greedy + fixed-j20, fixed-j64;
  panels 4r, 4b (ENA), 4s (NCBI), 4g (GSA), 4h (held-out ENA, D3_seg 2 x 11.5 GB), 4m
  (mixed: 13 ENA + 2 GSA runs). Criterion fixed before the data, in `remaining_tasks.md`
  and `bench/e3/score_round2.py`: a case = (panel, rep); a win = within 10 % of the
  fastest arm in that case; rank by wins, ties by lower mean archive connections;
  disqualified if any run is not md5-verified or the median ratio on any panel > 1.5.
  Score with `python bench/e3/score_round2.py e3_round2_expanse/e3_*/e3_results.tsv`.
- After round 2: report the ranking to the user and recommend. Making the winner the
  default (`Options`/`controller_mode` default and README) is the user's decision; then
  the paper's 5-rep chain (3r + 3b, all tools, `ARM_SET=submission`) on that build,
  results root `e3_submission_<version>_expanse`. Don't change a candidate while a round
  runs; a fix means a new round with fresh reps.
- Caveat for the paper: knee was designed on the round-1 panels; round 2 uses fresh reps,
  a held-out panel and a mixed list.

## 6. Open items for the user (not yours to decide)

Decision A (completion claim wording), B (report md5-verified separately; recommended),
the Fabric half of the paper, co-authors/ORCIDs/funding, allocation number
(TG-CIS250262 vs CIS250262), PyPI release (PyPI has only 0.1.3; 0.1.4 to 0.1.9 are local
wheels), Zenodo, Bioconda (task written in `remaining_tasks.md`; needs PyPI first),
merging `origin/app-notes` `6ae2fd3`, the iSeq GSA/GEO note for Table 1, `-r ftp` stalls
at ENA (docs note or HTTPS fallback), optional block-by-block corruption diagnostic
(`diag_batch` with `METHODS=curl-ftp,curl-https,aseq-https ROUNDS=1`).
