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

**State of the benchmark: setup done, gate running.** Two Slurm jobs:

| Job | What | State |
|---|---|---|
| `54902878` `adaptiseq_setup` (`shared`, 8 cores, 2 h) | env, wheel, tests, README check, ENA probe | **COMPLETED** 20:40 to 21:20 PDT on `exp-1-44`, all steps passed (below) |
| `54902879` `adaptiseq_gate` (`compute`, exclusive, 20 h limit) | the gate: one rep of 3r + 3b | **RUNNING** since 21:20 PDT on `exp-5-53` (AMD EPYC 7742, 128 cores, 251 GB, 870 GB free NVMe) |

Both jobs waited about 3 h in the queue because of a Lustre fault on Expanse
(about 600 compute nodes draining, "Lustre df is hung"). The full five-rep run is
not submitted; it waits on the gate (see "What you need to do next").

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
  The gate's `versions.txt` shows the same wheel hash, so the benchmark is
  running exactly these files. Upload these two, unchanged, if you release.
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
3. Then submit the full run, split so each job fits in 48 h. With the gate's
   wall times `T3r` and `T3b` (sum over the six arms), one job holds
   `48 h / (T3r + T3b)` repetitions. If that is 3, for example:
   ```bash
   cd plans_and_experiments
   export ENV_NAME=adaptiseq_e3_sub E3_ASEQ_WHEEL=$PWD/wheels/adaptiseq-0.1.4-py3-none-any.whl
   export E3_TIMEOUT_3R=10800 E3_TIMEOUT_3B=30000 RESULTS_ROOT=$PWD/e3_submission_expanse
   j1=$(REPS=3 sbatch --parsable --export=ALL bench/e3/e3_expanse.sbatch)
   E3_REP_FIRST=4 REPS=2 sbatch --export=ALL --dependency=afterany:$j1 bench/e3/e3_expanse.sbatch
   python bench/e3/analyze_submission.py --tsv Expanse=<job1>/e3_results.tsv \
       --tsv Expanse=<job2>/e3_results.tsv --outdir paper/numbers
   ```
   The two jobs must not overlap (they would share the link), hence the
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
      Expanse for the rebuilt wheel (sha256 `40bbfd17...`; CLI and API both
      3/3 runs md5-verified, `setup_expanse_54902878/readme_example.txt`).
      Repeat from PyPI after release.
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
