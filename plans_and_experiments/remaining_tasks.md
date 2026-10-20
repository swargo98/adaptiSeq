# Remaining tasks after executing MINIMAL_SUBMISSION_PLAN.md

Written 2026-10-13 on branch `app-notes`. Nothing has been committed, pushed,
tagged, or published; every change is in the working tree for you to review.

The plan has four steps. Steps 1 and 3 are done as far as they can be without
your accounts or the two benchmark machines. Step 2 is prepared and smoke-tested
but not run. Step 4 is drafted with placeholders where results go.

Three things I found along the way change what the paper can claim. They are in
"Decisions needed before the benchmark" and should be read first.

---

## Update 2026-10-13, Expanse (`login02`, account `umr115`)

Fresh clone of `app-notes` at `3b073f1` in `/home/rswargo/adaptiSeq`. This
session's changes are committed locally as they come in (from `4947475` on);
nothing was pushed, tagged, or published.

**Branches (2026-10-14 18:15 PDT):** this work is pushed to
`expanse-app-notes` (remote `expanse`, deploy key). `app-notes` on GitHub got
a separate commit from the Node-MICH machine, `6ae2fd3` "3b and 3r running"
(its gate results plus its own fix for the ENA error body in `metadata.py`,
`batch.py`, `core.py`). That fix and ours (`41ac3c9`) touch the same lines,
so merging the two branches will conflict there; I have not merged. Keep one
of the two fixes when you merge (ours has the tests in
`tests/test_list_resilience.py` and also keeps a list going past a failed
accession).

**State of the benchmark (2026-10-18 12:35 PDT): rep 1 done (hit by ENA portal outage; re-run queued as `54997452`), rep 2 and rep 3 done, rep 4 running.**

| Job | What | State |
|---|---|---|
| `54902878` `adaptiseq_setup` (`shared`, 8 cores, 2 h) | env, wheel, tests, README check, ENA probe | **COMPLETED** 20:40 to 21:20 PDT on `exp-1-44`, all steps passed (below) |
| `54902879` `adaptiseq_gate` (`compute`, exclusive, 20 h limit) | the gate: one rep of 3r + 3b | **TIMEOUT** at the 20 h limit (21:20 to 17:20 PDT) inside the 3b `iseq` arm, as predicted; 3b Kingfisher did not run. GATE PASS (md5 gate); `check_run.txt` lists the missing rows. Node `exp-5-53` (AMD EPYC 7742, 128 cores, 251 GB, 870 GB free NVMe) |
| `54908326` `adaptiseq_setup` | rebuild the wheel from the checkout (with the ENA-error, list-resilience and stale-`.part.meta` fixes), reinstall into `adaptiseq_e3_sub`, tests, README check | **COMPLETED** 17:44 to 17:49 PDT, all passed; new wheel sha256 `2a0a6f5c...` (below); ENA probe 2.1/15.6/43.7 MB/s at 1/8/20 connections |
| `54927001`, `54927008`, `54927009`, `54927010`, `54927011` `adaptiseq_e3` | the full run: reps 1 to 5 of 3r + 3b, one rep per job (48 h limit, about 24.5 h each) | `54927001` (rep 1) **COMPLETED** 23:24 10-14 to 04:23 10-16 (29 h) on `exp-4-08`; `54927008` (rep 2) **COMPLETED** 04:24 10-16 to 11:15 10-17 (30 h 51 min) on `exp-3-36`, check_run CHECK FAIL (3 timeouts: 3r iseq, 3b iseq, 3b fastq-dl); `54927009` (rep 3) **COMPLETED** 11:15 10-17 to 12:32 10-18 (25 h 17 min) on `exp-3-36` (same node as rep 2), check_run CHECK PASS (no timeouts; 3b adaptiseq-default and fixed-j20 7/8 rc=1 on md5); `54927010` (rep 4) **RUNNING** since 12:33 10-18 on `exp-2-48`. Rep 4: GATE PASS, wheel `2a0a6f5c...`, link probe 2.0/12.3/29.0 MB/s at 1/8/20 connections, back to rep 1 and 2 levels (about 2 MB/s per connection), so rep 3's 7.2 MB/s was a passing state, not a lasting change at ENA. Rep 4 3r order starts with iseq. **2026-10-18 15:50 PDT, user: cancel the two queued 0.1.4 jobs.** `54927011` (rep 5) and `54997452` (rep 1 re-run) are CANCELLED, saving about 6,200 SU: the paper should benchmark the fixed adaptiSeq (see "Why adaptiSeq lost panel 3b"), not 0.1.4. **Then, user: cancel rep 4 too.** `54927010` CANCELLED at 15:50 10-18 after 3 h 17 min (3r iseq and adaptiseq-default done; 3r kingfisher was cut off mid-arm, its log is partial and it has no result row). The 0.1.4 record is reps 1 (outage), 2 and 3 in full, and rep 4's two 3r rows. **Next, user's order: build 0.1.5 with the fixes, check it on panel 3b, then run a fixed-j sweep.** **Done / submitted 2026-10-18:** 0.1.5 wheel `1a1aeeca...` built and tested (`setup_expanse_55057801`: offline + network suites pass, README examples 3/3). **Note: PyPI has only 0.1.3; 0.1.4 was never uploaded**, so the 0.1.4 benchmark ran a local wheel too. Submitted, all `ENV_NAME=adaptiseq_e3_sub`, wheel 0.1.5, timeouts 3r 10800 / 3b 30000:
- `55057914`: 3b check, `ARM_SET=aseq` (adaptiseq-default + fixed-j20), 1 rep, `RESULTS_ROOT=e3_v015_expanse`; waits `afterany` on diag `55055531` so the two do not share ENA.
- `55057915`, `55057916`, `55057917`: fixed-j sweep reps 1, 2, 3 (`PANELS="3jr 3jb"`, -j 1 2 4 8 16 32 64 + default, one rep per job, about 9 to 10 h each), `RESULTS_ROOT=e3_jsweep_expanse`, chained `afterany`. If the check shows a problem, cancel these before they start. **18:41 10-18: `55057914` failed in 4 s at the egress check** (node `exp-10-14` could not resolve `ftp.ncbi.nlm.nih.gov`; the ENA hosts were fine), so nothing ran (`e3_v015_expanse/failed_55057914/`). Resubmitted as **`55061121`** with `--exclude=exp-10-14`; sweep rep 1 `55057915` now waits `afterany:55061121`.

