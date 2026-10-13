# adaptiSeq: pre-submission plan (Bioinformatics, Application Note)

Status: draft, 2026-10-13. Supersedes the "what to claim" parts of
`EXPERIMENT_PLAN_adaptiseq.md`; the experiment protocols there remain the
reference where this document does not override them.

Target format (OUP author guidelines): Application Note, up to 4 journal pages
(approx. 2,600 words, or 2,000 words plus one figure). Plan for one multi-panel
figure, one table, and a Supplementary document. Abstract in the journal's
structured format (Motivation / Results / Availability and implementation /
Contact / Supplementary information).

---

## 0. Target paper (what the evidence must support)

**Thesis.** adaptiSeq is an importable Python library and CLI that acquires
public sequencing data for *lists* of accessions across ENA/SRA/DDBJ/GSA/GEO
**completely** (strict superset of runs completed by iSeq, Kingfisher, fastq-dl),
**faster** in batch (parallel, per-endpoint rate-limited resolution plus a
parallel segmented download pool), and **safely** (md5-verified, resumable,
never-truncate, server-etiquette compliant).

**Claims, ranked, with the experiment that must support each:**

| # | Claim | Evidence | Status today |
|---|-------|----------|--------------|
| K1 | Completes a strict superset of runs; md5-verified | E7a/E7e at scale, two machines | Strong but small (241 runs, 1 machine, 2 reps) |
| K2 | Batch throughput: X-fold vs each competitor **in its best configuration**, default settings for adaptiSeq | E3 rerun (3a, 3b), two machines | Strong direction; competitor configs and arm selection need fixing |
| K3 | Resolution is parallel yet never exceeds per-endpoint rate caps | E10 rerun with batch-mode competitors; 10c as labelled simulation | Good; competitor protocol is a strawman |
| K4 | Adaptive mode makes `-j` a safe upper bound: avoids the collapse that the same fixed `-j` suffers under throttling/over-provisioning | E3 existing climb-j40 vs fixed-j40, plus new E4b | Supported by existing data (see §3.4); not yet framed this way |
| K5 | Library API: values and typed exceptions, usable inside pipelines | E6 listing + Snakemake example | Not done (cheap) |
| K6 | Modest resource envelope (~60 MB RSS) | E8 | Done; supplementary |

**Claims to drop or demote.** "Adaptive beats the best fixed setting"; "14x to
19x faster than iSeq" (best-of-arms vs stock iSeq); "resolution overlaps
transfer" (not implemented, `core.py:380`); adaptive Aspera as a speed result
(E5: adaptive 14 MB/s vs fixed j4/j8 34 MB/s, n = 2).

**Figure 1 (single figure, four panels).**
(a) Architecture: resolve (rate-limited, multi-DB chain) -> batch pool ->
segmented engine -> verify/convert/merge; Python API on top.
(b) Batch throughput, 3a and 3b, Fabric and Expanse: adaptiSeq default vs each
competitor at best config; points = reps, bar = median, annotated paired ratio.
(c) Runs completed per tool on the reliability corpus, stratified by run layout
(1-, 2-, 3-file runs) and database.
(d) Over-provisioning robustness: fixed `-j 40` vs adaptive `-j 40` vs
fixed `-j 20` (K4).

**Table 1.** Feature matrix (E1), every cell verified by a command, with tool
versions.

---

## 1. Phase A: decisions to make first (blocking everything else)

Make these in writing (commit to this file) before any rerun. They are the
pre-registration.

**A1. Default adaptive controller.** The shipped `--adaptive` uses `legacy`;
`climb` is reachable only via `ASEQ_ADAPTIVE_MODE` (`batch.py:142`) and was
benchmarked with a non-default `ASEQ_PROBE_WINDOW=8`. Legacy lost to
`fixed-j20` in nearly every panel. Decide one of:

- **A1-a (recommended):** promote `climb` to the default adaptive mode, expose it
  as a real CLI flag (`--adaptive-mode {climb,legacy}`), make its tuned probe
  window the default, keep `legacy` selectable. Default `-j` cap = 20.
- A1-b: default to fixed `-j 20`, adaptive opt-in. Honest, but awkward for a tool
  named adaptiSeq.

**A2. The adaptive claim.** Adopt K4 (robustness to over-provisioning), not
"faster than the best fixed". Existing medians already support it:

