# adaptiSeq: minimal submission plan (Bioinformatics, Application Note)

Goal: the least work that still gives a defensible Application Note. This
drops everything in `SUBMISSION_PLAN.md` that is "nice to have". What remains
is what an editor or reviewer would otherwise use to reject the paper.

Estimated effort: 3 to 5 working days hands-on, plus 1 to 2 days of unattended
machine time.

---

## Paper in one sentence

adaptiSeq is a pip-installable Python library and CLI that downloads lists of
public sequencing accessions **completely** (it finishes runs iSeq and
Kingfisher drop) and **several times faster** than existing dedicated tools,
with **default settings**.

Claims made: completeness, batch speed at defaults, Python API, polite
rate-limited parallel resolution (mechanism only).
Claims **not** made: adaptive beats the best fixed setting; resolve/download
overlap; adaptive Aspera speed; anything about single-file speed.

---

## Step 1: software (about 1 day)

| # | Task | Why it is necessary |
|---|------|---------------------|
| 1 | Add iSeq's MIT notice (`Copyright (c) 2024 BioOmics`) to `LICENSE`; restore "adaptiSeq builds on iSeq; please cite iSeq" in the README; credit FastBioDL for `engine/segmented.py` | Licence compliance. iSeq authors are likely reviewers; missing provenance is the fastest route to a rejection |
| 2 | README on `main`: remove "not yet on PyPI" and the stale badge comment; `CITATION.cff`: real author names, ORCIDs, current version | Reviewers install from the README |
| 3 | Fix exit code 1 on SRA-only runs that produce valid FASTQ (reproduce with `SRR1031066`). If not fixable in 2 hours, document it in the README as known behaviour | Reliability is the headline claim; a reviewer who tests one SRA-only accession will hit it |
| 4 | Release 0.1.4 on PyPI with 1 to 3; tag it; enable the GitHub-Zenodo integration so the tag gets a DOI | The paper must cite one exact, archived version |

Not necessary: Bioconda, the `--adaptive-mode` flag, overlap streaming,
docs rewrite.

---

## Step 2: one benchmark rerun (about 0.5 day setup, then unattended)

The existing E3 data cannot be reused as the main result, for three reasons:
- the arm order was effectively fixed (the seeded `shuf` in `run_e3.sh:165`
  gives the same positions 2 to 5 in every rep);
- Kingfisher was restricted to `-m ena-ftp`;
- no arm used the released defaults (they ran `--meta-jobs 8`, and the
  `climb` arms also had `ASEQ_PROBE_WINDOW=8`; the defaults are
  `--meta-jobs 3`, probe window 5).

**Harness changes (`bench/e3/run_e3.sh`):**
1. Replace the shuffle with a real seeded permutation, e.g.
   `python3 -c "import random,sys; a=sys.stdin.read().split('\n'); a=[x for x in a if x]; random.Random(int(sys.argv[1])).shuffle(a); print('\n'.join(a))" "$rep"`.
2. Add the version and the installed wheel's sha256 to every TSV row
   (or write them once to `versions.txt` and do not change the install
   during the run).

**Arms (6):**

| arm | command |
|---|---|
| adaptiSeq default | `adaptiseq -i LIST -g -o .` (no tuning flags at all) |
| adaptiSeq fixed | `adaptiseq -i LIST -g --no-adaptive -j 20 -o .` (anchors the default) |
| iSeq -p 8 | `iseq -i LIST -g -p 8 -o .` |
| iSeq | `iseq -i LIST -g -o .` |
| Kingfisher | `kingfisher get --run-identifiers-list LIST -m ena-ftp aws-http prefetch --check-md5sums -f fastq.gz --output-directory .` (check flags against `kingfisher get --help` first) |
| fastq-dl | as in the current harness |

**Panels (2):**
- **3r:** `D1_full_PRJNA916347` (241 runs, 7.6 GB), overhead-bound. Also gives
  runs completed, including the 40 three-file runs.
