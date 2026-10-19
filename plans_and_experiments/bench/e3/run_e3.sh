#!/usr/bin/env bash
# E3 -- Batch download (HEADLINE, Fig 3). Driver.
#
# The submission benchmark (MINIMAL_SUBMISSION_PLAN.md, Step 2) is panels 3r and
# 3b with the default arm set:
#
#   E3_ASEQ_WHEEL=/path/adaptiseq-0.1.4-py3-none-any.whl PANELS="3r 3b" \
#       bash bench/e3/run_e3.sh all 5
#
# Panels:
#   3a  overhead-dominated  (D1_fair, 201 runs / 4.4 GB)   -- fair timing, all tools complete
#   3r  robustness          (D1_full, 241 runs / 7.6 GB)   -- runs-completed; iseq drops the 3-file runs
#   3b  byte-dominated      (D2_subset, 8 runs / 25.9 GB)  -- honesty panel
#   3c  cross-database      (D4_mixed, 20 accessions)      -- ENA + SRA-only + GSA routing
#   3d  worker sweep        (D0_sweep, 8 files / 11.9 GB)  -- -j {4,8,16} only (feeds E9)
#   3s  segment sweep       (D3_seg, 2 files / 23 GB)      -- --max-segments {4,8,16}
#
# Usage:  bash bench/e3/run_e3.sh <panel> [reps]
#         PANELS="3a 3b" bash bench/e3/run_e3.sh all
#
# Arm sets (ARM_SET):
#   submission (default)  6 arms: adaptiSeq at released defaults, one fixed-j
#                         anchor, and each competitor as its docs recommend
#   legacy                the 11 arms of the first E3 campaign (tuned adaptiSeq
#                         arms, Kingfisher restricted to ena-ftp)
#
# Fairness protocol enforced here (EXPERIMENT_PLAN §12):
#   * every arm downloads the same list, in the same job, on the same node;
#   * arm order is a fresh seeded permutation every rep (logged to
#     logs/arm_order.tsv) so no arm keeps a systematic cold/warm-cache position;
#   * every row records the adaptiSeq version and build hash it ran;
#   * payload deleted after every arm;
#   * success/bytes judged by md5 against the ENA manifest, not by exit code.

set -uo pipefail

E3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E3_DIR/../.." && pwd)"
source "$E3_DIR/e3_lib.sh"

PANEL="${1:-3a}"
REPS_ARG="${2:-}"

# ---- knobs (override from the environment / sbatch) -------------------------
export E3_PYTHON="${E3_PYTHON:-python3}"
export E3_WORK="${E3_WORK:-/tmp/e3_work}"          # payload: node-local NVMe
export E3_OUT="${E3_OUT:-$REPO_DIR/e3_results}"    # results: Lustre (persists)
export E3_MD5_JOBS="${E3_MD5_JOBS:-32}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
ENABLE_FETCHNGS="${ENABLE_FETCHNGS:-0}"            # needs Nextflow+Singularity; off by default
ARM_SET="${ARM_SET:-submission}"
# The release wheel the installed adaptiSeq must be byte-identical to. Its sha256
# goes in every row; see aseq_fingerprint.py. Required for the paper panels.
export E3_ASEQ_WHEEL="${E3_ASEQ_WHEEL:-}"
export E3_SEED="${E3_SEED:-20261013}"              # base seed for the arm-order permutation
# First repetition number. A run too long for one job can be split: a second job
# with E3_REP_FIRST=4 and reps=2 produces reps 4 and 5, with the arm orders those
# reps would have had in a single job (the seed depends on the rep number). Give
# each job its own E3_OUT and pass every TSV to analyze_submission.py under the
# same machine name.
export E3_REP_FIRST="${E3_REP_FIRST:-1}"
# Kingfisher's prefetch fallback writes nothing with sra-tools >= 3.1 unless this
# is set (found in E8). It only matters when ena-ftp fails for a run.
export NCBI_VDB_PREFETCH_USES_OUTPUT_TO_FILE="${NCBI_VDB_PREFETCH_USES_OUTPUT_TO_FILE:-1}"