| panel | fixed-j40 | adaptive(climb)-j40 | fixed-j20 |
|---|---|---|---|
| 3a Fabric | 6.8 | 31.0 | 35.4 |
| 3r Fabric | 9.7 | 39.4 | 70.0 |
| 3r Expanse | 7.4 | 49.8 | 66.9 |

That is a 4x to 7x protection against a bad cap, while still below a good fixed
cap. Say both halves.

**A3. Competitor set and their best configuration.** Freeze versions.

| tool | main-figure invocation (best effort, same output format) | notes |
|---|---|---|
| iSeq | `iseq -i LIST -g -p 8 -o .` | primary iSeq baseline; stock `iseq -g` kept as a secondary arm |
| Kingfisher | `kingfisher get --run-identifiers-list LIST -m ena-ftp aws-http prefetch --download-threads 8 --check-md5sums -f fastq.gz` | method *chain*, not `ena-ftp` only (`run_e3.sh:87`); confirm flags against 0.5.x help |
| fastq-dl | `fastq-dl --accession ... --cpus 8` (or its list mode) | check retry option and use it |
| nf-core/fetchngs | optional; via Singularity on Expanse | reviewers in genomics will ask; include if setup cost is < 1 day |
| aria2c | not in the batch figure (no resolver); single-file note in Supplement | |

Before freezing, run each competitor's `--help` and check its README for the
recommended batch usage. Record the reasoning per tool in the Supplement.

**A4. Primary metric and statistics.** Primary: verified MB/s per rep
(`bytes_verified / wall`) and runs completed. Effect size: per-rep paired ratio
(adaptiSeq / competitor within the same rep block), reported as median with
bootstrap 95% CI. Test: Wilcoxon signed-rank over reps. Reps: 10 for 3a/3b
main arms. No post hoc selection between adaptiSeq arms: exactly one
pre-specified adaptiSeq arm (the default) appears in Fig 1b.

**A5. Relationship to prior work.** Write the paragraph now, not at the end:
(i) adaptiSeq vs iSeq (port plus what is new); (ii) adaptiSeq vs FastBioDL
(arXiv:2508.05511), which also does adaptive concurrency for the same datasets.
If the adaptive controller is shared with FastBioDL, it cannot be a novelty
claim here; say so and cite. Decide author list and contributions (CRediT).

**A6. Attribution and licence.** adaptiSeq ports `iSeq-main/bin/iseq` 1.9.8. If
iSeq is MIT-licensed, the MIT terms require keeping its copyright notice:
add it to `LICENSE` (or a `NOTICE` file). Consider contacting the iSeq authors
before submission; it reduces the risk of a hostile review.

---

## 2. Phase B: software fixes and release

| ID | Task | Acceptance criterion |
|----|------|----------------------|
| B1 | Fix exit code on SRA-only runs: currently `rc=1` and the run in `fail.log` while valid `_1/_2(.fastq.gz)` are produced (E8, both machines; reproduce with `SRR1031060`/`SRR1031066`) | exit 0, run in `success.log`, regression test added |
| B2 | Resolve/transfer overlap: either implement producer/consumer streaming using `resolve_all(on_task=...)` in `core._batch_download_phase` and `_aspera_download_phase`, or remove every overlap claim | if implemented: test showing first download starts before resolution ends; if not: grep shows no overlap claim in README, docs, FINDINGS |
| B3 | Implement A1 (controller flag, defaults) | CLI help, docs, tests updated |
| B4 | Remove stale claims flagged by the 2026-06-15 Codex verdict (`--protocol` default, `--engine` fallback text, etc.) | all items in that document closed or answered |
| B5 | Decide whether an SRA-only accession now resolves via ENA (E10 notes say `SRR1031060` resolves with 1 ENA request; E8 says it is forced to `.sra`). Fix the resolver or the notes | one consistent, tested statement |
| B6 | Version bump to 0.2.0; changelog | tag pushed |
| B7 | Publish to PyPI | `pip install adaptiseq` works in a clean env |
| B8 | Bioconda recipe (gives BioContainers image automatically) | `conda install -c bioconda adaptiseq` works |
| B9 | Zenodo DOI for the release (GitHub integration) | DOI in README and CITATION.cff |
| B10 | CI green on 3.10 to 3.12; offline test suite passes; coverage figure if cheap | badge green |
| B11 | Repository hygiene before reviewers look: move internal notes (`HANDOFF.md`, `PART*_PLAN.md`, `adaptiseq_codex_*.md`, `NOTES.md`, `adaptiSeq_part*.md`) to a `dev-notes/` directory or a separate branch; remove `btae641 (1).pdf`; remove `*.bak` | top-level contains only user-facing material |
| B12 | Upstream: check the latest iSeq release; if the 3-file-run bug persists, open an issue on BioOmics/iSeq with the reproducer (`SRR22904269`) | issue link (cite in Supplement) |

