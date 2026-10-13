#!/usr/bin/env bash
# E8 -- Resource profile (Fig 6, mirrors iSeq Fig 1D). Driver.
#
# Panels (see docs/EXPERIMENT_PLAN_E8.md):
#   8-ENA  one ~1.6 GB ENA .fastq.gz fetch   adaptiseq vs iseq vs kingfisher
#   8-SRA  one .sra -> fasterq-dump fetch     + prefetch (SRA-Toolkit)
#
# Usage:  bash bench/e8/run_e8.sh <panel> [reps]
#         PANELS="8-ENA" bash bench/e8/run_e8.sh all
#
# One node, one job, arms STRICTLY SEQUENTIAL (a co-scheduled arm would pollute the
# CPU/I/O trace of its neighbour). Payload deleted after every arm. profile_run.py
# samples the whole process tree at 2 Hz and is the SAME instrument for every tool.

set -uo pipefail

E8_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E8_DIR/../.." && pwd)"
E3_DIR="$REPO_DIR/bench/e3"

PANEL="${1:-8-ENA}"
REPS_ARG="${2:-}"

export E8_PYTHON="${E8_PYTHON:-python3}"
export E8_WORK="${E8_WORK:-/tmp/e8_work}"
export E8_OUT="${E8_OUT:-$REPO_DIR/e8_results}"
export E8_MD5_JOBS="${E8_MD5_JOBS:-8}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
export E8_HZ="${E8_HZ:-2}"
# kingfisher 0.5.0 calls `prefetch -o FILE`, deprecated in sra-tools >=3.x (exit 3).
# This env var re-enables the option so the kingfisher SRA arm works. Harmless to
# every other tool. (Found on Fabric with sra-tools 3.4.1 + kingfisher 0.5.0.)
export NCBI_VDB_PREFETCH_USES_OUTPUT_TO_FILE="${NCBI_VDB_PREFETCH_USES_OUTPUT_TO_FILE:-1}"
# The SRA-only run for 8-SRA. NOT manifest-scored (SRA sizes are not in ENA).
# VERIFY it is ~0.5-2 GB before the run (see plan §2) and override on the day.
export E8_SRA_ACC="${E8_SRA_ACC:-SRR1031060}"

mkdir -p "$E8_WORK" "$E8_OUT"
export E8_LOGS="$E8_OUT/logs"; mkdir -p "$E8_LOGS"

