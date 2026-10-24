# Remaining tasks (open items only)

Updated 2026-10-23. What has been done, with every job, result row and decision, is in
`progress_log.md` (sections newest first). This file lists only what is still open. When an item is
done, add a dated note to `progress_log.md` and delete it here.

---

## 1. In progress: round 3, then the paper benchmark (mine)

The user's instruction (2026-10-22): "make these fixes on 0.1.12 and test them. I am inclined to topdown
as default. Proceed to run all the remaining tasks with topdown as default if topdown still leads after
the fixes."
**Superseded 2026-10-23 19:20 (user):** "lets provide 3 criterions. the previous one, current one, and mean
connection. Let the runs finish, then we'll decide who'll be the default." Then: "The second rule is 'the best
worst case'". So round 3 no longer triggers the chain by itself: report the three rankings and wait for the
user's choice of default.

1. **Round 3 on 0.1.12** (wheel `0c5e6a82`, env `adaptiseq_e3_sub`, results `e3_round3_expanse/`).
   Protocol and the "topdown still leads" test were fixed before the data: `progress_log.md` section 1,
   "Round 3 protocol". Reps: `55203207` done (01:06 10-23, all 42 arm-cases verified); `55203208`
   running (4r, 4b, 4s, 4g recorded); `55203209` queued (`afterany`). Record rows per panel in
   `progress_log.md` section 1 (after the last "Rep N" table), then score from `plans_and_experiments/`:
   `python bench/e3/score_round2.py e3_round3_expanse/e3_*/e3_results.tsv`. The output ends with the **three
   criteria** to report: (1) as written (any unverified run disqualifies); (2) best worst case (highest ratio to
   the fastest arm in any one case, lowest first; a timeout counted at the limit; a run missing or unverified
   without a timeout ranks last); (3) mean connections, fewest first. Say which arms are adaptive. The 19:00
   amendment (`--timeout-censored`, a timeout does not disqualify) was replaced by criterion 2; report it only
   if asked. **Then wait for the user to choose the default.**
2. **After the user chooses the default:** if topdown, no code change (`Options.controller` is `None`, so
   topdown); otherwise change the default in code, add a test, rebuild `adaptiseq_e3_sub` (allowed once round 3
   has ended) and check the wheel. Run the paper's 5-rep chain on 0.1.12 (or the rebuilt version), one rep per
   48 h job, chained so no two overlap (about 24.5 h each, about 120 h in all):
   ```bash
   cd plans_and_experiments
   export ENV_NAME=adaptiseq_e3_sub E3_ASEQ_WHEEL=$PWD/wheels/adaptiseq-0.1.12-py3-none-any.whl
   export ARM_SET=submission PANELS="3r 3b" E3_TIMEOUT_3R=10800 E3_TIMEOUT_3B=30000
   export RESULTS_ROOT=$PWD/e3_submission_0.1.12_expanse
   prev=""
   for r in 1 2 3 4 5; do
       dep=${prev:+--dependency=afterany:$prev}
       prev=$(E3_REP_FIRST=$r REPS=1 sbatch --parsable --export=ALL --exclude=exp-10-14,exp-3-51 $dep bench/e3/e3_expanse.sbatch)
   done
   ```
   Record rows per rep as for the tournament; check `check_run.txt` after each rep.
3. **Numbers and figure** once the chain is done:
   `python bench/e3/analyze_submission.py --tsv Expanse=<rep dir>/e3_results.tsv ... --outdir paper/numbers`
   (Expanse only unless the user decides on a Fabric half, item 3.3).
4. **Fill the manuscript placeholders** (`[[...]]` in `paper/manuscript_draft.md`) from `paper/numbers/`;
   the table at the end of the draft maps each to a file and field. Mark anything that depends on an
   open decision in section 3.
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
- **Optional:** block-by-block corruption diagnostic of ENA's bad copies (`diag_batch` with
  `METHODS=curl-ftp,curl-https,aseq-https ROUNDS=1`).
- **Old harness scripts** `submit_e3.sh` and `status.sh` still assume the six-panel layout.

## 3. The user's decisions and actions (not mine)

1. **Decision A: the completion claim.** Whether the paper may say adaptiSeq downloads lists
   "completely" depends on the 0.1.12 chain's results (`progress_log.md` section 10, A).
2. **Decision B: runs other tools fetched from SRA** (unverifiable against ENA's md5). Recommended:
   count only md5 matches and report the unverified count separately, with the cause (transient ENA
   metadata errors that Kingfisher and fastq-dl do not retry). Section 10, B.
3. **The Fabric half.** `Node-MICH` cannot produce a valid run (about 1 MB/s per connection from EBI);
   the plan allows Expanse only, but the manuscript still describes two machines (abstract, methods,
   Figure 1 legend, limitations). If Fabric stays: find a node with a usable ENA path, re-add the IPv4
   routes on `Node-MICH` after any reboot (section 9), and use the same wheel and timeouts as Expanse.
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