All benchmark reruns in Phase D must use the tagged release (B6), installed from
PyPI or Bioconda, not an editable checkout.

---

## 3. Phase C: benchmark harness fixes

**C1. Arm-order randomisation is degenerate.** `run_e3.sh:165` uses
`shuf --random-source=<(yes "$rep")`. Verified: for reps 1 to 5 the 2nd to 5th
positions are identical in every rep (`f d e c`), which matches the E3 logs
(fastq-dl always 3rd). Replace with a proper seeded permutation, e.g.
`python3 -c "import random,sys; r=random.Random(int(sys.argv[1])); ..."`,
log the order, and apply the same fix to E5/E7/E8 harnesses (E8 used a fixed
order). Acceptance: a test that the permutations differ in every position
across reps.

**C2. Rep blocking.** Run all arms of one rep back-to-back inside one block
(already the case), and record block start/end timestamps so paired ratios are
computed within a block.

**C3. Mixed-database panel (3c) redesign.** Today `D4_mixed.txt` has 20
accessions but only 12 (ENA) are in the manifest; adaptiSeq/iSeq wrote 8.86 GB
to disk (SRA conversion of the other 8) while Kingfisher wrote 0.22 GB, so wall
times are not comparable and, as tabulated, adaptiSeq looks 10x slower.
Replace with:
- a stratified list: ENA-mirrored, SRA-only (verified per run at run time),
  GSA (CRR/CRX), GEO (GSE -> SRX), DDBJ;
- per-stratum outcome per tool: completed / unsupported / failed, with output
  format and bytes;
- wall time compared **only** on the common subset all tools complete;
- this becomes Supplementary Table S-cross-db; its completion column feeds
  Fig 1c.

**C4. Output-format parity.** Every arm must produce `.fastq.gz` for the
throughput panels. Check Kingfisher `-f fastq.gz` and fastq-dl defaults; reject
reps whose format differs (log, do not silently compare).

**C5. Verifier.** Keep md5-vs-manifest (`verify_output.py`) as the only judge.
Add per-run layout (1/2/3 files) and database stratum to the output TSV so
Fig 1c needs no manual joins.

**C6. Machine metadata.** At job start record: hostname, kernel, CPU, link probe
(`curl` throughput to ENA HTTPS and FTP, 20 s each), RTT to `ftp.sra.ebi.ac.uk`
and `ftp-trace.ncbi.nlm.nih.gov`, and time of day. These become covariates and
the Methods text.

**C7. Dry run.** One rep of every panel on Fabric with the release build before
committing machine time. Gate: every arm produces a parseable TSV row and the
verifier agrees with a manual md5 check on 3 random runs.

---

## 4. Phase D: experiments

Run order follows dependency and payoff. Times are estimates from existing logs.

### D1. E1: feature matrix (Table 1). ~1 day
Tools: adaptiSeq, iSeq, Kingfisher, fastq-dl, fetchngs, pysradb, ffq,
SRA Toolkit. Columns: databases; accession types; output formats; metadata;
md5/vdb-validate; resume; parallel download; batch pool over many accessions;
rate-limited parallel resolution; merge; Python API (returns values, typed
exceptions); conda/pip. Each cell backed by a command in `bench/e1/` and its
logged output. No cell copied from iSeq's figure.

### D2. E3: batch throughput (Fig 1b, 1d). ~2 to 3 days machine time per machine
- **Datasets:** 3a = D1_fair (201 runs, 4.4 GB); 3b = D2 subset (8 runs,
  25.9 GB). Add **3b-large**: a 100 to 300 GB byte-bound set (e.g. full D2,
  60 runs, 206 GB) at 3 reps, to answer "does it hold at scale".
- **Arms (main):** adaptiSeq default (A1), iSeq -p 8, iSeq stock, Kingfisher
  (A3 chain), fastq-dl, [fetchngs].
- **Arms (Fig 1d / Supplement):** adaptiSeq fixed-j8, fixed-j20, fixed-j40,
  adaptive-j40.