mkdir -p "$E3_WORK" "$E3_OUT"
export E3_LOGS="$E3_OUT/logs"; mkdir -p "$E3_LOGS"

# Downloaded payload is pure scratch: it is hashed, recorded, and has no value
# afterwards (E3 keeps the TSV, not the fastq). run_arm purges each arm's dir as
# it goes, but a scancel / Slurm timeout / crash would strand whatever was
# in flight -- up to ~26 GB on panel 3b. Purge on ANY exit, including signals.
# Only ever touches $E3_WORK; results in $E3_OUT are never removed.
_e3_cleanup() {
    local rc=$?
    trap - EXIT INT TERM
    if [[ -n "${E3_WORK:-}" && -d "$E3_WORK" ]]; then
        local left
        left=$(du -sh "$E3_WORK" 2>/dev/null | cut -f1)
        rm -rf "${E3_WORK:?}"/* 2>/dev/null || true
        [[ -n "$left" && "$left" != "0" ]] && echo "[cleanup] purged payload ($left) from $E3_WORK" >&2
    fi
    exit $rc
}
trap _e3_cleanup EXIT INT TERM

# A previous run that was killed hard may have left payload behind; start clean
# so its bytes can never be attributed to an arm in this run.
if [[ -n "$(ls -A "$E3_WORK" 2>/dev/null)" ]]; then
    echo "[cleanup] removing stale payload from a prior run in $E3_WORK" >&2
    rm -rf "${E3_WORK:?}"/* 2>/dev/null || true
fi
ISEQ_BIN="${ISEQ_BIN:-iseq}"
export E3_TSV="$E3_OUT/e3_results.tsv"
e3_init_results "$E3_TSV" || exit 1

# Fail before the first download, not after 14 hours, if the install is not the
# release wheel.
if ! _fp="$(e3_aseq_fingerprint)"; then
    echo "[ERROR] cannot fingerprint the installed adaptiSeq (see message above)." >&2
    exit 1
fi
case "$PANEL" in
  3r|3b|3jr|3jb|4r|4b|4s|4g)
    if [[ "$ARM_SET" != "legacy" && -z "$E3_ASEQ_WHEEL" && "${E3_ALLOW_UNPINNED:-0}" != "1" ]]; then
        echo "[ERROR] E3_ASEQ_WHEEL is not set. The paper panels must run the released wheel:" >&2
        echo "          pip download adaptiseq==0.1.4 --no-deps -d wheels/" >&2
        echo "          pip install --force-reinstall --no-deps wheels/adaptiseq-0.1.4-py3-none-any.whl" >&2
        echo "          export E3_ASEQ_WHEEL=\$PWD/wheels/adaptiseq-0.1.4-py3-none-any.whl" >&2
        echo "        (E3_ALLOW_UNPINNED=1 overrides this for a dry run.)" >&2
        exit 1
    fi ;;
esac
if [[ "$PANEL" != "all" ]]; then
    {
        echo "# $(date -Is)  host=$(hostname -s)  panel=$PANEL  arm_set=$ARM_SET  seed=$E3_SEED"
        echo "adaptiseq: $_fp  wheel=${E3_ASEQ_WHEEL:-none}"
        echo "iseq: $("$ISEQ_BIN" -v 2>&1 | grep -m1 -i 'version' || echo missing)"
        echo "kingfisher: $(kingfisher --version 2>&1 | head -1)"
        echo "fastq-dl: $(fastq-dl --version 2>&1 | head -1)"
        echo "python: $("$E3_PYTHON" --version 2>&1)"
    } >> "$E3_OUT/versions_e3.txt"
fi
[[ -f "$E3_LOGS/trajectories.tsv" ]] || printf 'arm\trep\tline\n' > "$E3_LOGS/trajectories.tsv"

# adaptiSeq arms run through aseq_run.py: same code path as the bare CLI
# (cli.main -> core.run), but with the batch controller's INFO logging on so the
# per-probe gate.active decisions are recorded. Set ASEQ=adaptiseq to use the
# bare CLI instead (you then lose the internal trajectory, not any behaviour).
ASEQ="${ASEQ:-$E3_PYTHON $E3_DIR/aseq_run.py}"
# The submission arms use the bare CLI: the claim is about what a user gets from
# `adaptiseq -i LIST -g`, so nothing may sit between the harness and the release.
ASEQ_CLI="${ASEQ_CLI:-adaptiseq}"

# ---- arm table --------------------------------------------------------------
# "arm_name|tool|command".  $LIST / $IDS_CSV are exported by run_arm; CWD is a
# fresh empty dir.  Every arm is asked for gzip FASTQ from ENA so the formats are
# comparable; md5 checking is left ON for every tool that offers it (we do NOT
# pass adaptiSeq's -k), because integrity is part of what these tools are for.
#
# Submission set. adaptiseq-default carries no tuning flag at all (released
# defaults: -j 20, --adaptive, --meta-jobs 3, probe window 5). adaptiseq-fixed-j20
# differs from it only by --no-adaptive, to anchor the default. Kingfisher gets
# its documented method fallback chain, not ena-ftp alone.
declare -a ARMS_SUBMISSION=(
  "adaptiseq-default|adaptiseq|$ASEQ_CLI -i \$LIST -g -o ."
  "adaptiseq-fixed-j20|adaptiseq|$ASEQ_CLI -i \$LIST -g --no-adaptive -j 20 -o ."
  "iseq-p8|iseq|$ISEQ_BIN -i \$LIST -g -p 8 -o ."
  "iseq|iseq|$ISEQ_BIN -i \$LIST -g -o ."
  "kingfisher|kingfisher|kingfisher get --run-identifiers-list \$LIST -m ena-ftp aws-http prefetch --check-md5sums -f fastq.gz --output-directory ."
  "fastq-dl|fastq-dl|while read -r a; do [ -n \"\$a\" ] && fastq-dl --accession \"\$a\" --outdir . ; done < \$LIST"
)

# Legacy set (first E3 campaign). Kept so those results stay reproducible.
declare -a ARMS_FULL=(
  "iseq|iseq|$ISEQ_BIN -i \$LIST -g -o ."
  "iseq-p8|iseq|$ISEQ_BIN -i \$LIST -g -p 8 -o ."
  "kingfisher|kingfisher|kingfisher get --run-identifiers-list \$LIST -m ena-ftp --output-directory . --check-md5sums"
  "fastq-dl|fastq-dl|while read -r a; do [ -n \"\$a\" ] && fastq-dl --accession \"\$a\" --outdir . ; done < \$LIST"
  "adaptiseq-fixed-j8|adaptiseq|$ASEQ -i \$LIST -g --no-adaptive -j 8 --meta-jobs 8 -Q -o ."
  "adaptiseq-fixed-j20|adaptiseq|$ASEQ -i \$LIST -g --no-adaptive -j 20 --meta-jobs 8 -Q -o ."
  "adaptiseq-fixed-j40|adaptiseq|$ASEQ -i \$LIST -g --no-adaptive -j 40 --meta-jobs 8 -Q -o ."
  "adaptiseq-adaptive-j20|adaptiseq|$ASEQ -i \$LIST -g --adaptive -j 20 --meta-jobs 8 -Q -o ."
  "adaptiseq-adaptive-j40|adaptiseq|$ASEQ -i \$LIST -g --adaptive -j 40 --meta-jobs 8 -Q -o ."
  # NEW: explore-then-exploit adaptive controller (docs/ADAPTIVE_CONTROLLER.md).
  # Same CLI as the adaptive arms; the controller variant is selected by the
  # ASEQ_ADAPTIVE_MODE=climb env var (aseq_run.py inherits it). The legacy
  # adaptive arms above are kept unchanged for comparison.
  "adaptiseq-climb-j20|adaptiseq|ASEQ_ADAPTIVE_MODE=climb ASEQ_PROBE_WINDOW=8 $ASEQ -i \$LIST -g --adaptive -j 20 --meta-jobs 8 -Q -o ."
  "adaptiseq-climb-j40|adaptiseq|ASEQ_ADAPTIVE_MODE=climb ASEQ_PROBE_WINDOW=8 $ASEQ -i \$LIST -g --adaptive -j 40 --meta-jobs 8 -Q -o ."
)
FETCHNGS_ARM="fetchngs|fetchngs|nextflow run nf-core/fetchngs -r 1.12.0 --input \$IDS_CSV --outdir . -profile singularity --download_method ftp -ansi-log false"

build_arms() {
    case "$ARM_SET" in
      submission) ARMS=("${ARMS_SUBMISSION[@]}") ;;
      # the two adaptiSeq submission arms only: checks a new build on a panel
      # without spending hours on the other tools
      aseq)       ARMS=("${ARMS_SUBMISSION[@]:0:2}") ;;
      legacy)     ARMS=("${ARMS_FULL[@]}") ;;
      *) echo "unknown ARM_SET: $ARM_SET (want submission|aseq|legacy)" >&2; exit 2 ;;
    esac
    [[ "$ENABLE_FETCHNGS" == "1" ]] && ARMS+=("$FETCHNGS_ARM")
}

# ---- 3d: worker-count sweep (adaptiSeq only) --------------------------------
#
# ONE variable: -j. Everything else stays at the value the other panels use, so a
# difference between these arms can only be the worker count. This is deliberately
# NOT a grid -- meta-jobs and --max-conns-per-host are held fixed (the latter is
# auto = jobs x max_segments, so it scales with -j and never binds).
#
# D0 is 8 files, so -j 8 is one worker per file and -j 16 is deliberately past the
# work available: it measures the saturation point, not a bigger number. Going
# beyond 16 would only re-measure "there are only 8 files".
build_sweep_arms() {
    ARMS=()
    for j in 4 8 16; do
        ARMS+=("adaptiseq-j${j}|adaptiseq|$ASEQ -i \$LIST -g --no-adaptive -j ${j} --meta-jobs 8 -Q -o .")
    done
    # Adaptive at the same ceiling: does the controller find the fixed optimum?
    ARMS+=("adaptiseq-adaptive-j16|adaptiseq|$ASEQ -i \$LIST -g --adaptive -j 16 --meta-jobs 8 -Q -o .")
    # NEW: explore-then-exploit controller at the same ceiling.
    ARMS+=("adaptiseq-climb-j16|adaptiseq|ASEQ_ADAPTIVE_MODE=climb ASEQ_PROBE_WINDOW=8 $ASEQ -i \$LIST -g --adaptive -j 16 --meta-jobs 8 -Q -o .")
}

# ---- 3jr / 3jb: fixed worker-count sweep on the submission panels ------------
#
# Is there one fixed -j that is right everywhere? Each arm is the bare released
# CLI with --no-adaptive and one -j value, on the same datasets as 3r (241 runs,
# many small files) and 3b (8 runs, 16 large files), next to the untuned default.
# Nothing else changes: segments and the per-host cap stay at their defaults
# (auto cap = jobs x max_segments), so -j is the one variable. If the best fixed
# value differs between the panels (or machines), and the default lands near the
# best in each, that is the case for the adaptive controller; if one fixed value
# wins everywhere, the paper should say so.
build_jsweep_arms() {
    ARMS=()
    for j in ${E3_JSWEEP:-1 2 4 8 16 32 64}; do
        ARMS+=("adaptiseq-fixed-j${j}|adaptiseq|$ASEQ_CLI -i \$LIST -g --no-adaptive -j ${j} -o .")
    done
    ARMS+=("${ARMS_SUBMISSION[0]}")   # adaptiseq-default, untuned
}

# ---- 4r / 4b / 4s / 4g: controller tournament -------------------------------
#
# Which adaptive controller should be the default? Every candidate runs with
# --adaptive and the released defaults otherwise, next to fixed -j 20 (and the
# best fixed value from the 3jr/3jb sweep, E3_CTRL_FIXED), on each archive the
# paper says adaptiSeq reaches: ENA many small files (4r, D1_full) and large
# files (4b, D2_subset), NCBI's .sra copies on AWS (4s: the 3b runs with -d sra,
# .sra kept, checked against reference copies), and GSA (4g, download.cncb.ac.cn).
# DDBJ and GEO accessions resolve to ENA/NCBI files, so they add no new server;
# they get a routing check (4x), not a tournament panel.
build_ctrl_arms() {
    local flags="$1"
    ARMS=()
    for c in ${E3_CONTROLLERS:-topdown bottomup budget greedy}; do
        ARMS+=("adaptiseq-ctrl-${c}|adaptiseq|$ASEQ_CLI -i \$LIST ${flags} --adaptive --controller ${c} -o .")
    done
    for j in ${E3_CTRL_FIXED:-20}; do
        ARMS+=("adaptiseq-fixed-j${j}|adaptiseq|$ASEQ_CLI -i \$LIST ${flags} --no-adaptive -j ${j} -o .")
    done
}

# ---- 3s: connections-per-worker sweep (--max-segments) ----------------------
#
# Runs on D3_seg (2 files x ~11.5 GB), NOT D0. segments/file =
# min(max_segments, size // segment_size): an 11.5 GB file offers 22 at the 512 MB
# default, so 4/8/16 genuinely give 4/8/16 connections per worker. On D0's
# 1.1-2.0 GB files every setting collapses to 2-3 segments and the sweep would be
# a flat line dressed up as a result.
#
# -j 4 with 2 files => 2 workers, so total connections = 2 x max_segments. Since
# the per-host cap is auto (jobs x max_segments), it never binds here -- this
# isolates per-worker segmentation as the only variable.
build_seg_arms() {
    ARMS=()
    for ms in 4 8 16; do
        ARMS+=("adaptiseq-seg${ms}|adaptiseq|$ASEQ -i \$LIST -g --no-adaptive -j 4 --max-segments ${ms} --meta-jobs 8 -Q -o .")
    done
}

# ---- panel runner -----------------------------------------------------------
run_panel() {
    local panel="$1" dataset="$2" reps="$3" timeout_s="$4"
    local list="$DATASETS/${dataset}.txt"
    local manifest="$DATASETS/${dataset}.manifest"

    if [[ ! -f "$list" || ! -f "$manifest" ]]; then
        echo "[ERROR] missing $list or $manifest -- run: python bench/e3/make_datasets.py" >&2
        return 1
    fi
    export E3_TIMEOUT="$timeout_s"

    echo "############################################################" >&2
    echo "# panel $panel  dataset=$dataset  reps=$reps (from rep $E3_REP_FIRST)  arms=${#ARMS[@]}  timeout=${timeout_s}s" >&2
    echo "############################################################" >&2

    local orderf="$E3_LOGS/arm_order.tsv"
    [[ -f "$orderf" ]] || printf 'panel\trep\tseed\torder_idx\tarm\n' > "$orderf"

    for rep in $(seq "$E3_REP_FIRST" "$((E3_REP_FIRST + reps - 1))"); do
        # A fresh seeded permutation every rep. (`shuf --random-source=<(yes N)`,
        # used before, is not one: the repeating byte stream left most arms in the
        # same position in every rep.) The seed mixes panel and rep so the two
        # panels do not share an order; a str seed is hashed with sha512, so the
        # order is the same on every machine and Python 3 version.
        local seed="${E3_SEED}:${panel}:${rep}"
        mapfile -t shuffled < <(printf '%s\n' "${ARMS[@]}" | "$E3_PYTHON" -c '
import random, sys
arms = [ln for ln in sys.stdin.read().split("\n") if ln]
random.Random(sys.argv[1]).shuffle(arms)
print("\n".join(arms))' "$seed")
        if [[ ${#shuffled[@]} -ne ${#ARMS[@]} ]]; then
            echo "[ERROR] arm shuffle returned ${#shuffled[@]} of ${#ARMS[@]} arms" >&2
            return 1
        fi
        local idx=0
        for entry in "${shuffled[@]}"; do
            idx=$((idx + 1))
            IFS='|' read -r arm tool cmd <<< "$entry"
            printf '%s\t%s\t%s\t%s\t%s\n' "$panel" "$rep" "$seed" "$idx" "$arm" >> "$orderf"
            run_arm "$panel" "$dataset" "$arm" "$tool" "$rep" "$idx" \
                    "$list" "$manifest" "$cmd"
        done
    done
}

# ---- panels -----------------------------------------------------------------
case "$PANEL" in
  # Cheap end-to-end validation of every arm + the verifier + the TSV, on 3 tiny
  # files. Run this FIRST on Expanse; a broken competitor invocation costs 2
  # minutes here instead of 12 hours inside panel 3a.
  smoke) build_arms;     run_panel smoke "SMOKE_D1"           "${REPS_ARG:-1}"  "${E3_TIMEOUT_SMOKE:-300}" ;;
  3a)  build_arms;       run_panel 3a "D1_fair_PRJNA916347"   "${REPS_ARG:-5}"  "${E3_TIMEOUT_3A:-3600}" ;;
  3r)  build_arms;       run_panel 3r "D1_full_PRJNA916347"   "${REPS_ARG:-5}"  "${E3_TIMEOUT_3R:-5400}" ;;
  3b)  build_arms;       run_panel 3b "D2_subset_PRJNA762469" "${REPS_ARG:-5}"  "${E3_TIMEOUT_3B:-7200}" ;;
  3c)  build_arms;       run_panel 3c "D4_mixed"              "${REPS_ARG:-5}"  "${E3_TIMEOUT_3C:-3600}" ;;
  3d)  build_sweep_arms; run_panel 3d "D0_sweep_PRJNA762469"  "${REPS_ARG:-3}"  "${E3_TIMEOUT_3D:-5400}" ;;
  3s)  build_seg_arms;   run_panel 3s "D3_seg_PRJNA540705"    "${REPS_ARG:-3}"  "${E3_TIMEOUT_3S:-5400}" ;;
  3jr) build_jsweep_arms; run_panel 3jr "D1_full_PRJNA916347"  "${REPS_ARG:-3}"  "${E3_TIMEOUT_3R:-5400}" ;;
  3jb) build_jsweep_arms; run_panel 3jb "D2_subset_PRJNA762469" "${REPS_ARG:-3}" "${E3_TIMEOUT_3B:-7200}" ;;
  4r)  build_ctrl_arms "-g"; run_panel 4r "D1_full_PRJNA916347"  "${REPS_ARG:-3}" "${E3_TIMEOUT_CTRL:-7200}" ;;
  4b)  build_ctrl_arms "-g"; run_panel 4b "D2_subset_PRJNA762469" "${REPS_ARG:-3}" "${E3_TIMEOUT_CTRL:-7200}" ;;
  4s)  build_ctrl_arms "-d sra"; run_panel 4s "S1_sra_PRJNA762469" "${REPS_ARG:-3}" "${E3_TIMEOUT_CTRL:-7200}" ;;
  4g)  build_ctrl_arms ""; run_panel 4g "G1_gsa_CRA002399"     "${REPS_ARG:-3}" "${E3_TIMEOUT_CTRL:-7200}" ;;
  4x)  ARMS=("adaptiseq-default|adaptiseq|$ASEQ_CLI -i \$LIST -g -o .")
       run_panel 4x "X1_routing"                                 "${REPS_ARG:-1}" "${E3_TIMEOUT_CTRL:-7200}" ;;
  all)
      for p in ${PANELS:-3a 3r 3b 3c 3d 3s}; do
          bash "$E3_DIR/run_e3.sh" "$p" "$REPS_ARG"
      done
      ;;
  *) echo "unknown panel: $PANEL (want smoke|3a|3r|3b|3c|3d|3s|3jr|3jb|4r|4b|4s|4g|4x|all)" >&2; exit 2 ;;
esac

echo >&2
echo "=== results: $E3_TSV ===" >&2
column -t -s $'\t' "$E3_TSV" 2>/dev/null | tail -30 >&2 || true