- **3b:** `D2_subset_PRJNA762469` (8 runs, 25.9 GB), byte-bound.

**Reps and machines:** 5 reps on Expanse and 5 on Fabric, using the same
0.1.4 wheel. From current medians this is about 2.7 h per rep, i.e. roughly
14 h per machine, one unattended job each. If only one machine is available,
use Expanse and say so.

**Gate before the full run:** one rep of both panels; check that every arm
writes a TSV row and that the md5 verifier agrees with a manual check on
3 runs.

---

## Step 3: analysis (about 0.5 day)

One script reading the new TSVs:
- median and IQR of verified MB/s, per arm, panel and machine;
- per rep, the ratio adaptiSeq default / competitor; report the median ratio
  with a bootstrap 95% CI;
- runs completed per tool on 3r, split into 1/2-file and 3-file runs.

**Figure 1** (one figure, three panels, both machines side by side):
(a) 3r MB/s, (b) 3b MB/s, (c) runs completed on 3r.

**Table 1:** feature matrix. Use the tools' current docs and `--help`, with
versions. Columns: databases, batch download, parallel resolution,
md5 check, resume, merge, Python API, pip/conda.

**Supplement**, reusing existing results as they are, each with one caveat line:
- E7b/c/d (resume, never-truncate, corruption, circuit breaker);
- E10c (rate-limit etiquette; label it as a simulation driving the production
  limiter);
- E8 resource table;
- old E3 adaptive arms (fixed `-j 40` collapses, the adaptive controller at
  `-j 40` does not), labelled as an earlier version with a fixed arm order.

Dropped entirely: mixed-database panel 3c (invalid as run), E10 competitor
comparison (strawman protocol), E5 Aspera speed, E2, E4, E9.

---

## Step 4: manuscript (about 2 days)

About 2,000 words, one figure, one table (OUP limit: 4 pages).

1. **Abstract** in the journal's structured format; give the two headline
   numbers (runs completed; median speed ratio vs the fastest competitor, with CI).
2. **Introduction (250 words).** Pipelines need many accessions; existing
   tools work run by run and drop some layouts. Cite iSeq, Kingfisher,
   fastq-dl, fetchngs, pysradb, and FastBioDL.
3. **Implementation (600 words).** Resolution chain and per-endpoint rate
   limits; batch worker pool with an adaptive controller (describe it, do not
   claim it is optimal); segmented, resumable, md5-checked transfer (credit
   FastBioDL); a 6-line Python API example.
4. **Results (600 words).** Figure 1 and Table 1. State the competitor
   commands, machines, reps, and that arm order was randomised.
5. **Limitations (150 words).** Two US vantage points; archive throughput
   varies with time of day; aria2c is faster for a single file; the adaptive
   controller protects against a bad `-j`, it does not beat a good one.
6. **Availability.** GitHub, PyPI, Zenodo DOI, MIT; benchmark scripts and
   accession lists (on the `e8` branch or a small separate repo) with the
   exact commit.

**Cover letter:** two sentences on what is new relative to iSeq (2024, same
journal): batch completion of runs iSeq drops, several-fold speed on
accession lists, and a Python library interface.

---

## Checklist before pressing submit

- [ ] iSeq and FastBioDL credited in `LICENSE`/README/paper.
- [ ] `pip install adaptiseq==0.1.4` in a fresh environment runs the README example.
- [ ] Every number in the text comes from the new TSVs via the script.
- [ ] Zenodo DOI resolves.
- [ ] Accession lists and md5 manifests are public.

## Accepted risks (what a reviewer may still ask for)

Small reliability corpus (241 runs vs iSeq's 3,000 files), 5 reps, no
non-US machine, no Bioconda. Each is answerable in revision; none should
cause rejection on its own. The one risk this plan cannot remove: an editor
may judge the work "a faster iSeq" and desk-reject. If that happens, the fallback
venue is *Bioinformatics Advances*, where the same manuscript fits without
changes.