0.1.5 check (`55061121`, `e3_v015_expanse/e3_55061121/`, `exp-7-23`, link probe 2.2/16.7/40.7 MB/s, GATE PASS, wheel `1a1aeeca`):

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3b | adaptiseq-default | 1611 | 8/8 | 0.1.4: 4481 / 6552 / 7474 s, 6/8 / 8/8 / 7/8. No md5 mismatches and no refused-connect warnings this time, so fix 1 was not exercised. Connections rose to 45 in the first 4 min (0.1.4 never passed 25, so 25 was the old breaker's level, not a hard ENA limit), then the controller held **1 worker** for the last 20 min ("best 731 Mbps at 8 workers; last 5 Mbps at 1 worker", recent probes all 1w at 12 to 44 Mbps), at about 5 connections. 18:44 to 19:09 PDT |
| 3b | adaptiseq-fixed-j20 | **379** | 8/8 | 0.1.4: 1515 / 2500 / 10586 s. 26 GB at 68 MB/s: about 44 connections for the first 5 min (peak 50), done in 6.3 min. No mismatches, no refusals. **4.2x faster than the 0.1.5 adaptive default in the same job**, so the controller, not the engine, is now what limits the default. 19:09 to 19:16 PDT |

**Sweep held (19:17 10-18).** `55057915`/`16`/`17` are on `scontrol hold`: the sweep's adaptive arm would measure a
controller known to collapse to 1 worker at ENA. Release with `scontrol release 55057915 55057916 55057917`.

**Controller trace `55061744` (0.1.5, `diag_ctrl/out_55061744/`): the slow default was a per-file tail, not the
controller.** All 16 files started in the first 5 s (gate 16), so later worker counts changed nothing; 26 GB
mostly arrived in 4 min on about 50 connections (up to 94 MB/s), then the last 5 files took 15 min on about 5
connections, one slow segment each. Fixed -j 20 in the same job: 788 s at a steady 25 connections (the check's
379 s was a fast spell; ENA varies about 2x within an hour). Fix 1 fired once (SRR15852406_2 re-fetched in the pool).
**Fix (`1686708`, 0.1.6):** a finished segment's connection takes half of the largest remainder, and spare budget
with an empty queue splits files further (up to `--max-segments`); the grown plan resumes from `.part.meta`.
0.1.6 wheel `c7db4012...` built and tested (`setup_expanse_55063507`, suites and README pass).

**Resubmitted on 0.1.6 (21:10 10-18):** the 0.1.5 sweep jobs `55057915`-`17` CANCELLED (never ran). `55063970` 3b
check (`ARM_SET=aseq`, `e3_v016_expanse`), then `55063971` controller trace, then sweep reps 1 to 3 `55063972`,
`55063973`, `55063974` (`e3_jsweep_expanse`), all `--exclude=exp-10-14`. The sweep jobs are **held** until the check
and trace are read; release with `scontrol release 55063972 55063973 55063974`.

0.1.6 check (`55063970`, `e3_v016_expanse/e3_55063970/`, `exp-9-14`, probe 2.4/15.0/39.9 MB/s, GATE PASS, wheel `c7db4012`):

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3b | adaptiseq-default | 1774 | 8/8 | No better than 0.1.5. **Cause: refused range probes.** ENA refused a few `bytes=0-0` probes; `probe_range_support` read a failed probe as "no ranges" and those files (about 5) went `download_single_connection`, 1.5 to 2 GB each on one connection ("Single-conn attempt n/3 failed: Cannot connect", two files failed a round and were retried). Splitting cannot help a single-stream file. Present since 0.1.4; a refused first probe could also cache FTP as the host's transport. 21:10 to 21:39 PDT |
| 3b | adaptiseq-fixed-j20 | **288** | 8/8 | 90 MB/s, 44 to 49 connections for 4 min; no probe failures this time. 21:39 to 21:44 PDT |

**Fix (uncommitted, suite `55064720` queued):** the probe takes a host slot, waits at the connection ceiling, retries (4
attempts), and raises `ProbeError` instead of reporting "no ranges"; `_probe_ftp_kind` catches it and still falls back
to FTP when HTTPS never answers. The 0.1.6 trace `55063971` was cancelled (it would only show this bug again); the
held sweep jobs carry the 0.1.6 wheel and will be resubmitted on 0.1.7. **Done 22:10 10-18:** fix committed as `c2f6f5c` (0.1.7); wheel `2fa62d66...` built and tested (`setup_expanse_55064856`). 0.1.6 sweep jobs `55063972`-`74` CANCELLED (never ran). On 0.1.7: `55064909` 3b check (`e3_v017_expanse`), `55064910` controller trace, sweep reps 1-3 55064911 55064912 55064913 (**held**; release with `scontrol release 55064911 55064912 55064913`).

0.1.7 check (`55064909`, `e3_v017_expanse/e3_55064909/`, `exp-7-44`, probe 2.2/16.5/43.2 MB/s) and trace (`55064910`, `diag_ctrl/out_55064910/`, same node, right after):

| panel | arm | check wall_s | trace wall_s | runs | notes |
|---|---|---|---|---|---|
| 3b | adaptiseq-default | 529 | 378 | 8/8, 8/8 | No single-stream files, no probe retries logged, no md5 mismatches. Check: committed 4 workers, steady 25 connections, about 50 MB/s. Trace: probes 16w 966 Mbps, 8w 1006 Mbps, committed 8. 0.1.4: 4481 to 7474 s; 0.1.5: 1611; 0.1.6: 1774 |
| 3b | adaptiseq-fixed-j20 | 319 | 361 | 8/8, 8/8 | 0.1.4: 1515 to 10586 s |

The default is now 1.05x (trace) to 1.66x (check) of fixed -j 20; the remaining gap is the controller committing to 4
workers (25 connections) in the check. **Sweep released 22:30 10-18** (`55064911`-`13`), so the fixed-j sweep runs on 0.1.7.

**Controller tournament (user, 2026-10-19: "add this new controller logic (and maybe one or two more) using some
name; do not make it default; test on every source the paper claims; whichever performs best becomes the default").**
Code (uncommitted until the suite passes): `--controller topdown|bottomup|budget|greedy` (Options.controller /
`fetch(controller=)`; default unchanged, `None` -> `ASEQ_ADAPTIVE_MODE` -> topdown).
- `budget` (new): every worker active; steers a per-host *connection* budget (HostGuard.set_budget) instead of a worker
  count. Starts at min(cap, max(16, 2 x jobs)) (40 at -j 20), raises by a quarter while the gain is at least half of
  proportional, otherwise reverts, holds and tries a quarter cut (kept if it costs under a quarter of proportional);
  cuts 30 % on distress (429/503, refused with nothing open, dropped streams, >= 3 ceiling refusals per window);
  windows of 10 s; no judging once the queue is empty (the budget then only feeds segment splitting).
- `greedy` (new): what fixed -j does plus a reaction: all workers active, -25 % on 429/503, +10 % of the cap per quiet window.
- `topdown` (current default) and `bottomup` (original gradient) unchanged.
Sources the paper claims (Summary: "GSA, SRA, ENA, DDBJ, and GEO"); DDBJ and GEO accessions resolve to ENA/NCBI files, so
the distinct servers are ENA, NCBI's AWS copies (.sra) and GSA. Harness (`run_e3.sh`, replaced atomically while the
sweep runs; old panels unchanged): 4r ENA small (D1_full), 4b ENA large (D2_subset), 4s NCBI (.sra of the 3b runs, `-d sra`),
4g GSA (CRA002399, 3 runs), 4x DDBJ+GEO routing (default only). Arms: the 4 controllers + fixed -j 20 (+ best fixed
from the sweep via `E3_CTRL_FIXED`). Datasets: `bench/e3/make_ctrl_datasets.sbatch` (NCBI has no md5 for its AWS copy,
so reference copies are fetched and hashed once).
**Selection rule, fixed before any tournament data:** 3 reps per panel, arm order shuffled per rep, after the sweep.
(1) A candidate must complete every run (md5-verified) in every rep of every panel, or it is out. (2) Per panel, score
= median wall_s / the best arm's median wall_s in that panel (fixed references included). (3) Pick the lowest
worst-case score over the 4 panels; within 5 %, the lower geometric mean; still tied, the simpler / current one.
(4) The winner then becomes `adaptiseq-default` and is measured fresh in the paper's 5-rep chain; tournament numbers
are not reused as paper results (they go in the supplement, all candidates shown).
**Found while preparing GSA (2026-10-19): GSA downloads were broken.** GSA's browse page
(`ngdc.cncb.ac.cn/gsa/browse/CRA/CRR`), which adaptiSeq and iSeq read the download links from, now answers scripts
with a JavaScript "browser check" page and no links. Not worked around: adaptiSeq now takes the links from the
run-info table that GSA's API returns (`Download_path`) and fetches them from `download.cncb.ac.cn` over HTTPS
(range-capable; `download.big.ac.cn` has no HTTPS). Also: GSA runs now join the batch pool (they used to download one
file at a time, though the paper says resolution is concurrent for all five), with in-pool md5 from `md5sum.txt`; and
the GSA md5 retry now deletes the bad file first (the same fix SRA got in 0.1.4).
**Source speeds from a compute node (`diag_sources/out_55066512/`, 01:00 PDT 10-19, 20 s ranged GETs):** NCBI's AWS copy
(`sra-pub-run-odp.s3.amazonaws.com`) 32.4 MB/s on 1 connection, 257.6 on 8 (32 per connection, linear); GSA
(`download.cncb.ac.cn`) 9.5 on 1, 29.6 on 8 (3.7 per connection: it saturates early); ENA 2.0 on 1, 16.3 on 8 (2 per
connection, linear). Three different regimes, which is what the tournament needs: where a fixed -j suits one archive,
it may be far off for another. The 3b runs' .sra files are 1.9 to 3.1 GB (19.7 GB in all); GSA CRA002399 is 6 runs,
12.1 GB, so the GSA panel uses all 6 (`GSA_RUNS=6`).
**GEO was broken too (2026-10-19):** GEO's accession page (`geo/query/acc.cgi`) answers scripts with a reCAPTCHA
"Checking your browser" page, so every GSE/GSM was rejected. Fixed (`1fb6233`) through NCBI E-utilities: GSE ->
BioProject via GEO DataSets, GSM -> BioSample (its identifiers list the GSM). GEO's plain-text record is a fallback
(it returns 404 to wget's default agent; no user-agent tricks).
**End-to-end check `diag_sources/e2e_55067788/` (02:43 10-19, checkout `1fb6233`):** GSA CRR120304 (1.65 GB) over
HTTPS 62 s and over FTP 103 s (seven FTP segments got "426 Failure writing network stream" and recovered); a mixed
GSA + GEO list in one batch 632 s, both md5 OK (the topdown controller ran it on 1 worker; a mixed-archive list is
worth a tournament panel); GEO GSM7417667 -> SRR24721990 23 s md5 OK; GSE233000 -> PRJNA974701; DDBJ DRR421224
64 s md5 OK. **Bug found:** in both single-run GSA cases the md5 was skipped ("md5sum.txt is empty"): GSA refuses
connections now and then (a range probe was refused in the same minute), the md5 list fetch failed, the empty file
was never fetched again, and the run was recorded as a success unverified. Fixed (uncommitted, suite `55068312`):
the md5 list is retried (4 tries) and an empty one refetched; without an md5 list the size must match the run-info
table, and the note now says "NOT md5-verified".
**iSeq 1.9.9 cannot download from GSA or GEO now** (`diag_sources/iseq_55067790/`): `iseq -i CRR120304` prints
"download finished", exits 0 and writes `success.log`, but downloads no data file (the browse page has no links);
`iseq -i GSM7417667` and `-i GSE233000` fail with "not a valid GEO ... accession". **The paper's Table 1 lists GSA and
GEO for iSeq**; say that both stopped working when the archives put browser checks on these pages (date it), and that
iSeq's GSA path fails silently with exit 0.
**Tournament started on the non-ENA panels (03:20 10-19):** 0.1.8 wheel `63fe4b82...` (`setup_expanse_55068362`,
env `adaptiseq_e3_dev`, so the sweep's env is untouched; includes the GSA, GEO and GSA-md5 fixes). Jobs 55068446 55068447 55068448:
`PANELS="4s 4g"`, one rep each, chained, `RESULTS_ROOT=e3_ctrl_expanse`, `E3_TIMEOUT_CTRL=3600`. NCBI's AWS copies
and GSA are not ENA, so these run alongside the sweep; 4r and 4b (ENA) and 4x wait for the sweep to finish.

Tournament rows (`e3_ctrl_expanse/`; download phase = until the last archive connection closed, from `conc_*`):

| rep | panel | arm | wall_s | runs | download phase, connections (mean / max) | controller summary |
|---|---|---|---|---|---|---|
| 1 | 4s NCBI | topdown | 84.7 | 8/8 | 48 s, 24 / 64 | 2 probes; committed 4 workers |
| 1 | 4s NCBI | bottomup | 86.4 | 8/8 | 50 s, 9 / 24 | 7 probes; best at 1 worker |
| 1 | 4s NCBI | greedy | 80.3 | 8/8 | 43 s, 28 / 64 | 6 workers |
| 1 | 4s NCBI | budget | 81.2 | 8/8 | 44 s, 7 / 16 | held 16 connections |
| 1 | 4s NCBI | fixed-j20 | 82.8 | 8/8 | 46 s, 29 / 64 | - |

4s rep 1 (job `55068446`, `exp-9-37`, 03:12 to 03:20): every arm 8/8 md5-verified against the reference copies,
19.7 GB in 80 to 86 s, all within 8 %: about 4.4 Gbit/s while downloading (NCBI's AWS copy or the node's link is
the limit), then about 35 s of `vdb-validate`. `budget` matched the fastest with a quarter of fixed -j 20's
connections (16 max against 64).

GSA panel, 0.1.8 rep 1 (same job, 03:20 to 05:00 PDT = 18:20 to 20:00 in Beijing; run order greedy, bottomup, budget,
topdown, fixed-j20). All 6/6 md5-verified, 12.1 GB:

| arm | wall_s | cut-short responses | segments out of attempts | connections mean / max | controller |
|---|---|---|---|---|---|
| greedy | 1696 | 95 | 13 | 12.3 / 48 | ended at 1 worker |
| bottomup | 1852 | 95 | 17 | 7.3 / 47 | 364 probes |
| budget | 1320 | 38 | 4 | 5.0 / 16 | never left 16 (the queue-empty rule) |
| topdown | **411** | 43 | 0 | 15.5 / 48 | 6 workers |
| fixed-j20 | 714 | 68 | - | 18.8 / 48 | - |

GSA cut 38 to 95 responses short in every arm (12.1 GB / 411 s = 29 MB/s, the probe's 8-connection rate, so topdown
reached GSA's limit). The spread (411 to 1852 s) follows the run order as much as the controller: the later arms were
faster, so GSA's own load was falling through the evening in Beijing. With these swings, 3 reps per panel may not
separate the controllers on GSA; the selection rule stays as written, but the tournament should interleave the
reps over different hours. **These rows are 0.1.8 and do not count for the selection** (the budget queue-empty bug,
and none of the 0.1.9 retry fixes); the official tournament runs on 0.1.9.

**Official tournament on 0.1.9 (candidates frozen 05:15 PDT 10-19, commit `4a6051f`, wheel `cfa3acbd...`,
`setup_expanse_55071444`, env `adaptiseq_e3_dev`).** Non-ENA panels: jobs 55071526 55071527 55071528 (`PANELS="4s 4g"`, one rep each,
chained, `RESULTS_ROOT=e3_tournament_expanse`, `E3_TIMEOUT_CTRL=3600`). ENA panels 4r, 4b and the 4x routing check
are submitted after the sweep, with `E3_CTRL_FIXED` = 20 plus the sweep's best fixed -j per panel. 0.1.8 jobs
`55068447`/`48` cancelled (never ran). No code changes to the candidates from here until the tournament ends.

Official tournament rows (0.1.9):

| rep | panel | arm | wall_s | runs | connections mean / max | download phase | controller |
|---|---|---|---|---|---|---|---|
| 1 | 4s NCBI | topdown | 79.7 | 8/8 | 21.9 / 64 | 43 s | 4 workers |
| 1 | 4s NCBI | bottomup | 89.6 | 8/8 | 8.8 / 24 | 53 s | 1 worker |
| 1 | 4s NCBI | greedy | 79.3 | 8/8 | 28.0 / 64 | 42 s | 6 to 8 workers |
| 1 | 4s NCBI | budget | 81.6 | 8/8 | 7.8 / 20 | 45 s | tried 20, back to 16 |
| 1 | 4s NCBI | fixed-j20 | 90.2 | 8/8 | 24.7 / 64 | 53 s | - |
| 1 | 4g GSA | greedy | 690 | 6/6 | 19.6 / 48 | 46 cut short, 1 segment out of attempts | 6 workers, ended at 1 |
| 1 | 4g GSA | bottomup | 482 | 6/6 | 15.5 / 48 | 67 cut short, 2 out | 5 workers best |
| 1 | 4g GSA | budget | **2694** | 6/6 | 4.6 / 20 | 60 cut short, 3 out | cut to about 3 connections within 4 min |
| 1 | 4g GSA | topdown | 1761 | 6/6 | 11.6 / 48 | 73 cut short, 7 out | workers fell from about 30 to 3 connections over 28 min |
| 1 | 4g GSA | fixed-j20 | **385** | 6/6 | 21.9 / 48 | 76 cut short, 0 out | - |

Rep 1 (job `55071526`, 05:10 to 06:58 PDT, 20:10 to 22:00 Beijing). **GSA reading:** GSA cuts responses short at any
load (fixed -j 20: 76 at 22 connections; budget: 60 at under 5), so a cut-short response is not a load signal there.
`budget`'s rule "3+ cut short in a window = distress" (added in 0.1.9 after the 0.1.8 GSA rep) therefore cut it to
about 3 connections within 4 minutes and it spent 40 minutes there: my mistake, made from one observation. Holding
high concurrency (fixed -j 20, 35 connections at first) finished in 6.4 min. Candidates are frozen, so `budget`
competes as built; if it otherwise does well, the follow-up is a `budget` without that rule, evaluated on fresh reps.

| rep | panel | arm | wall_s | runs | connections mean / max | download phase | controller |
|---|---|---|---|---|---|---|---|
| 2 | 4s NCBI | fixed-j20 | 110.1 | 8/8 | 23.2 / 64 | 73 s | - (ran first) |
| 2 | 4s NCBI | greedy | 85.7 | 8/8 | 25.3 / 64 | 49 s | 6 workers |
| 2 | 4s NCBI | bottomup | 83.0 | 8/8 | 10.7 / 32 | 46 s | best at 3 workers |
| 2 | 4s NCBI | budget | 91.5 | 8/8 | 7.2 / 20 | 55 s | 16 connections |
| 2 | 4s NCBI | topdown | 78.9 | 8/8 | 22.1 / 64 | 42 s | 4 workers |
| 2 | 4g GSA | budget | 1184 | 6/6 | 11.2 / 25 | 35 cut short, 0 out | 17 to 18 connections (ran first) |
| 2 | 4g GSA | bottomup | 2187 | 6/6 | 13.4 / 48 | 106 cut short, 20 out | best at 2 workers |
| 2 | 4g GSA | greedy | 1652 | 6/6 | 16.1 / 48 | 112 cut short, 23 out | 6 workers |
| 2 | 4g GSA | fixed-j20 | 1247 | 6/6 | 21.5 / 48 | 60 cut short, 3 out | - |
| 2 | 4g GSA | topdown | **654** | 6/6 | 17.8 / 48 | 63 cut short, 0 out | 3 workers |

Rep 2 (job `55071527`, 06:59 to 09:06 PDT). **GSA is mostly noise so far:** fixed-j20 385 then 1247 s, topdown 1761 then
654, budget 2694 then 1184; the arm order changes per rep, and the same arm moves 3x between reps. Three reps will
give a median, but the GSA panel's verdict should be read as "no controller is reliably better at GSA" unless rep 3
changes the picture.

| rep | panel | arm | wall_s | runs | connections mean / max | notes |
|---|---|---|---|---|---|---|
| 3 | 4s NCBI | greedy | 85.1 | 8/8 | 26.1 / 64 | |
| 3 | 4s NCBI | budget | 85.4 | 8/8 | 8.3 / 20 | |
| 3 | 4s NCBI | fixed-j20 | 87.0 | 8/8 | 29.0 / 64 | |
| 3 | 4s NCBI | topdown | 84.2 | 8/8 | 23.7 / 64 | |
| 3 | 4s NCBI | bottomup | 83.3 | 8/8 | 10.4 / 32 | |
| 3 | 4g GSA | bottomup | 511 | 6/6 | 12.0 / 33 | 43 cut short, 0 out |
| 3 | 4g GSA | topdown | 963 | 6/6 | 11.6 / 48 | 133 cut short, 20 out |
| 3 | 4g GSA | fixed-j20 | 954 | 6/6 | 10.9 / 48 | 99 cut short, 22 out |
| 3 | 4g GSA | greedy | 657 | 6/6 | 15.6 / 48 | 53 cut short, 3 out |
| 3 | 4g GSA | budget | 589 | 6/6 | 9.5 / 25 | 40 cut short, 2 out |

Rep 3 (job `55071528`, 09:07 to 10:18 PDT). **Score after the NCBI and GSA panels**
(`bench/e3/score_tournament.py`; every arm completed every run in every rep, so all qualify):

| arm | NCBI median (s) | NCBI score | GSA median (s) | GSA score | worst | geometric mean |
|---|---|---|---|---|---|---|
| bottomup | 83.3 | 1.045 | 510.7 | **1.000** | **1.045** | 1.022 |
| greedy | 85.1 | 1.068 | 690.1 | 1.351 | 1.351 | 1.201 |
| fixed-j20 (ref) | 90.2 | 1.131 | 953.9 | 1.868 | 1.868 | 1.454 |
| topdown | **79.7** | **1.000** | 962.8 | 1.885 | 1.885 | 1.373 |
| budget | 85.4 | 1.071 | 1183.7 | 2.318 | 2.318 | 1.576 |

Caveats: on NCBI all arms are within 13 % (the link is the limit); on GSA the same arm moves 3x to 4x between reps
(bottomup 482, 2187, 511 s), so a 3-rep median there is fragile, and bottomup's GSA lead rests on two good reps of
three. The ENA panels (4r, 4b) are still to run; the decision waits for them.

**Round 2 (user, 2026-10-19: "I want a controller that beat others in most of the cases for every experiment.
maintaining as low connection as possible.") Criterion, fixed before any round-2 data** (`bench/e3/score_round2.py`):
a case = one (panel, rep); an arm wins a case when within 10 % of the fastest arm in that case; rank by cases won,
ties by lower mean archive connections (`conc_*.tsv` column 4); disqualified if any run is not md5-verified, or if its
median ratio to the fastest on any panel is above 1.5 (per panel, not per case: on round-1 GSA every arm had one case
above 1.5x). Candidates: knee (new, 0.1.10, `9eb5bca`), topdown, bottomup, budget, greedy; references fixed-j20 and
fixed-j64 (the sweep's best on 3b and close to best on 3r). Panels: 4r, 4b (ENA), 4s (NCBI), 4g (GSA), 4h (held-out
ENA, D3_seg, 2 x 11.5 GB, not used in designing knee), 4m (mixed: 13 ENA runs + 2 GSA runs in one list). 3 reps, one job
each, after the sweep. Round 1 by this criterion (NCBI and GSA only, for reference): bottomup 3 wins of 6 (qualifies),
topdown 4 wins but a GSA panel median of 1.89x, greedy 3, budget 2, fixed-j20 2.
**Submitted 18:50 10-19:** 0.1.10 wheel `25d13c2f...` (`setup_expanse_55085659`, env `adaptiseq_e3_dev`; suites and
README pass). Smoke `55090015`: knee alone on 4s and 4g (`e3_knee_smoke/`), beside the sweep (non-ENA). Round 2 jobs 55090016 55090017 55090018:
`PANELS="4r 4b 4s 4g 4h 4m"`, `E3_CTRL_FIXED="20 64"`, `E3_TIMEOUT_CTRL=7200`, one rep each, chained after sweep rep 3
(`afterany:55064913`), `RESULTS_ROOT=e3_round2_expanse`. If the smoke shows a knee problem, cancel these before
they start, fix, rebuild, resubmit. iSeq 1.9.9 presumably has the same
GSA problem; check before the paper's Table 1 claims GSA support for it.

**Knee smoke `55090015` (0.1.10 `25d13c2f`, `exp-2-23`, 21:46 to 22:13 PDT 10-19, `e3_knee_smoke/e3_55090015/`):**

| panel | arm | wall_s | runs | connections mean / max | controller |
|---|---|---|---|---|---|
| 4s NCBI | knee | 93.7 | 8/8 | 16.2 / 32 while downloading | 4c 1286 Mbps, 4c 2425, 8c 3761, 16c 4037: settled at 16, the link's knee. Round 1: 79 to 110 s |
| 4g GSA | knee | 1408 | 6/6 | 4.9 / 16 | best 641 Mbps at 8, then down to 4 to 6 for the rest (per-minute mean 11.5, 10.6, 8.7, 7.8, then 2 to 5). Round 1 GSA medians 511 to 1184 s |

**Knee misbehaved on GSA, cause found:** 22 cut-short responses (ignored, as designed) and 9 "Segment n attempt 1
refused: Connection timeout to host" at 2 to 11 open connections. `aiohttp.ConnectionTimeoutError` is not a
`ClientConnectorError`, so a connect timeout skipped the ceiling path (`note_refused`) and fell into the generic
`ClientConnectionError` branch of `download_segment_streaming`, which called `note_pushback(host, "refused")`
unconditionally: the host's cap halved, the host blocked for a backoff, and knee (and budget) read the "refused"
trip as distress and cut the budget 30 %. Knee's design says distress is a refusal *with nothing open*, so this
was a deviation from its own spec, and it applied to every arm's engine. **Fix (0.1.11):** `CONNECT_ERRORS` =
`ClientConnectorError` + `ConnectionTimeoutError` takes the refused-connect path in both the range probe and the
segment loop (ceiling while others are open, pushback with nothing open); dropped streams
(`ServerDisconnectedError`) are still distress. Tests in `tests/test_connection_ceiling.py`. **Round 2 jobs
55090016-18 cancelled 22:25 10-19 before they started** (they waited on the sweep). Rebuild `55094163`
(`ENV_NAME=adaptiseq_e3_dev`); then a fresh knee smoke and round 2 on 0.1.11, all arms on the new engine.
**0.1.11 built (00:48 10-20):** wheel `1b9ce128...` (`setup_expanse_55094163`, env `adaptiseq_e3_dev`; offline and
network suites and README examples pass). **Resubmitted:** knee smoke `55096326` (`E3_CONTROLLERS=knee`, 4s + 4g,
`e3_knee_smoke/`), beside the sweep; round 2 reps 1-3 `55096327`, `55096328`, `55096329` (same settings as before:
`PANELS="4r 4b 4s 4g 4h 4m"`, `E3_CTRL_FIXED="20 64"`, `E3_TIMEOUT_CTRL=7200`, `RESULTS_ROOT=e3_round2_expanse`), the
first `afterany` on the sweep and the smoke, the others chained. If the new smoke shows a knee problem, cancel them
before they start.

**Fixed-j sweep on 0.1.7** (`e3_jsweep_expanse/`; panels 3jr = D1_full 241 runs, 3jb = D2_subset 8 runs; -j 1 2 4 8 16 32 64 + adaptiseq-default; arm order shuffled per panel and rep).

Rep 1 (`55064911`, `exp-14-52`, probe 2.1/16.9/42.2 MB/s, GATE PASS, wheel `2fa62d66`):

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3jr | fixed-j64 | 235 | 241/241 | no fallbacks, mismatches or refusals; connections mean 17, max 25. 23:22 to 23:26 PDT |
| 3jr | fixed-j8 | 505 | 241/241 | clean; connections mean 7.5, max 16 |
| 3jr | fixed-j1 | 4197 | 241/241 | clean; 1 connection (241 runs one after another) |
| 3jr | fixed-j4 | 1250 | 241/241 | clean; connections mean 3.9 |
| 3jr | fixed-j32 | **163** | 241/241 | clean; connections mean 20.9, max 50. Faster than j64 (235): the 3r curve has a knee between 32 and 64 |
| 3jr | adaptiseq-default | 363 | 241/241 | clean; topdown committed 20 workers ("best 479 Mbps at 20"); connections mean 13.8, max 25 |
| 3jr | fixed-j2 | 3264 | 241/241 | clean; 2 connections |
| 3jr | fixed-j16 | 440 | 241/241 | clean; connections mean 13.7, max 25 |
| 3jb | fixed-j1 | 9708 | 8/8 | clean; one file at a time |
| 3jb | adaptiseq-default | 581 | 8/8 | clean; topdown committed 16 workers ("best 1732 Mbps at 16"); connections mean 23.3, max 25 |
| 3jb | fixed-j2 | 3291 | 8/8 | 3 cut-short responses, recovered; connections mean 5 |
| 3jb | fixed-j8 | 731 | 8/8 | 1 md5 mismatch and 1 probe retry, both recovered; connections mean 22.2 |
| 3jb | fixed-j16 | 469 | 8/8 | 2 md5 mismatches, recovered in the pool; connections mean 35.1, max 50 |
| 3jb | fixed-j4 | 1627 | 8/8 | clean; connections mean 10.6 |
| 3jb | fixed-j64 | **428** | 8/8 | 5 cut short, recovered; connections mean 36.1, max 50 |
| 3jb | fixed-j32 | 859 | 8/8 | 1 cut short; connections mean 22.6, max 25 |

**Sweep rep 1 done** (`55064911`, 23:21 10-18 to 07:12 10-19, 7 h 51 min, every arm complete and md5-verified).
3jr: j1 4197, j2 3264, j4 1250, j8 505, j16 440, default 363, j32 163, j64 235 s. 3jb: j1 9708, j2 3291, j4 1627,
j8 731, j32 859, default 581, j16 469, j64 428 s. Not monotonic past j8 on 3b (j32 859 s held 25 connections at most
while j16 and j64 reached 50), so ENA's state at the time matters as much as -j; reps 2 and 3 are needed.

Rep 2 (`55064912`, `exp-12-48`, probe 1.2/11.9/71.0 MB/s, GATE PASS, wheel 0.1.7 `2fa62d66`):

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3jr | adaptiseq-default | 556 | 241/241 | 2 md5 mismatches re-fetched in the pool; topdown best at 10 workers; connections mean 14.5, max 25 |
| 3jr | fixed-j4 | 2176 | 241/241 | 5 md5 mismatches re-fetched in the pool; connections mean 4.2 |
| 3jr | fixed-j64 | 298 | 241/241 | clean; connections mean 10.1, max 50 |
| 3jr | fixed-j8 | 639 | 241/241 | clean; connections mean 7.4 |
| 3jr | fixed-j2 | 3104 | 241/241 | 1 md5 mismatch re-fetched; connections mean 2.1 |
| 3jr | fixed-j1 | 10554 | 241/241 | clean; 246 s inside the 10800 s limit (rep 1: 4197 s): ENA's single-connection rate fell to about 0.7 MB/s |
| 3jr | fixed-j16 | 723 | 241/241 | 1 md5 mismatch re-fetched; connections mean 13.7, max 25 |
| 3jr | fixed-j32 | 593 | 241/241 | clean; connections mean 16.3, max 25 |

3jr rep 2 complete: j1 10554, j2 3104, j4 2176, j8 639, j16 723, j32 593, default 556, j64 **298** s (rep 1: j32 163 best,
default 363). ENA was about half as fast as in rep 1 for every arm.

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3jb | fixed-j1 | 11112 | 8/8 | 1 md5 mismatch re-fetched; connections mean 2.4 (the lone file splits now) |
| 3jb | adaptiseq-default | 1126 | 8/8 | 2 md5 mismatches re-fetched; connections mean 21.8, max 25 |
| 3jb | fixed-j4 | 2301 | 8/8 | 1 md5 mismatch re-fetched; connections mean 10.7 |
| 3jb | fixed-j16 | 1106 | 8/8 | 1 md5 mismatch re-fetched; connections mean 20.4, max 25 |
| 3jb | fixed-j64 | 1105 | 8/8 | |
| 3jb | fixed-j8 | 939 | 8/8 | |
| 3jb | fixed-j32 | **805** | 8/8 | connections 25 max |
| 3jb | fixed-j2 | 3922 | 8/8 | |

**Sweep rep 2 done** (`55064912`, 07:13 to 18:40 10-19, 11 h 27 min; `check_run` "CHECK FAIL" only lists the
submission arms a sweep job does not run). 3jb: j1 11112, j2 3922, j4 2301, j32 805, j8 939, j64 1105, j16 1106,
default 1126 s. ENA ran at about half of rep 1's rate all day, and above j8 the 3b times are within 40 % of each other.

Rep 3 (`55064913`, `exp-12-46`, started 21:26 10-19, probe 2.3/26.3/31.4 MB/s, GATE PASS, wheel 0.1.7 `2fa62d66`). ENA's
portal was down (HTTP 500) 21:18 to 21:24 and again 23:18 to 23:34 (500, 500, then a 60 s timeout):

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3jr | fixed-j64 | 688 | 238/241 md5-verified, 3 present unverified | ran first, 21:26, as the portal came back: 3 runs "no FASTQ files in the ENA database", fetched as .sra from NCBI's AWS copy; connections mean 10.3, max 53. Rep 1 235, rep 2 298 |
| 3jr | fixed-j4 | 1111 | 241/241 | clean; connections mean 3.9 |
| 3jr | fixed-j8 | 522 | 241/241 | clean; connections mean 7.2 |
| 3jr | fixed-j16 | 316 | 241/241 | clean; connections mean 10.3, max 25 |
| 3jr | adaptiseq-default | 447 | 241/241 | clean; topdown best 1215 Mbps at 10 workers, held 10; connections mean 9.8, max 20 |
| 3jr | fixed-j1 | 3727 | 241/241 | 1 md5 mismatch re-fetched in the pool |
| 3jr | fixed-j2 | 3296 | 228/241 md5-verified, 13 present unverified | started about 23:20, in the second portal outage: 13 runs had no usable ENA metadata and came from SRA; 1 range probe retried, 1 cut-short response; connections mean 2.1 |
| 3jr | fixed-j32 | **271** | 241/241 | clean; connections mean 16.7, max 25 |

3jr rep 3: j1 3727, j2 3296, j4 1111, j8 522, j16 316, default 447, j32 **271**, j64 688 s. The two arms with SRA
fallbacks still have every run present (the portal, not the download, failed); their wall times include the
.sra conversions, so read j64 rep 3 with care.

3jr rep 1 complete: j1 4197, j2 3264, j4 1250, j8 505, j16 440, default 363, j32 **163**, j64 235 s. Every arm 241/241,
no fallbacks or md5 mismatches. One rep only, and ENA varies about 2x in an hour; the j16 to j32 drop (440 to 163 s) is
bigger than the connection counts suggest (mean 13.7 vs 20.9), so wait for reps 2 and 3 before reading the curve. Rep 3: GATE PASS, wheel `2a0a6f5c...`, link probe **7.2/55.7/99.7 MB/s** at 1/8/20 connections, 3.4x rep 2's per-connection rate (2.1 MB/s) on the same node, Saturday morning PDT. Either ENA's per-connection limit was raised or eased at the weekend; it changes the absolute times for rep 3, so the paper should say the reps saw different ENA rates and lean on paired ratios. Rep 3 3r order starts with iseq. Rep 2: GATE PASS, wheel `2a0a6f5c...`, link probe 2.1/15.6/21.2 MB/s at 1/8/20 connections (20-connection rate about half of rep 1's). Rep 1: GATE PASS, `versions_e3.txt` shows wheel sha256 `2a0a6f5c...` (the rebuilt one), link probe 2.2/15.6/36.7 MB/s at 1/8/20 connections. The other three are PENDING (Dependency). **Rep 1 re-run (Decision C, user chose re-run, 2026-10-16 22:50 PDT):** `54997452`, `E3_REP_FIRST=1 REPS=1`, same env, wheel (sha256 checked `2a0a6f5c...` at submit), timeouts and `RESULTS_ROOT`, `afterany:54927011`, so it runs last. Same rep number, so the same seeded arm order as rep 1. For the analysis, pass `e3_54997452/e3_results.tsv` in place of `e3_54927001`; keep `e3_54927001` as the outage record. The first waited `afterok` on `54908326` (so a failed rebuild or test stops the whole chain); each later one `afterany` on the one before, so no two overlap. Results: `e3_submission_expanse/e3_<jobid>/` |


The first two jobs waited about 3 h in the queue because of a Lustre fault on
Expanse (about 600 compute nodes draining, "Lustre df is hung"). The full run is
submitted as above (env `adaptiseq_e3_sub`, `E3_ASEQ_WHEEL=wheels/adaptiseq-0.1.4-py3-none-any.whl`,
`E3_TIMEOUT_3R=10800`, `E3_TIMEOUT_3B=30000`, `RESULTS_ROOT=e3_submission_expanse`),
about 120 h of wall time and about 15,500 SUs once it starts. **While it runs,
do not edit `bench/e3/`, `datasets/` or the installed env:** every job reads them
when it starts. If the rebuild fails, the chain sits in `DependencyNeverSatisfied`;
`scancel` it and resubmit with the loop under "What you need to do next".

Full-run progress, rep 1 (`54927001`, `e3_submission_expanse/e3_54927001/`), 3r rows so far:

| arm | wall_s | runs | gate (`54902879`) wall_s / runs | notes |
|---|---|---|---|---|
| kingfisher | 3255 | 241/241 | 2649 / 237 | complete this time |
| adaptiseq-fixed-j20 | 1280 | 241/241 | 354 / 241 | 3.6x slower than the gate. The bulk phase held 20 connections for about 550 s (gate: about 250 s), so ENA served about half the gate's rate tonight; then about 700 s on 1 to 3 connections for the last files. One transient md5 mismatch (SRR22904281, 0.33 GB, over HTTPS), fixed by the retry; one failed segment attempt. The tail is the case the tail-end re-split (below) would address. Don't judge the speedup on one rep; use the five-rep medians |
| fastq-dl | 10800 | 44/241 **TIMEOUT** | 2395 / 237 | 5.81 of 7.59 GB verified. One FTP stream: per-run rates from the log were 1.5 to 2 MB/s until about 01:20 PDT, then 0.15 to 0.5 MB/s from 01:20 to 03:40 PDT (09:20 to 11:40 UK time, ENA's working day); two md5 mismatches retried by fastq-dl. ENA throughput clearly varies with time of day. Arm order is shuffled per rep, so the five-rep medians average this out, but the paper should say runs were spread over several days and times |
| iseq | 10678 | 143/241 md5-verified, 98 present unverified, exit 0 | 10800 / 181 TIMEOUT | Reached the last accession inside the limit and printed "download and md5 check successful" for all 241. For 98 runs, iSeq's ENA metadata query came back empty ("No metadata information found for ... in the ENA database, try to download from the SRA database"), so it fetched the `.sra` from NCBI over HTTPS and converted it to fastq.gz. The converted files can't match ENA's md5 (`format=gz,none`, `extra_files=234`, `runs_present_unverified=98`). The other 193 used ENA FTP. The gate run had no SRA fallbacks in any arm, so this is new tonight. Under ENA portal load, iSeq quietly switches archives and still exits 0. Decision B: report md5-verified runs (143) and give the present-unverified count separately. Log: wget dot-progress lines aren't removed by `strip_progress.pl` (it only handles `\r` redraws); the raw log is 36 MB, so the commit holds `3r_..._iseq_rep1.log.gz` (5.9 MB) and the raw file stays on Expanse only |
| iseq-p8 | 8600 | 198/241 md5-verified, 43 present unverified, exit 0 | 4097 / 241 | Same pattern: 43 runs fell back to SRA after an empty ENA metadata answer (06:39 to 09:03 PDT); log 10.6 MB (axel bars stripped) |
| adaptiseq-default | 1647 | **0/241 md5-verified, 241 present unverified**, exit 0 | 577 / 239 (rc=1) | Every run was resolved to SRA (`sra-pub-run-odp.s3.amazonaws.com`): `.sra` download, fasterq-dump, gzip, so nothing can match ENA's md5. **Cause: ENA's portal API was down.** A probe at 09:32 PDT returned HTTP 500 (an HTML error page) for every `filereport` query. The adaptiSeq arm ran 09:03 to 09:30. Log 58 MB raw (fasterq-dump progress); the commit holds the `.log.gz` (11.8 MB) |

3b rows, rep 1:

| arm | wall_s | runs | gate wall_s / runs | notes |
|---|---|---|---|---|
| fastq-dl | 28137 | 3/8 md5-verified, 5 present unverified | 24132 / 8 | "Querying ENA was unsuccessful" 11 times, so 5 runs went to SRA (`Archive: SRA`, AWS S3 at up to 34 connections); 5 md5 mismatches on the ENA FTP runs, each retried by fastq-dl. Ran 09:30 to 17:20 PDT, all during the outage |
| iseq-p8 | 3274 | 7/8 md5-verified, 1 present unverified | 1990 / 8 | 1 SRA fallback after an empty ENA answer (17:20 to 18:15 PDT) |
| adaptiseq-fixed-j20 | 1515 | 5/8 md5-verified, 3 present unverified | 1903 / 8 | 3 runs resolved to SRA (`sra-pub-run-odp.s3.amazonaws.com`): ENA's portal timed out (probes at 18:27 and 18:33 PDT got no answer in 60 s). 10 segment attempts failed with `ContentLengthError` (the server closed early) and were retried; no md5 mismatch. 18:15 to 18:41 PDT |
| adaptiseq-default | 4481 | 6/8 md5-verified, 2 present unverified | 4136 / 7 (rc=1) | 2 runs resolved to SRA (ENA portal). 2 md5 mismatches on ENA HTTPS `_2` files, both fixed by the retry; 6 refused connects to `ftp.sra.ebi.ac.uk:443`. The adaptive controller collapsed again: summary "85 probes; best 3690 Mbps at 14 workers; last 9 Mbps at 1 worker". **Correction (10-16):** the 3690 Mbps best is probably real. Two of the 8 runs were `.sra` files from AWS S3, and S3 can deliver a 1.6 GB file to Expanse in a few seconds. The 3r default arm of rep 1, all on S3, logged 4003 Mbps at 20 workers. The connection trace shows ENA only (the S3 transfers fall between its samples). The drop to 1 to 5 connections after about 840 s is the tail: 16 files, each with segments fixed when it starts, so connections fall as files finish. That is the tail-end re-split item, not a controller fault. A side effect worth noting: once a fast source (S3) has set the "best" probe, the controller compares slow ENA probes against it. Check that this doesn't push it down when sources are mixed. Also: the meter counts an already-complete file's full size at once (`segmented.py:346`, `ftp.py:234`). That is harmless in a fresh directory, but it would inflate a probe on a resumed batch; consider not counting it. 18:41 to 19:56 PDT |
| iseq | 30000 **TIMEOUT** | 4/8 md5-verified, 3 present unverified | ran out of the gate's 20 h | 2 SRA fallbacks logged before the cut; 7 md5 mismatches on ENA FTP (iSeq retries and keeps going). One FTP stream; 12.4 of 25.9 GB verified. Raw log 47.6 MB of wget dots; the commit holds the `.log.gz` (3.4 MB). 19:56 to 04:16 PDT |
| kingfisher | 411 | **0/8, rc=1** | did not run in the gate | The first file, `SRR15852400_1.fastq.gz` over ENA FTP (aria2c), failed Kingfisher's `pigz -t` gzip test (a corrupt transfer); `_2` passed md5. Kingfisher does not retry a corrupt file: it aborts the whole list with rc=1, so the other 7 runs never ran. 04:16 to 04:23 PDT |

Rep 1 ended **COMPLETED** at 04:23 PDT on 10-16 after 28 h 59 min. `check_run.txt`: CHECK FAIL (3r fastq-dl and 3b iseq TIMEOUT; nine rows with present-unverified runs). Committed the whole result directory (scripts, summaries, `fig3_*.png`, slurm files), except the three raw logs over 20 MB; their `.log.gz` copies are committed.

Rep 2 (`54927008`, `e3_submission_expanse/e3_54927008/`) rows:

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3r | kingfisher | 4978 | 218/241 md5-verified, 23 present unverified | 23 times "Unexpected ENA API response ... missing one or more required columns (fastq_ftp, fastq_md5)", then `aws-http` (SRA). So the ENA portal is still flaky on 10-16 (probes 200 but up to 49 s). 04:26 to 05:49 PDT |
| 3r | adaptiseq-fixed-j20 | 561 | 240/241 md5-verified, 1 present unverified | 1 run resolved to SRA (the ENA probe at 05:49 timed out). 320 files over ENA HTTPS. Gate 354 s, rep 1 1280 s. 05:49 to 05:59 PDT |
| 3r | iseq-p8 | 5139 | 227/241 md5-verified, 14 present unverified | 14 SRA fallbacks after empty ENA metadata. Gate 4097 s, rep 1 8600 s. 05:59 to 07:24 PDT |
| 3r | fastq-dl | 9545 | 239/241 md5-verified, 2 present unverified | fastq-dl retries the ENA metadata query: 12 first attempts failed, 2 also failed the second attempt and went to SRA. This is the behaviour the adaptiSeq source fix now copies. 1 md5 mismatch, retried. Gate 2395 s, rep 1 TIMEOUT. 07:24 to 10:03 PDT |
| 3r | adaptiseq-default | 1320 | 241/241 | All 321 files over ENA HTTPS. Controller: "63 probes; best 419 Mbps at 10 workers; last 5 Mbps at 1 worker". The best reading is again above the node's link probe (21 to 44 MB/s, 170 to 350 Mbps), and the arm ends at 1 worker. Gate 577 s (rc=1), rep 1 0/241 (outage). 10:03 to 10:25 PDT |
| 3r | iseq | 10800 (TIMEOUT) | 198/241 | Single ENA FTP connection (about 23 Mbps at the end); 205 runs finished before the 3 h limit hit at SRR22904459. 7 SRA fallbacks ("No metadata information found ... in the ENA database"), 7 present-unverified; 0 md5 mismatches. Rep 1: 10678 s, 143/241, 98 fallbacks. 10:25 to 13:25 PDT |
| 3b | kingfisher | 5232 | 7/8 | 7 runs via ena-ftp, all md5 OK, no corrupt files. SRR15852430 got "Unexpected ENA API response ... missing one or more required columns" at 14:48 (the portal probe saw HTTP 500 at 14:47) and came from aws-http (.sra, converted), so it is present-unverified. Rep 1: 0/8 (aborted on a corrupt pigz file). 13:25 to 14:52 PDT |
| 3b | iseq | 30000 (TIMEOUT) | 7/8 | One ENA FTP connection. 7 runs finished with "download and md5 check successful"; the limit hit during the last run, SRR15852430 (3.75 GB pair), which is left partial (counted present-unverified). 0 SRA fallbacks. 4 md5 mismatches, all retried by iSeq: SRR15852400_2 x2, SRR15852406_1 x2. Log 47 MB raw (wget dots), so the commit holds the `.log.gz` (3.4 MB). Rep 1: 30000 TIMEOUT, 4/8, 7 mismatches. 14:52 to 23:12 PDT |
| 3b | iseq-p8 | 4088 (rc=1) | 6/8 | All 8 runs from ENA FTP (axel, 8 connections), 0 SRA fallbacks. SRR15852404 and SRR15852406 failed md5 3 times each and went to `fail.log` (6 mismatches: 404_1 x1, 404_2 x2, 406_1 x3). iSeq quirk: its first retry doesn't remove the file, axel says "already there; not retrieving", and the same bad file is hashed again, so 3 tries is really 2 downloads. kingfisher got both runs md5 OK the same afternoon. Rep 1: 3274 s, 7/8. 23:12 to 00:23 PDT |
| 3b | adaptiseq-fixed-j20 | 2500 | 8/8 | All 16 files over segmented ENA HTTPS, 0 SRA fallbacks. 8 segment connects refused by `ftp.sra.ebi.ac.uk:443` (193.62.193.165), all retried. 1 md5 mismatch, SRR15852406_1, fixed by the retry. That file has now mismatched in 3 of 4 rep-2 3b arms (iseq x2, iseq-p8 x3, fixed-j20 x1); kingfisher got it OK. Rep 1: 1515 s, 5/8 (3 via SRA). 00:23 to 01:05 PDT |
| 3b | fastq-dl | 30000 (TIMEOUT) | 6/8 | One ENA FTP stream, 0 SRA fallbacks. SRR15852404_1 failed md5 3 times (02:34, 03:10, 03:41) and fastq-dl gave the run up; SRR15852406_1 mismatched once, then OK. The limit hit during the last run, left partial (present-unverified). Rep 1: 28137 s, 3/8 (5 via SRA). 01:05 to 09:25 PDT |
| 3b | adaptiseq-default | 6552 | 8/8 | All 16 files over segmented ENA HTTPS, 0 SRA fallbacks. 4 md5 mismatches, all fixed by retries (SRR15852400_2, SRR15852404_1, SRR15852425_2 x2, the last needing the third try); 8 refused connects to 193.62.193.165:443. Controller: "107 probes; best 1608 Mbps at 16 workers; last 3 Mbps at 1 worker", so most of the 6552 s was the 1-worker tail (ENA's per-connection limit), again the tail-end re-split case. 2.6x slower than fixed-j20 this rep. Rep 1: 4481 s, 6/8. 09:25 to 11:14 PDT |

Rep 3 (`54927009`, `e3_submission_expanse/e3_54927009/`) rows:

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3r | iseq | 9658 | 241/241 | First complete iseq 3r of the full run (rep 1 10678 s 143/241, rep 2 10800 TIMEOUT 198/241). All via ENA FTP: 0 SRA fallbacks, 0 md5 mismatches. Faster link today (probe 7.2 MB/s per connection). 11:17 to 13:58 PDT |
| 3r | kingfisher | 2082 | 241/241 | All 241 via ena-ftp, all md5 OK, no ENA API errors (rep 1 3255 s 241/241, rep 2 4978 s 218/241 with 23 via aws-http). 13:58 to 14:32 PDT |
| 3r | iseq-p8 | 2625 | 240/241 md5-verified, 1 present unverified | 1 SRA fallback: SRR22904279 ("No metadata information found ... in the ENA database"); every 5-min portal probe in the arm's window returned 200. The same run also fell back in rep 1 and rep 2 iseq; ENA lists it normally now, so it's probably chance, but worth watching. 0 md5 mismatches. Rep 1 8600 s 198/241, rep 2 5139 s 227/241. 14:32 to 15:16 PDT |
| 3r | fastq-dl | 7598 | 241/241 | All 241 from ENA FTP (one stream), no SRA fallbacks, no md5 mismatches or retries. Rep 1 10800 TIMEOUT 44/241, rep 2 9545 s 239/241. 15:16 to 17:23 PDT |
| 3r | adaptiseq-fixed-j20 | 644 | 241/241 | All 321 files over segmented ENA HTTPS; no SRA fallbacks, md5 mismatches or refused connects. Not faster than rep 2 (561 s) despite the 3.4x link: 15+ archive connections until 335 s, then about 300 s on 3 or fewer (31% of samples), the tail again. Gate 354 s, rep 1 1280 s. 17:23 to 17:34 PDT |
| 3r | adaptiseq-default | 725 | 241/241 | All 321 files over ENA HTTPS, no SRA fallbacks. 1 md5 mismatch, SRR22904279, fixed by the retry; that is the run that fell back to SRA in rep 1 and 2 iseq and rep 3 iseq-p8, so it is now a repeat offender (single 0.3 GB file). Controller: "14 probes; best 1366 Mbps at 20 workers; last 6 Mbps at 1 worker"; held 20 workers to 326 s, then 3 or fewer archive connections for 42% of samples (tail). Rep 1 1647 s (outage), rep 2 1320 s. 17:34 to 17:46 PDT |
| 3b | fastq-dl | 20583 | 8/8 | All 16 files from ENA FTP (one stream), no SRA fallbacks, no md5 mismatches. Mean 1.26 MB/s over 25.9 GB, well under the link probe's 7.2 MB/s per connection, so the single FTP stream is limited by more than the per-connection cap. First complete fastq-dl 3b (rep 1 28137 s 3/8, rep 2 30000 TIMEOUT 6/8). 17:46 to 23:29 PDT |
| 3b | kingfisher | 2510 | 8/8 | All 8 via ena-ftp, all md5 OK, no ENA API errors, no corrupt files. 10.3 MB/s mean. Rep 1 411 s 0/8 (pigz abort), rep 2 5232 s 7/8. 23:29 to 00:11 PDT |
| 3b | iseq-p8 | 1436 | 8/8 | All 8 from ENA FTP (axel, 8 connections), no SRA fallbacks, no md5 mismatches. 18.0 MB/s mean. Rep 1 3274 s 7/8, rep 2 4088 s 6/8 (rc=1). 00:11 to 00:36 PDT |
| 3b | iseq | 24862 | 8/8 | All 8 from ENA FTP (one connection), no SRA fallbacks, no md5 mismatches. 1.04 MB/s mean, again far under the 7.2 MB/s per-connection probe (like fastq-dl's 1.26 MB/s). First complete iseq 3b (rep 1 30000 TIMEOUT 4/8, rep 2 30000 TIMEOUT 7/8). Log 40 MB raw (wget dots); the commit holds the `.log.gz`. 00:36 to 07:31 PDT |
| 3b | adaptiseq-default | 7474 (rc=1) | 7/8 | All 16 files over segmented ENA HTTPS, no SRA fallbacks. **SRR15852425 failed md5 on all 3 tries** and went to `fail.log`: _1 mismatched on the first two downloads, then _2 on the third (adaptiSeq deletes the bad file before each retry, so these were real re-downloads, unlike iSeq). SRR15852406_1 and SRR15852415_2 mismatched once each, fixed by retries. 5 mismatches in about 21 file downloads, while every FTP arm of rep 3 3b (fastq-dl, kingfisher, iseq-p8, iseq) had 0. 6 refused connects to 193.62.193.165:443. Controller: "111 probes; best 1265 Mbps at 8 workers; last 6 Mbps at 1 worker"; 3 or fewer connections for 73% of samples after 1495 s, so slow as well (5.2x iseq-p8). Rep 1 4481 s 6/8, rep 2 6552 s 8/8 (4 mismatches). 07:31 to 09:36 PDT |
| 3b | adaptiseq-fixed-j20 | 10586 (rc=1) | 7/8 | All 16 files over segmented ENA HTTPS, no SRA fallbacks. **8 md5 mismatches**: one each on SRR15852400_1, 404_2, 406_2, 415_1, 425_2 (each fixed by the retry), and SRR15852430 failed all 3 tries (_1, then _2 twice), so it went to `fail.log`. 6 refused connects. 3 or fewer connections for 81% of samples after 1415 s, so the retries ran on 1 connection each, hence 10586 s (rep 1 1515 s, rep 2 2500 s). 09:36 to 12:32 PDT |

Rep 4 (`54927010`, `e3_submission_expanse/e3_54927010/`) rows:

| panel | arm | wall_s | runs | notes |
|---|---|---|---|---|
| 3r | iseq | 10759 | 241/241 | All via ENA FTP, no SRA fallbacks, no md5 mismatches; 41 s inside the 10800 s limit (rep 3 9658 s on the faster link). 12:35 to 15:34 PDT |
| 3r | adaptiseq-default | 721 | 241/241 | All 321 files over ENA HTTPS; no SRA fallbacks, md5 mismatches or refused connects. Controller "28 probes; best 318 Mbps at 12 workers; last 5 Mbps at 1 worker"; 15+ connections until 404 s, then 3 or fewer for 36% of samples (tail). Rep 2 1320 s, rep 3 725 s. 15:34 to 15:46 PDT |

**md5 mismatches per 3b arm, reps 1 to 3 (counted from the logs, 2026-10-18):** adaptiseq-default 2 / 4 / 5; adaptiseq-fixed-j20 0 / 1 / 8; fastq-dl 5 / 4 / 0; iseq 7 / 4 / 0; iseq-p8 0 / 6 / 0; kingfisher 0 / 0 / 0 (plus the rep 1 corrupt file that pigz caught). Both adaptiSeq arms use the same engine and segment plan (512 MB segments, so 3 per 1.5 to 1.9 GB file) and differ only in `--adaptive` vs `--no-adaptive -j 20`. The gate never interrupts an in-flight file (`batch._worker` gates at pickup only, `fetch_async` gets no pause token), so I found no code path that would make adaptive mode corrupt more, and rep 3's fixed-j20 arm then had 8, so it is not the controller. **The split in rep 3 is by transport:** the two adaptiSeq arms (segmented HTTPS from `ftp.sra.ebi.ac.uk:443`) had 13 mismatches in about 45 file downloads, all four FTP arms 0 in about 64 (17:46 10-17 to 07:31 10-18), and the HTTPS arms ran 07:31 to 12:32 PDT 10-18. In rep 2 the FTP arms had 14 between them, so FTP is not immune; it may be time of day at ENA, or ENA's HTTPS service, or adaptiSeq's ranged reads. **After the chain (it would perturb the benchmark now):** rerun `bench/e3/diag_corrupt` on SRR15852425, SRR15852404, SRR15852406 and SRR22904279 through `BatchDownloader` in both modes, several passes each, keeping every bad copy and comparing it block by block with a good one. Zero blocks at segment boundaries would mean adaptiSeq; scattered differences would mean the wire or ENA. Decision A's wording depends on the answer.

**Why adaptiSeq lost panel 3b, and what is fixed (2026-10-18, user: "making the tool robust is more important").**
From the concurrency samples (`conc_3b_*`, 5-min bins) every adaptiSeq 3b arm has two phases. Phase A, the batch,
moves all 26 GB in 25 to 35 min at 18 to 25 connections, about the same time as iseq-p8 (24 min) and faster than
kingfisher (42 min). Phase B, the per-Run md5 check, then re-downloads each corrupt file serially, one file at a time
on its 3 segments (1.5 to 3 connections), for 1 to 2.5 h. That is the whole gap. Two more things showed up:
- Connections to `ftp.sra.ebi.ac.uk` peak at exactly 25 in every adaptiSeq arm, and ENA refuses some connects
  (the 6 to 8 "Connect call failed" lines per arm). **Correction (0.1.5 check):** 25 was not a hard ENA limit; with
  fix 2 the 0.1.5 default arm held up to 45. It was where the old breaker settled after halving. Each refusal halved adaptiSeq's
  per-host cap, blocked the host, and spent one of the segment's 3 attempts.
- A 1.6 GB file is split into 3 segments of 512 MB, fixed at its start, so a lone file (the batch tail, or a
  re-fetch) uses 3 of the 25 connections ENA allows.

Fixed in source (not in the benchmarked wheel; tests in each commit, full suite `pytest_expanse_55055698` passes):
1. `4a8f115`: the batch md5-checks each `.fastq.gz` as it lands (tasks carry ENA's `fastq_md5`) and re-queues a bad
   one in the pool, so it is fetched again in parallel at full concurrency; the per-Run check reuses the digest.
2. `64c1028`: a refused connect while other connections are open holds the per-host cap at the open count and
   waits for a slot without spending an attempt (`HostGuard.note_refused`). With nothing open it is pushback as before.
3. `2838193`: a file starting near the end of a batch gets `budget // files left` segments, up to `--max-segments`,
   none under 64 MiB; a resumed `.part` keeps its stored plan.

Still open: **why the transfers are corrupt.** Diagnostic `55055531` (`diag_batch/`, started 15:26 10-18, imports
the checkout as it was before these fixes, so it measures the benchmarked engine) replays the 3b download phase,
16 files at once, twice each with adaptiSeq segmented HTTPS, adaptiSeq segmented FTP, 16 curl HTTPS streams and 16
curl FTP streams, md5-checks every file and compares bad copies block by block with good ones. It also gives the
per-connection rate of HTTPS against FTP at the same time of day.
**First two passes (15:26 to 16:30 10-18): the corruption is not adaptiSeq's.** 16 plain curl FTP streams produced
SRR15852411_1 at exactly its ENA size (1,400,303,576 bytes) with the wrong md5 (`da2052d2...`, ENA `37f6be6d...`):
a full-length corrupt transfer from a standard client over plain FTP. The same pass also shows ENA's connection
limit hitting plain tools: 6 of the 16 curl FTP streams got "Could not connect to server" (FTP needs a control and a
data connection each), and one transfer was cut short (curl 18). adaptiSeq segmented HTTPS in the same hour: 16/16
md5 OK in 1491 s (17.4 MB/s, against 11.0 MB/s for the 10 curl FTP streams that connected, about 1 MB/s each), with
13 refused connects that drove the old breaker's cap to 1. So the right response is detection and fast re-fetch,
which is fix 1. **Third pass, adaptiSeq segmented FTP (`-r ftp`), 16:30 to 18:37: 1 of 16 files in 2 h.** ENA's FTP
server reset most data connections ("Connection reset by peer", "426 Failure writing network stream", refused data
ports), so segmented FTP is unusable at ENA under its connection limit. The default (`-r auto`) picks HTTPS there,
so the benchmark arms are not affected, but `-r ftp` users would be; worth a note in the docs, or a fallback to
HTTPS when FTP segments keep failing. **I cancelled the diagnostic at 18:37** (3 h 11 min) because it held up the
0.1.5 check and the sweep (`afterany`) and the remaining passes (curl HTTPS, round 2) were not going to change the
conclusion. The block-by-block comparison never ran (it runs at the end, and the bad copies were on node-local
scratch); rerun `diag_batch` with `METHODS=curl-ftp,curl-https,aseq-https ROUNDS=1` after the sweep if the damage
pattern is wanted for the paper.

**ENA portal outage on 2026-10-15 (about 09:00 PDT, possibly earlier and partial).**
`ena_portal_status_20261015.tsv` probes one `filereport` query every 5 min from
the login node. From 09:33 to 17:20 PDT, 15 probes got HTTP 500 and 2 timed out
(000). The failures came in short windows (09:33 to 10:14 almost solid, then 1 or 2
probes per hour), and 24 successful answers took more than 10 s.
Two probes (01:19 and 04:04 PDT on 10-16) got HTTP 200 with only the header
line (24 bytes, no rows) for a run that is in ENA, so ENA's "empty" answer
can't be trusted either. The adaptiSeq fix must therefore also retry an
empty 200 (with backoff, for example 3 tries over about 1 min) before it
falls back to SRA, not only non-200s and timeouts.
The 98 iSeq and 43 iSeq-p8 fallbacks above are probably the same outage
starting on and off. Whenever an ENA query fails outright (HTTP 500, timeout,
empty body), every tool treats it as "this run is not in ENA" and goes to SRA:
iSeq does, and adaptiSeq inherits it (`metadata.get_sra_metadata`: `wget_to_file`
leaves no file on HTTP 500, `_row2_field1` is empty, `ctx.database = "sra"`).
The `ERROR occurred` retry (fix `41ac3c9`) covers only an HTTP 200 carrying an
error body. Consequences:
- For the paper, rep 1's 3r rows for iseq, iseq-p8 and adaptiseq-default (and
  any 3b arm that ran during the outage) measure an outage, not the tools. Either
  re-run rep 1 as a sixth chained job once the chain ends, or report md5-verified
  counts and say ENA was down. **User decision (C): re-run** (2026-10-16). Submitted as
  `54997452` (`E3_REP_FIRST=1 REPS=1`, `afterany:54927011`); its results replace rep 1's.
- **Done in source (not in the benchmarked wheel), 2026-10-16:** `metadata.get_sra_metadata` now retries a failed ENA query (wget exit non-zero: HTTP 500, timeout) like the error body (4 tries, 2/4/8 s), and retries an empty answer once (`ENA_EMPTY_ATTEMPTS = 2`) before it falls back to SRA. 4 new tests in `tests/test_list_resilience.py`, which fail on the old code (`pytest_expanse_54976002`). Full offline suite with the fix: 184 passed, 7 skipped (`pytest_expanse_54975961`). README notes: new "Unreleased" section, so the 0.1.4 notes still describe the benchmarked wheel. Batch mode now also prints "N accession(s) had no usable ENA metadata and will be downloaded from SRA: ..." (`core._non_ena_accessions`, test `test_batch_phase_names_accessions_sent_to_sra`). Offline suite `pytest_expanse_54977858`: all pass except `test_batch.py::test_auto_cap_does_not_truncate_intended_concurrency` (peak 7 concurrent, wants more than 8). It passed on the rerun `54977879` and in every earlier run, so it is a timing flake on a 4-core shared node; it doesn't touch the changed code. **Fixed (tests only), 2026-10-16:** the cause was the test server, not adaptiSeq. `socketserver`'s default listen backlog is 5. On a loaded node the single accept thread took about 13 ms per connection, the backlog filled, the kernel dropped SYNs, and the client retried about 1 s later. Request timings in `flaky_repeat_check/slurm_flaky_diag_54986212.out` show exactly 8 connections, then a 1 s gap. Fix: `request_queue_size = 128` on both servers in `tests/servers.py`, and that test now holds each request 0.3 s (was 0.05 s). The `>8` threshold is unchanged. Repeat check with 4 busy loops on the job's 4 CPUs: before, 35/40 loaded (`slurm_flaky_54986111.out`, delay change only); after, 40/40 idle and 40/40 loaded (`slurm_flaky_54986565.out`). Full offline suite: all pass, 7 skipped (`pytest_expanse_54986841`). **Done in source, 2026-10-16: `--no-sra-fallback`** (`Options.no_sra_fallback`). A Run with no usable ENA metadata (after the retries) or with an ENA row that lists no file now raises `MetadataError` / `DownloadError` instead of querying NCBI or calling `srapath`. In a list it goes to `fail.log` and the rest continue; exit 1. A cached SRA runinfo TSV (`metadata.is_ena_tsv` false) is queried again on ENA. Rejected with `-d sra`. `-d ena` keeps its iSeq meaning (it still falls back). 6 tests in `tests/test_no_sra_fallback.py`; offline suite 191 passed, 7 skipped (`pytest_expanse_54987992`). README Unreleased and `docs/usage` updated. Benchmark use (after the chain, needs a new wheel): an arm with `--no-sra-fallback` would report ENA outages as failures instead of present-unverified files.
- Original note: adaptiSeq improvement (after the full run, since it changes the measured wheel):
  tell "ENA failed" (non-200, timeout, network error) apart from "ENA answered and
  has no rows". Retry the first with backoff, and fall back to SRA only on the
  second. A `--no-sra-fallback` / `--require-md5` style option would stop a
  benchmark or pipeline from silently getting unverifiable files.

Setup job results (`setup_expanse_54902878/`):

- **Env** `adaptiseq_e3_sub` built from the exact pins of the Fabric export:
  iSeq 1.9.9, Kingfisher 0.5.0, fastq-dl 4.0.1, sra-tools 3.4.1, aria2 1.37.0,
  axel 2.17.13, Python 3.11.17 (`versions.txt`; full list re-exported to
  `bench/e3/env_adaptiseq_e3_sub.yml`). Note iSeq is 1.9.9 here, not the 1.9.8
  of the July env; Table 1 and the manuscript should name 1.9.9.
- **Wheel and sdist rebuilt** from this tree, `twine check` passed for both.
  New hashes (`wheel_sha256.txt`), replacing `a9f9de40...`:
  - `adaptiseq-0.1.4-py3-none-any.whl` sha256
    `40bbfd17a0703ebafcb4589710974252d87d3819c2614991b90f7f1cd1699650`
  - `adaptiseq-0.1.4.tar.gz` sha256
    `2e34f82ae26bedf7fb910aa4392f8d97023398bf6a4fe3efd64a0693a77b3114`
  The gate's `versions.txt` shows the same wheel hash, so the gate ran
  exactly these files. **Superseded 2026-10-14 17:44** by the rebuild in
  `setup_expanse_54908326/` (adds the ENA-error-body, list-resilience and
  stale-`.part.meta` fixes; `twine check` passed; tests offline and with
  network pass, only the live-Aspera opt-in skipped; README CLI and API 3/3):
  - `adaptiseq-0.1.4-py3-none-any.whl` sha256
    `2a0a6f5ca5580bd660b4bf6da5a0a4475968b6b01fd430558f644086ec3b7f25`
  - `adaptiseq-0.1.4.tar.gz` sha256
    `185e5d1221135a3670f3718aa99d0e00b422ca0e5e78a4a972b959aba09bb9e0`
  The full run uses this wheel (`check_run.txt` of each job prints the
  hash). Upload these two, unchanged, if you release.
- **Tests:** 176 collected. Offline (`ADAPTISEQ_NO_NETWORK=1`): all pass, 7
  skipped (the live tests). With network: all pass, 1 skipped (live Aspera,
  opt-in, needs `ascp` and a key).
- **README examples** (CLI and Python API) in a clean venv from the wheel on
  `SMOKE_D1`: both exit 0, 3/3 runs and 3/3 files verified by md5
  (`readme_example.txt`).
- **ENA probe from a compute node** (`exp-1-44`, public IP 198.202.103.211):
  1.7 MB/s with 1 connection, 16.9 with 8, 40.4 with 20 (1.65 to 2.11 MB/s per
  connection). Same picture as from the login node.

**iSeq 1.9.9 may no longer drop the three-file runs. This affects a claim in the
paper.** I diffed the July iSeq 1.9.8 script against the 1.9.9 now in the
benchmark env. The usage text is identical (Table 1 cells unchanged; row now
says 1.9.9). But for ENA gzip downloads, 1.9.9 loops over every `fastq.gz` link
of a run, where 1.9.8 handled exactly one or two links and failed on the 40
three-file runs of PRJNA916347; md5 is checked per file against the ENA
metadata. (The other changes: run metadata from E-utilities instead of the
Trace back end, and a wider BioSample pattern.) So iSeq 1.9.9 will probably
complete those 40 runs. The gate's 3r panel shows it either way. If it does:

- The Results sentence "none of the 40 three-file runs ... because it passes the
  three URLs to `wget` as a single string" is wrong for the version benchmarked.
  I already replaced it in `manuscript_draft.md` with a placeholder that states
  the 1.9.8 behaviour and what to delete.
- The Introduction lists "correct handling of three-file runs" as one of
  adaptiSeq's additions over iSeq. It was true against 1.9.8; against 1.9.9 it
  is not a difference. Reword or drop it, and check Fig. 1c's legend and the
  abstract's completeness sentence.
- Alternative: benchmark iSeq 1.9.8 (the July env has it). I did not do this,
  because comparing against an outdated release is easy for a reviewer to
  object to. Your call; the switch is `ENV_NAME=adaptiseq_e3` plus installing
  the wheel into it.

**Gate result, iSeq 1.9.9 at defaults (3r rep 1): TIMEOUT at 10800 s, 181 of
241 runs verified, 34 of the 40 three-file runs.** So 1.9.9 does handle
three-file runs; the July claim is out for this version (the bullets above
apply). Of the 6 three-file runs it did not complete, 2 failed md5 and 4 were
after the point where it timed out. Details:

- **Why so slow.** iSeq downloads ENA files over FTP by default (all 272
  downloads in the log are `Mode: ftp`, single `wget` stream), and ENA's FTP is
  slower per connection than HTTPS at present: 0.2 to 1.2 MB/s in this log, vs
  about 2 MB/s for HTTPS in the probes. In July the same arm took about 1470 s.
  The paper must say iSeq used its default protocol, FTP.
- **3 runs failed md5 three times** (`SRR22904281`, a single-file run;
  `SRR22904283` and `SRR22904284`, three-file runs, failing on the large
  unpaired file). The full file size arrived each time. Kingfisher and adaptiSeq
  verified these same files in the same job. About 50 min of the 3 h went to
  re-downloading `SRR22904281`. Cause unknown; diagnostic job `54907181`
  (`bench/e3/diag_iseq_md5.sbatch`, output `diag_iseq_md5_<jobid>/`) downloads
  the three files over FTP (iSeq's `wget` command) and HTTPS, compares md5 with
  ENA's, and reruns iSeq on `SRR22904281` keeping its metadata.
  **Result (01:55 to 02:05):** over both FTP and HTTPS all three files arrived
  complete and matched ENA's md5 (FTP 1.4 to 1.6 MB/s, HTTPS 2.1 to 2.3 MB/s).
  So ENA's files and md5s are consistent now, and the failures are not a
  property of these runs; a transfer problem during iSeq's window (about 23:00
  to 00:00) is the likeliest cause. Not size-related: 7 other files of 0.32 to
  0.38 GB passed iSeq's check in the same arm. The iSeq rerun in that job did
  not happen (conda activation broke under `set -u`); fixed and resubmitted as
  job `54907247`. **Result (02:07 to 02:37):** iSeq 1.9.9 itself, run alone on
  each of the three, succeeded first time (exit 0, all files md5-verified, 127
  to 290 s each). So the gate's failures were transient, not a defect of iSeq or
  of these runs. For the paper: report iSeq's completeness as measured, and if
  the full run shows md5 failures again, describe them as transient transfer
  errors that iSeq retried three times (and note that its retry counter is not
  reset between runs). Logs in `diag_iseq_md5_54907181/` and
  `diag_iseq_md5_54907247/`.

**Gate result, iSeq `-p 8` (3r rep 1): 241 of 241 runs verified, all 40
three-file runs, 4097 s, exit 0.** With axel's 8 FTP connections per file it
finishes where iSeq at defaults timed out.

**Harness fix: the iSeq `-p 8` log was 26 GB.** axel draws its progress bar
with `\r` and no newline, and without a terminal the bar is very wide, so the 3r
`iseq-p8` log grew to 26 GB (1.7 GB on disk after ZFS compression). A 1.46 GB
partial copy of it had gone into three of my local commits; GitHub refuses files
over 100 MB, so a push would have failed. I rewrote those three unpushed
commits without the file (`4f2658e`, `8cbdfba`, `d80b459` replace `732b3f7`,
`0edfff6`, `4506bd4`; messages and dates kept). The old commits are kept on the
local branch `backup/app-notes-before-log-rewrite`; delete it once you are happy
(`git branch -D backup/app-notes-before-log-rewrite`). Changes:

- `bench/e3/strip_progress.pl` (new): drops the bar redraws, keeps every line of
  text, and appends a count of what it removed.
- `bench/e3/e3_lib.sh`: each arm now writes its output to the node's scratch,
  and only the stripped copy goes to the results `logs/` directory. This takes
  effect for jobs started after this change. The running gate read the old
  version when it started, so its 3b `iseq-p8` log will be large again. (I
  replaced the file by rename, not in place, so the running job is not
  disturbed.) Also, the gate copies `bench/e3/*` into its results directory when
  it ends, so that copy will show the new `e3_lib.sh`, not the one it ran.
- `bench/e3/strip_logs.sbatch` (new): strips logs written before the fix,
  keeping the raw file as `<log>.raw.gz` (git-ignored). Job `54907912` is doing
  this for the 3r `iseq-p8` log; I will run it again for the 3b one after the
  gate ends.
- A smoke test of the changed harness (`SMOKE_D1`, all six arms) is job
  `54907911`; output in `smoke_strip_<jobid>/` (not a result).
- iSeq's retry counter (`count`) is a global that is never reset, so after the
  first run that fails md5, later failing runs get no retries. Minor; worth one
  clause if the paper discusses iSeq's failures.
- 2 runs hit the same transient ENA metadata error ("ERROR occurred. Not all
  results may have been written") that cost Kingfisher and fastq-dl 4 runs each;
  iSeq logged "not available in all databases" for them.

`paper/supplement.md` still says iSeq 1.9.8; that is correct, since those
experiments ran 1.9.8.

Because of the Lustre fault the gate writes its results to home, not Lustre:
`plans_and_experiments/e3_submission_expanse/e3_<jobid>/`. Payload still goes to
the node's local NVMe. The setup job writes to
`plans_and_experiments/setup_expanse_<jobid>/`.

**ENA limits throughput per connection for Expanse too.** This is the check the
Fabric section asked for. From `login02`, one 1.3 GB ENA file, 20 s windows:
2.2 MB/s with 1 connection, 16.2 with 8, 44.3 with 20 (2.0 to 2.2 MB/s per
connection throughout). In July a single stream from Expanse got 9 to 13 MB/s.
So the limit is not specific to the Fabric networks; EBI applies it generally
at present, at about twice the rate Fabric saw. Consequences:

- The July timeouts no longer hold. At 2.2 MB/s a single-stream arm needs about
  3.3 h for 3b (limit was 7200 s) and about 1.2 h for 3r (limit 5400 s). The
  gate is submitted with the values the Fabric section proposed,
  `E3_TIMEOUT_3R=10800 E3_TIMEOUT_3B=30000`.
- One repetition will take roughly 12 h, not 2.7 h, so five repetitions (about
  60 h) do not fit in one 48 h job. `run_e3.sh` now takes `E3_REP_FIRST`, so the
  run can be split across jobs (for example reps 1 to 3, then
  `E3_REP_FIRST=4 REPS=2`); each rep keeps the arm order it would have had in a
  single job. `analyze_submission.py` already accepts several TSVs under one
  machine name (`--tsv Expanse=a.tsv --tsv Expanse=b.tsv`).
- The comparison now measures tools against a per-connection limit. Tools that
  open more connections win by roughly the number of connections, which favours
  adaptiSeq more than the July data did. The paper should state the limit and
  the probe figures (the gate records them in `link_probe.txt`); a reviewer who
  reruns on a day without the limit will see smaller ratios.
- The login-node figures are from a login node. The setup job and the gate
  repeat the probe from compute nodes; use those in the paper.

**The wheel changed, and so did its sha256** (new hash above). I edited files
that go into the package (below), so the wheel built on the Fabric node
(`a9f9de40...`) was no longer what would be released. The setup job rebuilt the
wheel and sdist from this tree and replaced the files in `wheels/`; the gate runs
that wheel. No valid benchmark row exists for the old wheel, so nothing is lost. The earlier
advice still applies: upload exactly the file in `wheels/`. `pyproject.toml`,
`README.md`, `LICENSE`, and everything under `adaptiseq/` go into the wheel, so
a change to any of them means a rebuild and a new sha256 (`CITATION.cff` does
not). If only the metadata files change, the code the benchmark ran is still
identical, but the hash in the TSV rows will not be the one PyPI shows.

Done in this session:

- **FastBioDL licence (Step 1, item 2): resolved.** FastBioDL is public and MIT
  (`github.com/swargo98/FastBioDL-Adaptive-Parallel_Downloader`, "Copyright (c)
  2025 Rasman Mubtasim Swargo"). MIT requires the notice to travel with copied
  portions, so the notice is now reproduced in `LICENSE` next to iSeq's,
  verbatim from FastBioDL's `LICENSE`.
- **README comparison table (Step 1, item 4): corrected** in the three places
  Table 1 flagged. Kingfisher: "Python API ✔", databases "SRA, ENA, DDBJ, GSA
  (experimental)", accessions "All except GEO". pysradb: "Batch ✔" (I confirmed
  in the 2.5.1 source that `--threads N` maps the file list over N threads;
  default 1). The sentence "No other tool combines all three" is still true.
  These are edits to how your table describes competitors, so please read the
  two rows.
- **README update notes for 0.1.4** now also list the retry fix and the licence
  and table changes.
- **`pyproject.toml` author** changed from `swargo98` to `Rasman Mubtasim
  Swargo` (the name on FastBioDL's licence and on arXiv). Co-authors, ORCIDs,
  and affiliations are still yours to add, there and in `CITATION.cff`.
- **Table 1: no `?` left.** fetchngs resolves ids in parallel (one Nextflow task
  per id) with no request-rate cap; its lookup script waits and retries after an
  HTTP 429 or 500. Read from the source at tags 1.12.0 and 1.13.0. The row now
  describes 1.13.0 (the current release, 2026-09-15); 1.13.0 also adds a
  `fastq-dl` download method and no longer lists Synapse ids.
- **References: all verified, none pending.** FastBioDL author order is Swargo,
  Arslan, Arifuzzaman on arXiv (2508.05511), which is what the draft and
  `CITATION.cff` have. (FastBioDL's own README has a commented-out BibTeX entry
  with Arifuzzaman second; that one is the odd one out.) I found no published
  proceedings version of the FastBioDL paper in Crossref, so it stays an arXiv
  citation; replace it if the PDSW version has a DOI. fetchngs is cited as Patel
  H, Garcia MU, Talbot A *et al.*, v1.13.0, from its Zenodo record. Archive
  references added and cited in the Introduction: SRA (Katz 2022), ENA (Yuan
  2026), DDBJ (Ara 2026), GSA (Chen 2021), each checked in Crossref.
- **Introduction, the two statements to check (Step 4, item 4).** "Tens of
  millions of runs" holds: ENA's portal counts 44.4 million read runs and NCBI
  Entrez 47.2 million SRA records (both queried 2026-10-13). The second
  statement was wrong and is rewritten: fetchngs is not the only tool with
  parallelism across runs, because pysradb has `--threads`. The text now says
  fetchngs runs one task per run, pysradb can download several files at once
  when given a thread count (default one), and the others are sequential.
- **Acknowledgements (Step 4, item 3): drafted.** The ACCESS sentence and grant
  numbers are copied from access-ci.org's acknowledgement page, with the
  Expanse, ACCESS, and FABRIC citations (DOIs checked). The FABRIC grant list
  matches the FABRIC portal footer. Two things for you: the allocation number
  (`expanse-client user` reports `TG-CIS250262`; I wrote `CIS250262`), and
  whether the FABRIC sentence stays, which depends on whether FABRIC results
  are in the paper. Funding, co-authors, and corresponding author are still
  placeholders.
- **Harness.**
  - `bench/e3/setup_expanse.sbatch` (new): one job that creates the env, builds
    and installs the wheel, runs the tests offline and with the network, runs
    the README's CLI and Python examples from the wheel in a clean venv, and
    probes ENA at 1, 8, and 20 connections.
  - `setup_env.sh`: `ENV_FILE=<yml>` creates the env from exact pins.
  - `e3_expanse.sbatch`: `ENV_NAME` selects the env; the link probe is replaced
    (it downloaded a 17 KB file, so it finished in one round trip and measured
    nothing; it now uses a 1.3 GB file at 1, 8, and 20 connections); the node's
    CPU, memory, and scratch are recorded in `machine.txt` for the methods
    paragraph.
  - `run_e3.sh`: `E3_REP_FIRST`; `check_run.py`: `--rep-first`.
- **Environment (Step 2, item 2): decided as "rebuild, same builds as Fabric".**
  The setup job creates a new env, `adaptiseq_e3_sub`, from
  `bench/e3/env_adaptiseq_e3.yml` (the Fabric export: iSeq 1.9.9, Kingfisher
  0.5.0, fastq-dl 4.0.1, sra-tools 3.4.1, aria2 1.37.0, Python 3.11.17). The
  July env `adaptiseq_e3` (iSeq 1.9.8, adaptiSeq 0.1.3 editable) is untouched.
  If you would rather benchmark the July versions, submit with
  `ENV_NAME=adaptiseq_e3` after installing the wheel into it.

Not done here, and why:

- **The gate**: running (job `54902879`); results not in yet.
- **The full run**: waits on the gate.
- **Env build on the login node**: tried first and failed twice ("Resource
  temporarily unavailable": the login nodes cap virtual memory at 8 GB). Moved
  to a compute node at your instruction. The empty `adaptiseq_e3_sub` stub those
  attempts left in `~/.conda/envs` is removed.
- **Release, Zenodo, publishing the benchmark files**: unchanged, yours.

### What you need to do next

1. ~~When the setup job has run, read `setup_expanse_<jobid>/`.~~ Done: all
   passed (above).
2. When the gate has run, read `e3_submission_expanse/e3_<jobid>/`:
   `check_run.txt`, `manual_md5_check.txt`, `link_probe.txt`, and in
   `e3_results.tsv` the `wall_s` of every arm and `runs_present_unverified` for
   Kingfisher (decision B).
   **Timing from the gate so far:** 3r arms took Kingfisher 2649 s,
   adaptiSeq-j20 354 s, fastq-dl 2395 s, iSeq 10800 s (timeout). Because iSeq
   uses FTP, its 3b arm will very likely run to the 30000 s timeout too.
   **Update 2026-10-14 09:53:** the first 3b arm, fastq-dl, took 24132 s
   (6.7 h, 8/8 runs, about 1.1 MB/s: one FTP stream per file; one md5 mismatch
   on `SRR15852406_2`, which fastq-dl re-downloaded by itself). The seeded 3b
   order for rep 1 is fastq-dl, iseq-p8, adaptiseq-fixed-j20,
   adaptiseq-default, iseq, kingfisher, so the gate's 20 h limit (17:20 PDT)
   will stop it inside the `iseq` arm and Kingfisher's 3b arm will not run in
   the gate. My estimate for one repetition is now about 24 h (3r about 5.8 h;
   3b about 18 h: fastq-dl 6.7 h, iSeq up to 8.3 h, Kingfisher about 2.5 h at its
   3r rate, iSeq `-p 8` and the two adaptiSeq arms about 1 h together).
   **Two repetitions do not fit in a 48 h job**, so the full run is 5 chained
   jobs of one repetition each (`E3_REP_FIRST=1..5 REPS=1`, `afterany`),
   about 120 h of wall time and about 15,500 SUs (128-core node; the
   allocation has about 159,000 left). Lowering the iSeq/fastq-dl timeouts
   would shorten this but report less of them; I would keep them.
   **Update 11:00:** 3b iSeq `-p 8` took 1990 s and adaptiSeq-fixed-j20
   1903 s, both 8/8 (about 13 MB/s each; its log stayed at 22 KB, so no
   stripping needed). So on 3b adaptiSeq is only about 5% faster than iSeq
   `-p 8` in this rep, against 11.6x on 3r. The connection log shows why:
   adaptiSeq held about 17 HTTPS connections for the first 20 minutes, but
   the path gave about 13 MB/s whatever the connection count (the setup-job
   probe got 40 MB/s at 20 connections the evening before), and the last
   10 minutes ran on 8 or fewer connections while the largest files' final
   segments finished. Six segment connects to `ftp.sra.ebi.ac.uk:443` were
   refused and retried. These three arms together take about 1.6 h, so a
   repetition is about 24.5 h; one per 48 h job still holds. A 3b result
   this close is worth knowing before the paper's claims are written: the 3b
   speedup should be reported from the five-rep medians, and a tail-end
   re-split of the last segments would be a real improvement but changes the
   tool under test, so not before the full run.
   **Update 12:09:** 3b adaptiSeq-default finished 7/8 in 4136 s, exit 1:
   SRR15852411 failed md5 three times (the batch copy of `_1`, a fresh `_1`,
   then a fresh `_2`; `integrity.check_sra` drops the mismatching file before
   each retry, so these were three separate downloads). All of them were HTTPS,
   so TLS rules out corruption in transit, and the log has no failed segment,
   only 8 refused connects, which write nothing. The worker gate does not pause
   files mid-download (`batch._worker` passes no pause token), so the
   adaptive controller cannot cause it either. That leaves ENA serving wrong
   bytes for that run for a while, or a bug I have not found. Other tools hit
   md5 mismatches in this gate too (fastq-dl on `SRR15852406_2`, iSeq on three
   3r runs), which fits a server-side cause. The retries ran at 1 or 2
   connections (about 1 MB/s per connection), which is most of the extra
   40 minutes over the fixed arm. **Diagnostic `54917324`**
   (`bench/e3/diag_corrupt.{py,sbatch}`) downloads SRR15852411 four times with
   adaptiSeq's `SegmentedDownloader` and with curl side by side, logs each
   response's ETag/Last-Modified/Content-Range, and compares any bad copy
   block by block with a good one (zero blocks at a segment boundary would
   mean adaptiSeq; scattered garbage or a second ETag would mean ENA). I will
   hold the full run until it reports.
   **While looking, I found and fixed a real adaptiSeq bug (`98f3e56`):** resume
   state is two files, and a `.part.meta` that outlived its `.part` was
   resumed from. The single-connection path never removed `.part.meta`, so if
   a segmented attempt was interrupted, the retry finished on one connection,
   and the md5 check later deleted the file, the next download fetched only the
   segments the old metadata listed as unfinished and left the rest as zeros.
   Segmented FTP had the same flaw and could even return success with no file.
   New tests fail on the old code (`pytest_expanse_54917332`) and the full
   offline suite passes with the fix (`pytest_expanse_54918923`: 180 passed,
   7 skipped). It does not obviously explain the gate failure: the log shows
   no segment that ran out of retries, which is what would leave such metadata
   behind, and it cannot explain the first bad copy. The queued wheel rebuild
   (`54908326`) builds from the checkout, so the full run gets this fix.
   **Diagnostic result (13:07 to 17:00, `diag_corrupt_54917324/`):** 16
   downloads of SRR15852411 (4 passes x 2 files x adaptiSeq's
   `SegmentedDownloader` and curl), all 16 matched ENA's md5. Every response
   carried the same ETag and a 2021 Last-Modified, so ENA serves one copy and
   the md5 in its report is current. The gate's three bad copies were deleted
   with the arm's payload, so the failure cannot be examined directly and was
   not reproduced. My reading: a transient fault on ENA's side or on the
   path, of the same kind as fastq-dl's and iSeq's mismatches in this gate,
   not adaptiSeq. For the paper, report md5 failures per tool from the full
   run as they occur. The adaptiSeq per-connection rate was 0.9 to 2 MB/s
   (2 connections per file), curl's 0.5 to 1 MB/s.
3. Then submit the full run, one repetition per 48 h job (see the timing
   above), chained so that no two overlap:
   ```bash
   cd plans_and_experiments
   export ENV_NAME=adaptiseq_e3_sub E3_ASEQ_WHEEL=$PWD/wheels/adaptiseq-0.1.4-py3-none-any.whl
   export E3_TIMEOUT_3R=10800 E3_TIMEOUT_3B=30000 RESULTS_ROOT=$PWD/e3_submission_expanse
   prev=""
   for r in 1 2 3 4 5; do
       dep=${prev:+--dependency=afterany:$prev}
       prev=$(E3_REP_FIRST=$r REPS=1 sbatch --parsable --export=ALL $dep bench/e3/e3_expanse.sbatch)
   done
   python bench/e3/analyze_submission.py --tsv Expanse=<job1>/e3_results.tsv ... \
       --tsv Expanse=<job5>/e3_results.tsv --outdir paper/numbers
   ```
   The jobs must not overlap (they would share the link), hence the
   dependency. They will probably land on different nodes; ratios are paired
   within a repetition, so that does not bias them, but say it in the methods.
4. Decide what the paper says about the Fabric half. `Node-MICH` did not produce
   a valid run, and the plan allows Expanse only. The manuscript still describes
   two machines in the abstract, methods, Figure 1 legend, and limitations.

---

## Update 2026-10-13, Fabric node `Node-MICH`

The earlier work is committed on `app-notes` (`d59bd0a`) and on the remote.
This session's changes are uncommitted in the working tree; nothing was pushed,
tagged, or published.

**The benchmark was not run here, because this node cannot produce a valid
one.** The gate started, and I stopped it during the second arm. What I measured:

- The node is IPv6-only and reaches the archives through NAT64 (public address
  152.54.14.11; plain IPv4 does not connect). General egress is fast: about
  109 MB/s from NCBI and 38 MB/s from the AWS SRA bucket, single stream.
- To ENA (`ftp.sra.ebi.ac.uk`) each connection gets about 1 MB/s, and the total
  scales with the number of connections: 1.0, 8.8, and 18.5 MB/s with 1, 8, and
  20 parallel `curl` range requests. FTP single stream was 0.3 MB/s. In July on
  `Node-FIU`, single-stream tools got 12 to 16 MB/s on panel 3b.
- About 25 simultaneous TCP connections to ENA are accepted; further ones are
  refused (25 of 40 parallel connects succeeded).
- At 1 MB/s per connection the single-stream arms need about 2 hours for 3r and
  7 hours for 3b, both past the harness timeouts (5400 s and 7200 s). One
  repetition would take over a day, and the result would measure this node's
  per-connection limit, not the tools.

Gate results before I stopped it
(`e3_submission_Node-MICH_gate_20261013_220822/`, one TSV row plus logs):

- The by-hand md5 check passed (5 files, 3 runs, `verify_output.py` agrees).
- Kingfisher exited after 28 s with 5 of 241 runs: its ENA file-report query for
  the sixth run failed (curl exit 35) and it does not retry or continue. See B.
- `adaptiseq-fixed-j20` had 241 MB after 5 minutes, with repeated "Cannot
  connect to host ftp.sra.ebi.ac.uk:443" and connection timeouts.

**adaptiSeq at its defaults fails on this node.** `adaptiseq -i LIST -g` on the
first 30 runs of D1 (2.9 GB) verified no run in 400 s. With
`-j 12 --max-conns-per-host 12` the same list finished 30/30 in 380 s with no
connection errors. So the default of 20 workers runs into the roughly
25-connection allowance when connections are slow and pile up, and the circuit
breaker does not react because it lowers concurrency on 429/503 only, not on
refused connections. This bears on the "default settings" claim and is yours to
weigh: either the controller should back off on refused connections, or the
paper should say the defaults assume a path that is not rate-limited per
connection. I did not change it.

**Recheck on 2026-10-14, after the public IPv4 interface (`enp9s0`,
23.134.232.99) was added: unchanged, and the limit is at EBI, not in the node's
network.** The interface only had a route to 8.8.8.8, so nothing used it. With a
temporary route for EBI's range (193.62.192.0/21 via 23.134.232.97, removed
afterwards) and `curl -4`, ENA gave the same figures as through NAT64: 1.1, 9.4,
and 25.7 MB/s at 1, 8, and 20 connections, and 26 of 60 parallel connects
accepted. `ftp.ebi.ac.uk` gave 1.5 MB/s. Other European servers from this node,
single stream: 27 MB/s (London), 26 (Frankfurt), 23 (FAU), 13 (Oxford). So two
independent source addresses see about 1 MB/s per connection from EBI only. I
cannot tell from here whether EBI applies this to everyone at present or only
to these networks; one `curl` of an ENA file from Expanse or a laptop would
settle it. If Expanse sees the same, the timeouts and the plan's 14-hour
estimate no longer hold anywhere, and the single-stream arms need about 9 hours
per repetition.

**Later on 2026-10-14: IPv4 path forced, at your request.** `enp9s0` is now the
IPv4 default route (`ip route replace default via 23.134.232.97 dev enp9s0`),
and `/etc/gai.conf` prefers IPv4 (full precedence table appended; the original
is `/etc/gai.conf.bak-20261014`). That was not enough: the conda `curl` (8.22,
which Kingfisher and the harness use) still tried the DNS64 address first and
timed out on it intermittently, which is also what ended Kingfisher's run
yesterday. So the NAT64 prefix is now blocked
(`ip -6 route add unreachable 2600:2701:5000:5001::/96`), and every tool falls
back to IPv4 at once. Neither route survives a reboot; both must be re-added
before any further run on this node. Verified with the conda `curl` and
`aria2c`: ENA, the ENA portal, AWS, and NCBI all connect over IPv4 from
23.134.232.99.
(The suggested one-line `gai.conf` change would have dropped glibc's default
table, and the NAT64 prefix here is `2600:2701:5000:5001::/96`, not
`64:ff9b::/96`.)

Effect: the per-connection rate from ENA is the same (1.2, 9.9, 23.9 MB/s at 1,
8, 20 connections), with no loss on the path and a 3 MB receive buffer on our
side, so the limit is on EBI's server. What did change: adaptiSeq at defaults
now completes. The 30-run list finished 30/30 in 283 s with no refused
connections (8 connection timeouts, all retried successfully). Yesterday's
refusals were therefore a property of the shared NAT64 address, not of the
defaults, and numbers from before and after this change are not comparable.

A gate run was started on this path with the timeouts raised so the
single-stream arms can finish (`E3_TIMEOUT_3R=10800 E3_TIMEOUT_3B=30000`): log
`/mnt/nvme0n1/work/gate2.log`, results in the newest
`e3_submission_Node-MICH_gate_*` directory. Expect roughly a day. The raised
timeouts are a change to the protocol; if you keep them, use the same values
on Expanse.

What you need to decide: where to run the Fabric half. Options are a Fabric
site whose path to ENA is not limited like this (I do not know whether
`Node-FIU` was IPv4 or simply a better day; a 20 s check is
`bash /mnt/nvme0n1/work/rng.sh`, which should show well over 1 MB/s at P=1),
or Expanse only, which the plan allows.

Done in this session:

- **Retry fix (decision A's open question).** Confirmed: on an md5 mismatch the
  first retry re-ran the download with the bad file in place, and the engine
  treats a full-size file as "Already complete", so only the second retry was a
  real download. `check_sra` now deletes the mismatching file before the first
  retry (a missing or partial file is still resumed). `adaptiseq/integrity.py`,
  one new test in `tests/test_logs_integrity.py`. This departs from iSeq, which
  keeps the file. Offline tests pass. The live-network tests were not completed
  on this node: they stall on its ENA path, and `test_ena_columns_present`
  failed once when the ENA query came back empty and the code fell back to SRA.
- **0.1.4 wheel and sdist built** from this tree (with the retry fix), `twine
  check` passes: `plans_and_experiments/wheels/`. Wheel sha256
  `a9f9de4045867f4d6273dd5c46f525394cb9bc5c5367a839f2c0a0a801619362`. To keep
  "the same wheel on both machines" true, upload this file to PyPI as it is. If
  you change anything first (for example `authors` in `pyproject.toml`), rebuild
  and use the new file everywhere.
- **Environment on this node:** Miniforge at `/mnt/nvme0n1/work/miniforge3`, env
  `adaptiseq_e3`, exported to `bench/e3/env_adaptiseq_e3.yml`. Versions: iSeq
  1.9.9 (July used 1.9.8), Kingfisher 0.5.0, fastq-dl 4.0.1, sra-tools 3.4.1,
  aria2 1.37.0, Python 3.11.17. `setup_env.sh` now works without environment
  modules.
- **Table 1:** two of the three `?` cells resolved from the installed sources
  (Kingfisher does not resume partial files; pysradb does not md5-check
  downloads). fetchngs rate limiting is still `?`.
- **References:** the Kingfisher, fastq-dl, pysradb, nf-core, and iSeq entries
  are now checked against Crossref, Zenodo, and the projects' citation files,
  with DOIs. Still open: FastBioDL author order (a search result listed Swargo,
  Arifuzzaman, Arslan; the draft has Arslan second), and the archive references.
- `.DS_Store` added to `.gitignore`.

Other things to know:

- This node has 4 cores, not the 8 the manuscript states for the Fabric machine.
- Zenodo lists nf-core/fetchngs 1.13.0 (2026-09-15); Table 1 describes 1.12.0.
- Kingfisher's citation file is for 0.4.1; the benchmark uses 0.5.0.

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
**Update:** the retry weakness was real and is fixed (see the update section):
only one of the retries was a fresh download. That makes a transient bad
transfer less likely to survive, but it does not show what caused the July
failures, so the wording decision still waits on the rerun.

**Update, Expanse gate (job `54902879`, 3r rep 1): two adaptiSeq bugs found
and fixed.** `adaptiseq-fixed-j20` completed 241/241 (354 s), but
`adaptiseq-default` completed 239/241 (577 s, exit 1). The log shows why:

1. ENA's portal answered the filereport query for `SRR22904257` with the
   in-band error "ERROR occurred. Not all results may have been written..."
   (the same transient error that cost Kingfisher and fastq-dl 4 runs each).
   adaptiSeq accepted it, took the error line for a Run, and cached it as
   `SRR22904257.metadata.tsv`, so the accession could never be resolved, even
   in Phase B, which reuses cached metadata.
2. In Phase B (the per-accession md5/convert/merge pass after the batch
   download), the resulting `DownloadError` ended the whole loop at the fifth
   accession. So no later accession was md5-checked or retried. The second lost
   run is presumably a file that failed in the batch phase and that Phase B
   would have retried; the payload is deleted, so I cannot name it. iSeq runs
   each accession in a subshell, so there one bad accession does not stop the
   list; adaptiSeq diverged from iSeq here.

Fixes (in `adaptiseq/metadata.py`, `core.py`, `batch.py`; tests in
`tests/test_list_resilience.py`; README 0.1.4 notes updated):
- An ENA answer containing the error line is retried (4 tries, 2/4/8 s apart),
  then treated like an empty answer (SRA fallback). A cached metadata file
  containing it is fetched again, in both the batch resolver and Phase B.
- In a list, an `AdaptiSeqError` for one accession is reported, written to
  `fail.log`, `ctx.failed` is set (exit 1), and the loop continues. A single
  accession still raises as before.

This changes the wheel again (new sha256). The gate's remaining adaptiSeq arms
(3b) run the old wheel; the full run must use the rebuilt one. Test job
`54908172` (`bench/e3/pytest_expanse.sbatch`, output `pytest_expanse_54908172/`)
ran the suite from the checkout: all pass, offline (7 live tests skipped) and
with network (1 skipped, live Aspera). Committed as `41ac3c9`. The wheel is
rebuilt after the gate ends, because rebuilding reinstalls into the env the
gate is using: setup job `54908326` is queued with `--dependency=afterany:54902879`
and writes `setup_expanse_54908326/` (new `wheel_sha256.txt`, tests, README
check).

For decision A: with the fix, a transient ENA error costs adaptiSeq nothing
(it retries); without it, adaptiSeq is no better than the other tools on this.
The full run will show whether 241/241 holds.

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

**Update:** the gate run points at a different cause for Kingfisher's partial
lists. It did not fall back at all: one failed ENA file-report query ended the
whole run (5 of 241 runs, 28 s). The 93 and 153 unfinished runs in July fit an
abort partway through the list better than per-run fallbacks. If that holds on
Expanse, `runs_present_unverified` will be near zero and option (1) is enough,
but the paper should then say that Kingfisher stops at the first failed
metadata query, which is a fairer description than "drops runs".

**Update, Expanse gate (job `54902879`, 3r rep 1):** Kingfisher did not abort
this time. It finished all 241 runs in 2649 s (exit 0): 237 md5-verified
(including all 40 three-file runs), 4 `runs_present_unverified` (`SRR22904287`,
`SRR22904300`, `SRR22904432`, `SRR22904448`). For each of the four, Kingfisher's
ENA query returned no URLs ("No ENA FTP download URLs found ... cannot
continue"), so it fell back to `aws-http` and recompressed from SRA. ENA does
have FASTQ for them: I queried the ENA file report for two of them afterwards
and both list a `fastq_ftp` and `fastq_md5`. So the empty answer was transient
and Kingfisher does not retry the query. The count is small (4 of 241, 1.7%),
so option (1) is enough: count only md5 matches and state in the paper that
4 runs (median over reps, from the full run) were obtained by Kingfisher from SRA
after a failed ENA query and could not be checked against ENA's checksums.
Kingfisher's three-file handling is fine; it is the Kingfisher completeness
number that the paper should explain this way.

**fastq-dl has the same problem (same gate, 3r rep 1).** fastq-dl took 2395 s
and verified 237 of 241 runs (39 of the 40 three-file runs); exit 0, nothing
partial. The 4 missing runs (`SRR22904276`, `SRR22904351`, `SRR22904370`,
`SRR22904422`) are 4 different runs from Kingfisher's. For each one, ENA's
search API answered "ERROR occurred. Not all results may have been written"
instead of the record, and fastq-dl 4.0.1 crashed with `KeyError: 'fastq_ftp'`
(no retry, no fallback). The harness calls fastq-dl once per accession, so only
that run was lost. adaptiSeq completed all 241 in the same window. So ENA's
metadata service fails transiently about 1 query in 60 at present; tools that
do not retry lose those runs. For the paper: describe the shortfall of both
tools this way (transient ENA metadata errors, no retry), with the median count
from the full run, rather than as a failure on particular runs.

### C. The gate has not been run on the benchmark machines

The plan's gate ("one rep of both panels, then check") needs about 2.7 hours and
34 GB on the benchmark machines. I ran the equivalent on the 3-run smoke dataset
on this laptop instead. See Step 2 below for what that did and did not cover.

**Update:** started on `Node-MICH` and stopped; that node's path to ENA rules it
out (see the update section). The gate is still to be run on Expanse and on a
usable Fabric node.

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
   co-authors, ORCIDs, and affiliations. I do not have them. `authors` in
   `pyproject.toml` now has the same name (Expanse update); co-authors there are
   also yours. `LICENSE` still reads "Copyright (c) 2026 swargo98".
2. ~~**FastBioDL's licence.**~~ Done (Expanse update): FastBioDL is MIT and its
   notice is in `LICENSE`.
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
4. ~~**README comparison table.**~~ Done (Expanse update): the three cells are
   corrected. Read the Kingfisher and pysradb rows, since the column definitions
   are yours.

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

1. **Run the gate, then the full benchmark, on Expanse and Fabric.** On
   Expanse the gate is running (job `54902879`; Expanse update) and
   the full run follows it, split across jobs. `Node-MICH` is unusable. The
   14-hour estimate below is from July; with ENA's per-connection limit expect
   about 12 hours per repetition. The commands below are the original ones; on
   Expanse use those in the Expanse update, which set the env name, timeouts,
   and results directory. With the wheel in
   `wheels/` (or after 0.1.4 is on PyPI), from `plans_and_experiments/` on each
   machine. On a fresh Fabric node, install Miniforge first and put `conda` on
   `PATH`; set `E3_WORK` to the NVMe, since the default is `/tmp`:
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
   rebuild the environment, and use the same choice on both machines. A fresh
   environment today gets iSeq 1.9.9 (this node did), so keeping 1.9.8 on Fabric
   means pinning it in `setup_env.sh`. **Decided on Expanse:** a new env
   `adaptiseq_e3_sub` built from the Fabric export, so both machines have the
   same builds (iSeq 1.9.9); the July env is kept as it was.
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
2. ~~**One cell in Table 1 is still marked `?`**~~ Resolved from the fetchngs
   source (Expanse update): parallel resolution, no request-rate cap. fetchngs
   was still not installed or run; its row describes 1.13.0 from the source and
   documentation at that tag.
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
2. ~~**References.**~~ Done (Expanse update): every entry is verified, the
   archive references are added, and fetchngs has its author list.
3. **Things only you know:** co-authors and affiliations, funding, the
   corresponding author, and the description of the two machines (I wrote "128-core
   Expanse node" and "8-core FABRIC virtual machine" from the result files;
   `Node-MICH` had 4 cores, and the gate writes the Expanse node's hardware to
   `machine.txt`). The ACCESS/Expanse and FABRIC acknowledgement wording is now
   drafted from the programs' pages; confirm the allocation number.
4. ~~**Two factual statements in the Introduction.**~~ Checked (Expanse
   update): the first holds, the second was wrong and is rewritten.
5. **Convert to the journal's format** (OUP template, 4 pages) once the numbers
   are in. The draft is Markdown.

---

## Checklist from the plan

- [x] iSeq and FastBioDL credited in `LICENSE` and README. In the paper: drafted.
- [ ] `pip install adaptiseq==0.1.4` in a fresh environment runs the README
      example. Verified with the wheel built on the Fabric node, and again on
      Expanse for the rebuilt wheel (sha256 `40bbfd17...`, then `2a0a6f5c...`;
      CLI and API both 3/3 runs md5-verified,
      `setup_expanse_54908326/readme_example.txt`).
      Repeat from PyPI after release.
- [ ] Every number in the text comes from the new TSVs via the script. The
      script and placeholders are in place; the TSVs do not exist yet.
- [ ] Zenodo DOI resolves. Needs the release.
- [ ] Accession lists and md5 manifests are public. They are in
      `plans_and_experiments/datasets/` on this branch and on `e8`; nothing has
      been pushed. Decide between the `e8` branch and a small separate
      repository, then put the URL and commit into the manuscript.
- [ ] **conda / Bioconda package (not started; added 2026-10-18 at the user's request).**
      What exists: `environment.yml` (a dev environment: external tools plus
      `pip install -e .`), and `docs/installation.md` says "A dedicated bioconda
      package is **TBD**"; the manuscript (Limitations) says "distributed through
      PyPI and not yet through Bioconda". There is no recipe anywhere. To do:
      1. Release to PyPI first (Bioconda recipes build from the PyPI sdist;
         **note PyPI has only 0.1.3**: 0.1.4 to 0.1.7 were built locally and
         never uploaded). Needs the user's go-ahead.
      2. Write `recipes/adaptiseq/meta.yaml`: `noarch: python`, source = the
         PyPI sdist URL + sha256, `script: {{ PYTHON }} -m pip install . -vv
         --no-deps`, `entry_points: adaptiseq = adaptiseq.cli:main`; run deps
         `python >=3.8`, `aiohttp >=3.8`, `aioftp >=0.21`, `numpy >=1.21`,
         `wget`, `pigz`, `sra-tools >=2.11.0` (Aspera optional, so not a hard
         dependency); `test: commands: adaptiseq --version, adaptiseq --help`
         and `imports: adaptiseq`.
      3. Check it locally with `bioconda-utils build` (or `conda build` +
         `conda-forge`/`bioconda` channels) on a compute node, then open a PR
         to `bioconda/bioconda-recipes`; after it is merged, update
         `docs/installation.md`, the README and the manuscript sentence.

## Housekeeping

- `.DS_Store` is now in `.gitignore`.
- On `Node-MICH`, everything I installed or downloaded is under
  `/mnt/nvme0n1/work/` (Miniforge, logs, `rng.sh`); payload scratch is empty.
- To reproduce the SRA-only check or the smoke run locally you need `wget`,
  `sra-tools`, and `pigz` on `PATH`; this machine has none of them outside a
  temporary environment I created in the session scratch directory.
