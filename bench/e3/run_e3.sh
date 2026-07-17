#!/usr/bin/env bash
# E3 -- Batch download (HEADLINE, Fig 3). Driver.
#
# Panels:
#   3a  overhead-dominated  (D1_fair, 201 runs / 4.4 GB)   -- fair timing, all tools complete
#   3r  robustness          (D1_full, 241 runs / 7.6 GB)   -- runs-completed; iseq drops the 3-file runs
#   3b  byte-dominated      (D2_subset, 8 runs / 25.9 GB)  -- honesty panel
#   3c  cross-database      (D4_mixed, 20 accessions)      -- ENA + SRA-only + GSA routing
#   3d  concurrency sweep   (D0_sweep, 4 runs / 11.9 GB)   -- -j and --meta-jobs (feeds E9)
#
# Usage:  bash bench/e3/run_e3.sh <panel> [reps]
#         PANELS="3a 3b" bash bench/e3/run_e3.sh all
#
# Fairness protocol enforced here (EXPERIMENT_PLAN §12):
#   * every arm downloads the same list, in the same job, on the same node;
#   * arm order is RESHUFFLED every rep (seeded, logged) so no arm keeps a
#     systematic cold/warm-cache position -- this subsumes BENCHMARK.md's
#     reversed-order control and generalizes it to all 10 arms;
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
export E3_TSV="$E3_OUT/e3_results.tsv"
e3_init_results "$E3_TSV"
[[ -f "$E3_LOGS/trajectories.tsv" ]] || printf 'arm\trep\tline\n' > "$E3_LOGS/trajectories.tsv"

ISEQ_BIN="${ISEQ_BIN:-iseq}"

# adaptiSeq arms run through aseq_run.py: same code path as the bare CLI
# (cli.main -> core.run), but with the batch controller's INFO logging on so the
# per-probe gate.active decisions are recorded. Set ASEQ=adaptiseq to use the
# bare CLI instead (you then lose the internal trajectory, not any behaviour).
ASEQ="${ASEQ:-$E3_PYTHON $E3_DIR/aseq_run.py}"

# ---- arm table --------------------------------------------------------------
# "arm_name|tool|command".  $LIST / $IDS_CSV are exported by run_arm; CWD is a
# fresh empty dir.  Every arm is asked for gzip FASTQ from ENA so the formats are
# comparable; md5 checking is left ON for every tool that offers it (we do NOT
# pass adaptiSeq's -k), because integrity is part of what these tools are for.
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
)
FETCHNGS_ARM="fetchngs|fetchngs|nextflow run nf-core/fetchngs -r 1.12.0 --input \$IDS_CSV --outdir . -profile singularity --download_method ftp -ansi-log false"

build_arms() {
    ARMS=("${ARMS_FULL[@]}")
    [[ "$ENABLE_FETCHNGS" == "1" ]] && ARMS+=("$FETCHNGS_ARM")
}

# ---- meta-jobs / -j sweep arms (panel 3d, adaptiSeq only) -------------------
#
# CONFOUND (measured, not theoretical): raising -j alone cannot raise download
# concurrency past --max-conns-per-host, because HostGuard is a process-wide cap
# acquired before every segment connection. On D0/D2 (~1.6 GB files -> 3 segments
# each) the default cap of 8 binds at ~3 in-flight files, so -j 16/32/64 would
# all measure the SAME thing and the "scaling" curve would be an artefact of our
# own default. So the sweep varies the cap alongside -j, and the cap sweep is
# what actually locates the knee E9 is after.
build_sweep_arms() {
    ARMS=()
    for mj in 1 3 8 16; do
        ARMS+=("adaptiseq-mj${mj}|adaptiseq|$ASEQ -i \$LIST -g --no-adaptive -j 20 --meta-jobs ${mj} -Q -o .")
    done
    # -j sweep at the DEFAULT cap: expected to saturate once the cap binds.
    # That saturation is a reportable result, not a failed arm.
    for j in 1 2 4 8 16 32 64; do
        ARMS+=("adaptiseq-j${j}|adaptiseq|$ASEQ -i \$LIST -g --no-adaptive -j ${j} --meta-jobs 8 -Q -o .")
    done
    # Cap sweep at fixed -j 32: isolates the per-host cap as the real knob.
    for cap in 2 4 8 16 32; do
        ARMS+=("adaptiseq-j32-cap${cap}|adaptiseq|$ASEQ -i \$LIST -g --no-adaptive -j 32 --max-conns-per-host ${cap} --meta-jobs 8 -Q -o .")
    done
    ARMS+=("adaptiseq-adaptive-j64|adaptiseq|$ASEQ -i \$LIST -g --adaptive -j 64 --meta-jobs 8 -Q -o .")
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
    echo "# panel $panel  dataset=$dataset  reps=$reps  arms=${#ARMS[@]}  timeout=${timeout_s}s" >&2
    echo "############################################################" >&2

    for rep in $(seq 1 "$reps"); do
        # Reshuffle arm order every rep, seeded by rep for reproducibility.
        mapfile -t shuffled < <(printf '%s\n' "${ARMS[@]}" | shuf --random-source=<(yes "$rep"))
        local idx=0
        for entry in "${shuffled[@]}"; do
            idx=$((idx + 1))
            IFS='|' read -r arm tool cmd <<< "$entry"
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
  3a)  build_arms;       run_panel 3a "D1_fair_PRJNA916347"   "${REPS_ARG:-10}" "${E3_TIMEOUT_3A:-3600}" ;;
  3r)  build_arms;       run_panel 3r "D1_full_PRJNA916347"   "${REPS_ARG:-3}"  "${E3_TIMEOUT_3R:-5400}" ;;
  3b)  build_arms;       run_panel 3b "D2_subset_PRJNA762469" "${REPS_ARG:-5}"  "${E3_TIMEOUT_3B:-7200}" ;;
  3c)  build_arms;       run_panel 3c "D4_mixed"              "${REPS_ARG:-5}"  "${E3_TIMEOUT_3C:-3600}" ;;
  3d)  build_sweep_arms; run_panel 3d "D0_sweep_PRJNA762469"  "${REPS_ARG:-3}"  "${E3_TIMEOUT_3D:-5400}" ;;
  all)
      for p in ${PANELS:-3a 3r 3b 3c 3d}; do
          bash "$E3_DIR/run_e3.sh" "$p" "$REPS_ARG"
      done
      ;;
  *) echo "unknown panel: $PANEL (want smoke|3a|3r|3b|3c|3d|all)" >&2; exit 2 ;;
esac

echo >&2
echo "=== results: $E3_TSV ===" >&2
column -t -s $'\t' "$E3_TSV" 2>/dev/null | tail -30 >&2 || true
