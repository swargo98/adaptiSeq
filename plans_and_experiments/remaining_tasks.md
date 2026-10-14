# Remaining tasks after executing MINIMAL_SUBMISSION_PLAN.md

Written 2026-10-13 on branch `app-notes`. Nothing has been committed, pushed,
tagged, or published; every change is in the working tree for you to review.

The plan has four steps. Steps 1 and 3 are done as far as they can be without
your accounts or the two benchmark machines. Step 2 is prepared and smoke-tested
but not run. Step 4 is drafted with placeholders where results go.

Three things I found along the way change what the paper can claim. They are in
"Decisions needed before the benchmark" and should be read first.

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

1. **Run the gate, then the full benchmark, on Expanse and Fabric.** Not done:
   `Node-MICH` is unusable for it (update section) and I have no access to
   Expanse. The run needs about 14 hours per machine. With the wheel in
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
   means pinning it in `setup_env.sh`.
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
2. **One cell in Table 1 is still marked `?`** (fetchngs rate limiting).
   fetchngs was not installed or run; its row comes from its documentation.
   The Kingfisher and pysradb cells are resolved from the installed sources.
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
2. **References.** The Kingfisher, fastq-dl, pysradb, nf-core, and iSeq entries
   are checked and carry DOIs. Still to do: confirm the FastBioDL author order,
   take the fetchngs author list from its Zenodo record, and add the archive
   references (SRA, ENA, DDBJ, GSA).
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

- `.DS_Store` is now in `.gitignore`.
- On `Node-MICH`, everything I installed or downloaded is under
  `/mnt/nvme0n1/work/` (Miniforge, logs, `rng.sh`); payload scratch is empty.
- To reproduce the SRA-only check or the smoke run locally you need `wget`,
  `sra-tools`, and `pigz` on `PATH`; this machine has none of them outside a
  temporary environment I created in the session scratch directory.
