# Remaining tasks (open items only)

Updated 2026-11-01. What has been done, with every job, result row and decision, is in
`progress_log.md` (sections newest first). This file lists only what is still open. When an item is
done, add a dated note to `progress_log.md` and delete it here.

---

## 1. In progress: round 3, then the paper benchmark (mine)

The user's instruction (2026-10-22): "make these fixes on 0.1.12 and test them. I am inclined to topdown
as default. Proceed to run all the remaining tasks with topdown as default if topdown still leads after
the fixes."
**Superseded 2026-10-23 19:20 (user):** "lets provide 3 criterions. the previous one, current one, and mean
connection. Let the runs finish, then we'll decide who'll be the default." Then: "The second rule is 'the best
worst case'", and added a fourth, the mean ratio to the fastest. So round 3 no longer triggers the chain by itself: report the three rankings and wait for the
user's choice of default.

1. **Round 3: done; default chosen 10-26 (user): topdown**, already the default, so no code change or rebuild
   (`progress_log.md` section 1, "Default chosen"). **Keep `budget`** (user, 10-26): "keep 'budget' as a separate
   option focused on minimizing connections. Will include it in the discussions later." Do not remove or
   rename it; in the paper's discussion, present it as the fewest-connections option (round 3 mean
   connections 13.1, second only to knee 12.8; mean ratio 1.84). Its description in `options.py`, `cli.py`
   and the README still says "candidate under evaluation"; reword it when the user takes up the discussion.
2. **Done 11-01: the paper's 5-rep chain on Expanse** (0.1.12, wheel `0c5e6a82`, env `adaptiseq_e3_sub`, jobs
   `55290250`-`55290254`, results `e3_submission_0.1.12_expanse/`). Reps took 30.6, 29.2, 30.9, 28.3 and 9.2 h;
   CHECK FAIL on reps 1-4 (TIMEOUTs, all in other tools), PASS on rep 5. Rows in `progress_log.md` section 1.
   Submission commands are in `progress_log.md` section 1 and in this file's history. Delete this item when
   item 4 starts.