- **Reps:** 10 for 3a/3b, 3 for 3b-large. Stock iSeq on 3b may drop to 5 reps
  (2,000 to 2,800 s per rep) if time is short; state it.
- **Machines:** Fabric and Expanse, same release, same lists.
- **Budget:** main arms on 3a+3b are ~2.4 h per rep per machine (from current
  medians), so 10 reps is ~24 h per machine plus the Fig 1d arms (~0.5 h per rep).

### D3. E4b: adaptive under contention/throttling (strengthens K4). ~1 day
- **Over-provisioning:** already covered by Fig 1d arms; make sure they run on
  both machines with 10 reps.
- **Shared link:** 2 and 4 concurrent adaptiSeq instances on one node, each
  with `-j 40`, fixed vs adaptive. Metrics: aggregate MB/s, per-instance MB/s,
  Jain's fairness index, HostGuard trips. 5 reps.
- **Go/no-go:** if adaptive shows no advantage over fixed `-j 40` here, K4 rests
  on Fig 1d alone; do not add further adaptive claims.

### D4. E7: reliability at scale (Fig 1c, Table S). ~2 days per machine
- **Corpus:** >= 1,000 runs, stratified random sample across >= 5 projects,
  including 1/2/3-file layouts, small to medium sizes (target <= 150 GB total so
  three tools x 3 reps x 2 machines is feasible). Freeze the list and manifest
  in `datasets/`.
- **Tools:** adaptiSeq default, iSeq -p 8 and stock, Kingfisher (chain),
  fastq-dl.
- **Reps:** 3 per machine.
- **Report:** runs completed (md5 vs manifest), stratified by layout and
  database; retries; failure causes (classify each failed run: unsupported,
  network, tool bug).
- Keep E7b (resume), E7c (never-truncate, corruption) and E7d (circuit breaker)
  results as they are; they are deterministic. Rerun once on the release build
  to confirm.
- State honestly: resume-from-offset is not a differentiator (iSeq's `wget -c`
  also resumes, E7b).

### D5. E10: resolution throughput and etiquette (Supplement). ~0.5 day
- Competitors in **batch mode**: `iseq -i LIST -m`, `pysradb metadata A B C ...`,
  `ffq A B C ...`, `kingfisher annotate -r A B C ...`.
- N in {100, 500, 2000} on live ENA, both machines, 3 reps; competitors at the
  same N (currently N = 20).
- Keep 10c (limiter vs naive) and label it explicitly as a deterministic
  simulation driving the production limiter.
- Correct the 10b text: resolution does not overlap transfer unless B2 is
  implemented.

### D6. E8: resource profile (Supplement). ~0.5 day
Rerun on the release with randomised order (C1). Report RSS, mean CPU,
`cpu_core_s`; report the Expanse single-file ENA completions (2/5 vs Kingfisher
5/5) in the Supplement as is. Do not use E8 wall times as a throughput claim.

### D7. E6: API case study (main text listing + Supplement). ~0.5 day
- 6 to 8 line listing: `get_metadata` -> pandas filter -> `fetch` -> handle
  `IntegrityError`.
- A Snakemake rule that imports `adaptiseq.fetch`, run end to end on 5 runs,
  in the repo under `examples/`.
- API vs CLI overhead on one accession (5 reps): expected negligible.

### D8. E5: adaptive Aspera. Supplement only, or drop
If kept: >= 5 reps with adaptive and fixed j1/j2/j4/j8 interleaved in the same
blocks, probe window >= ascp startup (15 s). Report as "completes reliably;
throughput depends on time-variable EBI session policy". The RSA-key finding
(DSA key rejected by ENA) is worth one sentence regardless.

### D9. Optional: third vantage point
Both machines are in the USA. A European or Asian cloud VM (root access) would
(i) test whether conclusions depend on distance to EBI/NGDC, (ii) allow `tc`
shaping at iSeq's 540 Mbps / 2 Gbps for a like-for-like panel. Do this only if
reviewers ask, or if time remains.

### Not doing (state in Limitations)
E2 single-file micro-benchmark (aria2c is faster per file; cite E8 addendum
probe), E9 strong scaling to TB scale.

---

## 5. Phase E: analysis

- One script per figure under `bench/paper/`, reading only the frozen TSVs;
  `make figures` regenerates everything.
- For each competitor: median MB/s with IQR; paired ratio with bootstrap 95% CI
  (10,000 resamples over reps); Wilcoxon signed-rank p.