_e8_cleanup() {
    local rc=$?; trap - EXIT INT TERM
    [[ -n "${E8_WORK:-}" && -d "$E8_WORK" ]] && rm -rf "${E8_WORK:?}"/* 2>/dev/null || true
    exit $rc
}
trap _e8_cleanup EXIT INT TERM
[[ -n "$(ls -A "$E8_WORK" 2>/dev/null)" ]] && rm -rf "${E8_WORK:?}"/* 2>/dev/null || true

TSV="$E8_OUT/e8_results.tsv"
HDR=$'panel\tdataset\tarm\ttool\trep\twall_s\texit_code\tstatus\tpeak_rss_mb\tmean_rss_mb\tmean_cpu_pct\tpeak_cpu_pct\tcpu_core_s\tread_total_mb\twrite_total_mb\tmean_write_mbps\tphase_setup_s\tphase_data_s\tphase_verify_s\tbytes_verified\tbytes_on_disk\tfiles_on_disk\tformat\tmd5_ok\thost\tstamp'
[[ -f "$TSV" ]] || printf '%s\n' "$HDR" > "$TSV"

ISEQ_BIN="${ISEQ_BIN:-iseq}"
ASEQ="${ASEQ:-$E8_PYTHON $E3_DIR/aseq_run.py}"

# profile one (arm x rep): expand $RUN/$LIST in the arm cmd from this shell's env.
profile_arm() {
    local panel="$1" dataset="$2" arm="$3" tool="$4" rep="$5" cmd="$6"
    local manifest="$7" timeout_s="$8"
    local safe="${arm//[^A-Za-z0-9_.-]/_}"
    local trace="$E8_LOGS/e8_trace_${panel}_${safe}_rep${rep}.tsv"
    echo "[$(date +%H:%M:%S)] $panel rep=$rep arm=$arm" >&2
    local man_args=()
    [[ -n "$manifest" && -f "$manifest" ]] && man_args=(--manifest "$manifest" --verify "$E3_DIR/verify_output.py")
    "$E8_PYTHON" "$E8_DIR/profile_run.py" \
        --cmd "$cmd" --workdir "$E8_WORK/${panel}_${safe}_rep${rep}" \
        --panel "$panel" --dataset "$dataset" --arm "$arm" --tool "$tool" --rep "$rep" \
        --hz "$E8_HZ" --timeout "$timeout_s" --trace "$trace" \
        --python "$E8_PYTHON" --jobs "$E8_MD5_JOBS" "${man_args[@]}" \
        >> "$TSV" 2>> "$E8_LOGS/${panel}_${safe}_rep${rep}.log"
    tail -1 "$TSV" | awk -F'\t' '{printf "    -> %ss  peakRSS=%sMB  cpu_core_s=%s  setup/data/verify=%s/%s/%s  md5=%s  %s\n",$6,$9,$13,$17,$18,$19,$24,$8}' >&2
}

# ---- ENA single-run list + manifest (derived from D2_subset) -----------------
make_ena_run() {
    local base="$DATASETS/D2_subset_PRJNA762469"
    [[ -f "$base.txt" ]] || { echo "[ERROR] $base.txt missing -- run make_datasets.py" >&2; return 1; }
    RUN=$(head -1 "$base.txt")
    LIST="$E8_WORK/ena_run.txt"; echo "$RUN" > "$LIST"
    ENA_MAN="$E8_WORK/ena_run.manifest"
    head -1 "$base.manifest" > "$ENA_MAN"
    grep -P "^${RUN}\t" "$base.manifest" >> "$ENA_MAN"
    export RUN LIST
}

make_sra_run() {
    RUN="$E8_SRA_ACC"
    LIST="$E8_WORK/sra_run.txt"; echo "$RUN" > "$LIST"
    export RUN LIST
}

run_ena() {
    local reps="${1:-5}"; local to="${E8_TIMEOUT_ENA:-1800}"
    make_ena_run || return 1
    echo "[8-ENA] run=$RUN  manifest=$ENA_MAN" >&2
    declare -a arms=(
      "adaptiseq|adaptiseq|$ASEQ -i \$LIST -g -j 4 -Q -o ."
      "iseq|iseq|$ISEQ_BIN -i \$LIST -g -o ."
      "kingfisher|kingfisher|kingfisher get -r \$RUN -m ena-ftp --output-directory . --check-md5sums"
    )
    for rep in $(seq 1 "$reps"); do
        for entry in "${arms[@]}"; do
            IFS='|' read -r arm tool cmd <<< "$entry"
            profile_arm 8-ENA D2_subset "$arm" "$tool" "$rep" "$cmd" "$ENA_MAN" "$to"
        done
    done
}

run_sra() {
    local reps="${1:-5}"; local to="${E8_TIMEOUT_SRA:-2400}"
    make_sra_run
    echo "[8-SRA] run=$RUN (NOT manifest-scored; verify ~0.5-2 GB)" >&2
    declare -a arms=(
      "adaptiseq|adaptiseq|$ASEQ -i \$LIST -g -j 4 -Q -o ."
      "iseq|iseq|$ISEQ_BIN -i \$LIST -g -o ."
      "kingfisher|kingfisher|kingfisher get -r \$RUN -m prefetch --output-directory ."
      "prefetch|prefetch|prefetch -O . \$RUN && vdb-validate ./\$RUN 2>/dev/null; true"
    )
    for rep in $(seq 1 "$reps"); do
        for entry in "${arms[@]}"; do
            IFS='|' read -r arm tool cmd <<< "$entry"
            profile_arm 8-SRA "$RUN" "$arm" "$tool" "$rep" "$cmd" "" "$to"
        done
    done
}

case "$PANEL" in
  smoke)  E8_TIMEOUT_ENA=600 run_ena "${REPS_ARG:-1}" ;;
  8-ENA)  run_ena "${REPS_ARG:-5}" ;;
  8-SRA)  run_sra "${REPS_ARG:-5}" ;;
  all)
      for p in ${PANELS:-8-ENA 8-SRA}; do
          bash "$E8_DIR/run_e8.sh" "$p" "$REPS_ARG"
      done ;;
  *) echo "unknown panel: $PANEL (want smoke|8-ENA|8-SRA|all)" >&2; exit 2 ;;
esac

echo >&2
echo "=== E8 results: $TSV ===" >&2
column -t -s $'\t' "$TSV" 2>/dev/null | tail -12 >&2 || true