3. **Next: the Fabric half, five reps on one Fabric node** (user, 11-01: start the analysis after the Fabric
   results). Same protocol as Expanse, so the two machines can be compared row for row:
   - **Build:** the same wheel, `wheels/adaptiseq-0.1.12-py3-none-any.whl`, sha256 `0c5e6a82...` (check it
     before installing). Env from `bench/e3/env_adaptiseq_e3_sub.yml`:
     `ENV_NAME=adaptiseq_e3_sub ENV_FILE=bench/e3/env_adaptiseq_e3_sub.yml E3_ASEQ_WHEEL=<wheel> bash bench/e3/setup_env.sh`.
     The versions must match Expanse: iSeq 1.9.9, Kingfisher 0.5.0, fastq-dl 4.0.1, Python 3.11.17.
   - **Settings:** `ARM_SET=submission PANELS="3r 3b" E3_TIMEOUT_3R=10800 E3_TIMEOUT_3B=30000`, default seed
     (20261013, so rep k runs the arms in Expanse's order). Payload on a local disk with 40 GB free (`E3_WORK`).
   - **Driver:** `bench/e3/run_submission.sh` (no Slurm). Before the first rep, bring it in line with
     `e3_expanse.sbatch`, as a separate commit: activate `${ENV_NAME:-adaptiseq_e3}` instead of the fixed
     `adaptiseq_e3`; add the ENA link probe (1/8/20 connections, `link_probe.txt`); pass `--rep-first` to
     `check_run.py`. Results go to `e3_submission_0.1.12_fabric/<rep dir>`.
   - **One rep per invocation**, run in sequence inside `tmux` or `nohup`
     (`E3_REP_FIRST=$r REPS=1 bash bench/e3/run_submission.sh full`), so a crash or reboot costs one rep.
     A gate rep first is optional: rep 1 runs the same gates.
   - **Before rep 1:** the link probe by hand. Expanse saw 0.5-2.1 MB/s per ENA connection at P=1 and
     `Node-MICH` saw 1.0-1.2 (`progress_log.md` section 9), so a node in that range is comparable. Below
     0.5 MB/s, or if more than about 25 connections are refused, stop and report to the user. On `Node-MICH`,
     re-add the IPv4 default route and the NAT64 block after any reboot (section 9).
   - **Expect** 10-31 h per rep (Expanse's range), five to six days in all.
   - **Record** each arm as on Expanse: a row in a "Fabric chain rows" table in `progress_log.md` section 1
     (same columns, ratio to the fastest arm with every run verified, connections from `tools/check_panel.sh`),
     commit, push. Package each finished rep: gzip logs over 20 MB, commit the `.log.gz` only.
   - **Push** to a separate branch, `fabric-app-notes`, not `expanse-app-notes`, so the two machines'
     sessions never push the same branch; merge into `expanse-app-notes` once both are done.
   - **Don't** change adaptiSeq or the wheel, or the timeouts, mid-run.
4. **Then the analysis and the manuscript, per `analysis_plan.md`:** checks, the script changes
   (`--reference`, completeness and connection tables, the stacked completion panel), numbers for both
   machines into `paper/numbers/`, a report to the user, then the placeholders and the rewording to the
   "whole system" framing (user, 11-01).
5. **Concurrency benchmark: more connections do not always help** (user, 2026-10-23; not done before). A
   medium workload, preferably: a new ENA list between 4r and 4b, e.g. 40-60 runs of 0.2-1 GB (20-30 GB in
   all), with an md5 manifest in `datasets/`. Arms: fixed `-j` 1, 2, 4, 8, 16, 32, 64, 128, plus the chosen
   default for reference; lift the host cap (`--max-conns-per-host`) on the fixed arms so the increase is
   really blind. At least 3 reps, arm order shuffled per rep, one job per rep on one node. Report wall time,
   MB/s, mean/max connections, md5 re-fetches, refused connects, cut-short responses, CPU and memory per
   arm; plot throughput against connections. Repeat on GSA and NCBI if time allows (their limits differ).
   Existing hints only, not a designed test: the fixed-j sweep (`progress_log.md` section 5) had j32 faster
   than j64 on 3jr rep 1 (163 vs 235 s) and on 3jb rep 2 (805 vs 1105 s), and ENA refuses connections beyond
   about 25 at times (section 1, 0.1.12 check).
6. **Full factorial benchmark** (user, 2026-10-23): every method x workload x transfer protocol x source,
   leaving out combinations that cannot exist.
   - Methods: topdown, bottomup, budget, greedy, knee (adaptive) and fixed-j20, fixed-j64.
   - Workloads: many small files (4r-like), few large (4b-like), medium (item 5's list), mixed (4m-like).
   - Protocol x source: ENA {HTTPS, FTP (`-r ftp`), Aspera (`-a`)}; GSA {HTTPS, FTP, Aspera}; NCBI SRA {HTTPS}.
     GEO and DDBJ accessions resolve to ENA or SRA, so they are accession types, not sources (add as extra
     rows only if wanted).
   - Not possible, leave out: NCBI x FTP (no FTP path in the code), NCBI x Aspera (`-a` falls back to HTTPS,
     `resolve.py`; do not label it Aspera). Check first: Aspera uses its own pool controller (`aspera.py`), so
     the five segmented controllers and `-j` may not apply to Aspera cells; if not, Aspera is one method
     (its controller) plus fixed counts. Needs a real `ascp` on Expanse (`bench/setup_real_ascp.sh`) and the
     Aspera ports reachable from compute nodes. `-r ftp` stalls at ENA (section 2), so expect timeouts there.
   - Size: up to 7 methods x 4 workloads x 7 protocol-source pairs = 196 cells per rep, a day or more each;
     3 reps. Pilot one rep on the medium workload first and size the rest from it. `run_e3.sh` needs a
     protocol axis in its arm definitions. One job at a time per source (jobs at the same archive interfere).
     Not blocking the paper.

## 2. Engineering follow-ups (not blocking the paper)

- **knee settles low when ENA is slow** (round 3 rep 1: 4r 3.1 mean connections, 4402 s; 4g never above
  8). Candidate only, not the default. Its phase-1 keep check also uses the old budget
  (`used2 >= 0.8 * budget`, `batch.py` knee code).
- **A per-source connection policy** (few connections on NCBI, many and early on ENA, held through GSA's
  cut streams): the one pattern that held across round 2 (`progress_log.md` section 2, "Routing"). A
  candidate for a later round with more reps, not a router over today's controllers.
- **`-r ftp` stalls at ENA**: add a docs note, or fall back to HTTPS.
- **20 workers on ~3 connections for 10 min** (paper chain rep 5, 3r, default arm; `progress_log.md` section 1,
  "Rep 5 default on 3r"): 403s on single-connection attempts, then the pool stayed at ~3 to one ENA address while
  topdown still read 20 workers. Re-run 3r once with `ASEQ_CLI=$PWD/bench/e3/aseq_info.sh` (INFO logs: host cap,
  refusals, `HostGuard` waits) to see which layer held it. Same 0.1.12 build, so it can run after the chain.
- **One failed HTTPS probe sends a whole list to FTP under `-r auto`** (paper chain rep 2, 3r, default arm: all
  353 files on segmented FTP, 2927 s at 3.1 mean connections against fixed-j20's 1132 s on HTTPS;
  `progress_log.md` section 1, "Rep 2 default on segmented FTP"). Again on rep 5 3b: all 16 files on FTP, 3129 s at 1.7 mean connections, 62 segments reset by peer. `Seam._select_transport` caches the per-host
  verdict for the whole run after one probe. Candidates: retry the HTTPS range probe before choosing FTP, re-probe
  after N files or on FTP errors, and log why the probe failed. A code change means a new version, so not during the
  0.1.12 chain; the user decides whether it goes into the paper's build.
- **Optional:** block-by-block corruption diagnostic of ENA's bad copies (`diag_batch` with
  `METHODS=curl-ftp,curl-https,aseq-https ROUNDS=1`).
- **Old harness scripts** `submit_e3.sh` and `status.sh` still assume the six-panel layout.

## 3. The user's decisions and actions (not mine)

1. **Decision A: the completion claim.** Whether the paper may say adaptiSeq downloads lists
   "completely" depends on the 0.1.12 chain's results (`progress_log.md` section 10, A).
   On Expanse both adaptiSeq arms exited 1 and named the run every time a 3r run was missing (one run, in reps
   2, 3 and 5); no adaptiSeq row was incomplete with exit 0. Recommended wording: "every file is md5-verified
   or reported as failed" (`analysis_plan.md` section 1).
2. **Decision B: runs other tools fetched from SRA** (unverifiable against ENA's md5). Recommended:
   count only md5 matches and report the unverified count separately, with the cause (transient ENA
   metadata errors that Kingfisher and fastq-dl do not retry). Section 10, B.
3. **The Fabric half: decided 11-01, run it** (section 1, item 3). Still yours: the node, if `Node-MICH`
   is not the one; the manuscript's Fabric machine description (cores, network) once the node is known.
4. **Release:** PyPI has only 0.1.3; 0.1.4 to 0.1.12 are local wheels. Order: merge to `main`, enable
   Zenodo's GitHub integration, `python -m build && twine check dist/* && twine upload dist/*`, tag and
   release on GitHub, then put the DOI and date into `CITATION.cff`, README and manuscript.
5. **Bioconda** (after PyPI): recipe plan in `progress_log.md` section 10, checklist.
6. **Publishing the accession lists and md5 manifests** (`datasets/`): `e8` branch or a separate
   repository; then the URL and commit go into the manuscript.
7. **Merging `origin/app-notes` `6ae2fd3`**: its ENA error-body fix conflicts with ours in
   `metadata.py`, `batch.py`, `core.py`; keep one (ours has the tests).
8. **Authorship and metadata:** co-authors, ORCIDs, affiliations, funding, corresponding author
   (`CITATION.cff`, `pyproject.toml`, manuscript); `LICENSE` reads "Copyright (c) 2026 swargo98".
9. **Allocation number** in the acknowledgements: `TG-CIS250262` (what `expanse-client` reports) or
   `CIS250262` (what the draft says); whether the FABRIC sentence stays.
10. **Paper wording on iSeq 1.9.9:** it can no longer download from GSA (exits 0 with no data) or GEO
    (archive browser checks); Table 1 needs a dated note. 1.9.9 handles three-file runs, so the
    Introduction's "correct handling of three-file runs" and the Fig. 1c legend and abstract need
    rewording, unless iSeq 1.9.8 is benchmarked instead (the July env has it). iSeq's retry counter is
    never reset (worth a clause if its failures are discussed).
11. **Read the Kingfisher and pysradb rows** of the README comparison table and Table 1 (they describe
    other tools; the column definitions are the user's). Kingfisher's citation file is for 0.4.1; the
    benchmark uses 0.5.0. Replace the FastBioDL arXiv citation if a PDSW version has a DOI.
12. **Journal format:** convert the Markdown draft to the OUP template (4 pages) once the numbers are in.
13. **Delete `/home/rswargo/adaptiseq_oldtree_check`** if wanted (a safety check blocked me).

## 4. Checklist from the plan (unchecked items)

- [ ] `pip install adaptiseq==<release>` in a fresh environment runs the README example (verified from
      local wheels on every build; repeat from PyPI after release).
- [ ] Every number in the text comes from the new TSVs via the script (waits on section 1).
- [ ] Zenodo DOI resolves (waits on the release).
- [ ] Accession lists and md5 manifests are public (item 3.6).
- [ ] conda / Bioconda package (item 3.5).