- Report both machines in every main panel; never pick the better machine.
- Pre-specified arm only in Fig 1b; all other adaptiSeq arms in Supplement.
- Negative results kept in Supplement: legacy adaptive < fixed-j20; adaptive
  Aspera < fixed; Kingfisher faster on a single large ENA file.
- Retire `analysis_fabric_vs_expanse/ANALYSIS.md` claims that rely on best-of-arm
  selection (14.2x, 18.9x) or omit 3c; replace with the new analysis.

---

## 6. Phase F: reproducibility package

- `datasets/`: every accession list and md5 manifest, with the date pulled.
- Environment: `conda env export` per machine plus the Bioconda adaptiSeq
  version; competitor versions.
- Raw TSVs and per-run logs archived on Zenodo (separate DOI from the software).
- `bench/README.md`: one command per panel, expected runtime, required egress.
- Data availability statement listing BioProjects (PRJNA916347, PRJNA762469,
  PRJNA540705, plus the E7 corpus projects).

---

## 7. Phase G: manuscript

| Section | Words (approx.) | Content |
|---|---|---|
| Abstract | journal limit | Motivation; Results with the two headline numbers (K1, K2); availability with PyPI/Bioconda/GitHub/Zenodo |
| 1 Introduction | 300 | batch acquisition problem; existing tools resolve and download serially or drop runs; iSeq and FastBioDL positioned |
| 2 Implementation | 600 | resolution chain and rate limiters; batch pool and controller; segmented engine and integrity guarantees; Python API listing |
| 3 Results | 700 | Fig 1b to 1d, Table 1; both machines; exact ratios with CIs |
| 4 Discussion and limitations | 250 | single-file throughput (aria2c), adaptive is a safety bound not an optimiser, time-variable archive throughput, two US vantage points |
| Supplement | unlimited | methods, all panels, cross-database table, E5/E8/E10, controller ablations, competitor configuration rationale |

Write Implementation and the Supplement Methods first (they do not depend on
the reruns), Results last.

---

## 8. Phase H: pre-submission checks

- [ ] Every number in the text traces to a TSV row via the figure scripts.
- [ ] Fresh-machine install from Bioconda and PyPI; README examples run.
- [ ] Software and data DOIs resolve; licence includes iSeq notice (A6).
- [ ] Internal review by one person outside the project, briefed to act as a
      hostile reviewer, against this checklist: competitor fairness, arm
      selection, novelty vs iSeq/FastBioDL, statistics.
- [ ] Cover letter states the novelty relative to iSeq (Bioinformatics 2024)
      in two sentences.
- [ ] Suggested reviewers without conflicts; do not suggest iSeq authors as the
      only reviewers.
- [ ] bioRxiv preprint at submission (optional, recommended).

---

## 9. Order of work and gates

| Step | Phases | Gate to proceed |
|---|---|---|
| 1 | A1 to A6 decisions written here | decisions committed |
| 2 | B1 to B5, B11, C1 to C6 | tests green; C1 permutation test passes |
| 3 | B6 to B10 release | `pip`/`conda` install of 0.2.0 in clean env |
| 4 | C7 dry run | all TSV rows parse; verifier spot-check passes |
| 5 | D1, D7 (cheap) in parallel with D2 on both machines | D2 complete, 10 reps |
| 6 | D3, D4 | D4 corpus complete on both machines |
| 7 | D5, D6, (D8) | |
| 8 | E, F | figures regenerate from scratch |
| 9 | G, H | checklist complete |

Indicative duration, if machine time is available without long queues:
about 6 to 8 weeks, of which roughly 2 to 3 weeks are unattended runs.

## 10. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Kingfisher with its method chain closes the gap on 3a/3b | K2 ratio shrinks | still report; K1 (completeness) and K3 carry the paper |
| Editor judges the work a reimplementation of iSeq | desk reject | lead with completeness, batch and API, quantified; cover letter explicit; consider Bioinformatics Advances as fallback venue |
| Adaptive overlaps FastBioDL | novelty objection | A5 paragraph; claim K4 only |
| EBI/NCBI throughput drifts between machines and weeks | noisy ratios | paired within-block ratios, 10 reps, report both machines |
| Latest iSeq has fixed the 3-file bug | K1 margin shrinks | benchmark the latest iSeq; report the version; claim stands for 1.9.8 only if unfixed |
