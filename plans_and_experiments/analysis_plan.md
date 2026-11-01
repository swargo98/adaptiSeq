# Analysis plan for the Application Note (written 2026-11-01)

What the paper's numbers and figure are computed from, how, and what they may claim. Start the analysis
only when both machines' five reps are in (the user, 11-01: "I'll start the analysis after the Fabric
results"). The Fabric run itself is planned in `remaining_tasks.md`, section 1, item 3.

---

## 1. Framing (the user, 11-01)

Sell the whole system, not the adaptive engine. The paper does **not** claim that adaptation is the
fastest setting: fixed `-j 20` beat the default in 9 of 10 Expanse panel-reps. What it highlights:

1. **Speed against existing tools.** Both adaptiSeq arms against iSeq, iSeq `-p 8`, Kingfisher and
   fastq-dl. This is the headline.
2. **Completeness, stated as "every file is md5-verified or reported as failed".** Not "always complete":
   adaptiSeq missed one 3r run in some reps (ENA served the same bad copy three times) but exited 1 and
   named the run each time. The contrast is the other tools' exit-0 rows with runs missing or fetched
   from SRA (unverifiable against ENA's md5). Decision A decides the final wording.
3. **Batch download from a list and the Python interface** (`fetch`, `resolve`, `get_metadata`), with the
   iSeq-compatible command line. Described, not benchmarked.
4. **The adaptive controller as an included option.** Described with its controllers; the benchmark
   reports its numbers next to fixed `-j 20` without ranking it first.

Open and the user's: which setting is the default (the paper must say why, if it stays adaptive),
Decision B, and whether the transport-probe fix goes into the paper's build (section 6).

## 2. Inputs

| machine | source | reps | build |
|---|---|---|---|
| Expanse | `e3_submission_0.1.12_expanse/e3_55290250` ... `e3_55290254`, one `e3_results.tsv` per rep | 1-5 | 0.1.12, wheel sha256 `0c5e6a82...`, iSeq 1.9.9, Kingfisher 0.5.0, fastq-dl 4.0.1, Python 3.11.17 |
| Fabric | the five Fabric rep directories (`remaining_tasks.md` section 1, item 3) | 1-5 | must be the same wheel and tool versions |

- Panels 3r (D1_full_PRJNA916347, 241 runs, 7.6 GB, timeout 10800 s) and 3b (D2_subset_PRJNA762469, 8 runs,
  25.9 GB, timeout 30000 s).
- All five reps count, including the slow ones (Expanse rep 4) and the TIMEOUTs. No rep is dropped or
  re-run for being unrepresentative. Gate runs, rounds 1-3 and the j-sweep are not paper numbers (they
  can go to the supplement, section 5).
- `analyze_submission.py` takes one TSV per machine, so first concatenate each machine's five TSVs (one
  header) into `paper/numbers/inputs/<machine>_e3_results.tsv`, and record the source paths in a README
  there.

## 3. Checks before any number is computed

1. One adaptiSeq version and wheel sha256 per machine, the same on both (the script refuses otherwise;
   do not pass `--allow-mixed`).
2. Same iSeq, Kingfisher, fastq-dl and Python versions on both (`versions_e3.txt` in every rep dir).
3. Five reps per machine x panel x arm, 60 rows per machine. Arm order per rep comes from the same seed
   (20261013), so rep k ran the arms in the same order on both machines; check `logs/arm_order.tsv`.
4. `link_probe.txt` for every rep (ENA MB/s at 1/8/20 connections), to report each machine's path.
   Expanse ranged 0.5 to 2.1 MB/s per connection at P=1.
5. Re-run `check_panel.sh` on every rep and compare with the rows in `progress_log.md`; a row that
   disagrees is investigated before the analysis goes on.

## 4. Metrics and statistics

Per machine x panel x arm x rep, from `e3_results.tsv` and the logs:

| metric | source | notes |
|---|---|---|
| wall time | `wall_s` | a TIMEOUT counts as the timeout and is marked; any ratio using it is a lower bound |
| verified throughput | `MBps_verified` | md5-verified bytes only, so a partial run cannot look fast |
| runs verified | `runs_complete` / `runs_expected` | 3r also split 1-2-file vs 3-file runs |
| runs present but unverifiable | `runs_present_unverified` | SRA fallbacks; reported separately (Decision B) |
| exit status | `exit_code`, `status` | ok / rc=N / TIMEOUT |
| **silent incompleteness** | exit 0 and runs verified < expected | the completeness claim's key number; new column |
| connections | `logs/conc_*.tsv` column 4 (`conns_archive`), mean and max | as in `check_panel.sh` |
| md5 re-fetches | log lines "MD5 mismatch" | ENA's bad copies; per arm |

Statistics:

- Medians, IQR and min-max over the five reps. No means in the text (right-skewed timings).
- Speed comparisons are **paired within a rep** (arms in one rep ran back to back on one node): ratio of
  verified MB/s, adaptiSeq arm / other arm, per rep; report the median of the five ratios with the
  bootstrap 95% CI the script computes (10,000 resamples, seed 20261013), and the min and max. With five
  reps the CI is coarse; the text gives the range as well.
- Report each machine separately; do not pool Expanse and Fabric. The claim is that the ranking holds on
  both.

### Script changes needed (`bench/e3/analyze_submission.py`)

The script fixes the reference at `adaptiseq-default` and computes default / other. For the system
framing:

1. `--reference` option, and run it twice: reference `adaptiseq-default` and reference
   `adaptiseq-fixed-j20`. The headline ("adaptiSeq vs the fastest other tool") uses the default unless the
   user changes the default, in which case it uses the new default.
2. A `completeness.tsv`: per machine x panel x arm, reps with all runs verified, reps with silent
   incompleteness, reps that exited non-zero, total runs present-unverified, total md5 re-fetches.
3. A `connections.tsv` from the `conc_*.tsv` files (mean and max per arm, median over reps).
4. A default-vs-fixed table (ratio per rep, both panels, both machines) for the supplement, with the
   cause of each ratio above 2 from `progress_log.md` (rep 2 3r and rep 5 3b: one failed HTTPS probe sent
   the list to segmented FTP; rep 4 3b: ENA's 403/416 on range requests).
5. Figure 1: (a) 3r MB/s and (b) 3b MB/s per arm, both machines; (c) runs on 3r stacked as verified /
   present-unverified / missing, so silent incompleteness is visible. Keep the fixed tool colours.

Outputs to `paper/numbers/`: `summary.tsv`, `ratios_ref-default.tsv`, `ratios_ref-fixed-j20.tsv`,
`completion.tsv`, `completeness.tsv`, `connections.tsv`, `numbers.json`, `fig1.pdf/.png`. Run on a compute
node (`srun -A umr115 ...`), not the login node.

## 5. What goes where

**Main text.** Speed: median ratio of adaptiSeq (both arms) to the fastest other tool, per panel and
machine. Completeness: runs verified per arm, silent-incompleteness counts, and adaptiSeq's failed runs
named with the cause. One sentence on the adaptive option and how it compares with fixed `-j 20`, with
the range.

**Supplement.**
- Every row of both machines (the tables in `progress_log.md` section 1, as one table).
- Default vs fixed `-j 20` per rep, with causes (script change 4).
- Connection counts per arm.
- The controller rounds 1-3 (topdown, bottomup, budget, greedy, knee) as the basis for the default
  choice, with budget as the fewest-connections option (user, 10-26).
- ENA's behaviour during the runs: md5 mismatches on bad copies, 403/416 on ranges, missing `fastq_ftp`
  in API answers, FTP resets.

**Limitations paragraph.** The transport probe (one failed HTTPS probe sends a whole list to FTP under
`-r auto`) unless fixed; ENA's per-connection rate on the day governs every tool; five reps.

## 6. Manuscript work after the numbers

1. Fill the 45 `[[...]]` placeholders from `paper/numbers/` (the table at the end of the draft maps each;
   update the map for the new file names).
2. Version: the draft says 0.1.4 throughout (abstract, availability, methods, Fig. 1 legend); the paper's
   build is 0.1.12.
3. Mark every sentence that says or implies the adaptive setting is the best (e.g. Discussion, "The
   adaptive controller prevents the ..."), and the Methods sentence that the `-j 20` arm is there "to show
   what the..."; reword to the section 1 framing and list each change for the user.
4. Completeness wording per Decision A; SRA fallbacks per Decision B.
5. Fabric machine description: cores and network as measured on the node actually used (`Node-MICH` had 4
   cores, not the 8 the draft states).
6. Then the OUP template (4 pages), `remaining_tasks.md` section 3, item 12.

## 7. Order of work

1. Fabric reps 1-5 done and committed (`remaining_tasks.md` section 1, item 3).
2. Checks (section 3).
3. Script changes (section 4), each tested on the Expanse TSVs alone first.
4. Run the analysis; commit `paper/numbers/` with the inputs README.
5. Report the numbers to the user, with the default-vs-fixed table, before writing any text.
6. Manuscript (section 6).
