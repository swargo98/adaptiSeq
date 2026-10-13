#!/usr/bin/env bash
# E5 -- Adaptive Aspera, efficiency hysteresis (Fig 5). Driver.
#
# Panels (see docs/EXPERIMENT_PLAN_E5.md):
#   5a  trajectory     adaptive only  -> additive-increase -> collapse -> settle
#   5b  vs fixed       adaptive + fixed-j{1,2,4,8}  -> aggregate MB/s
#   5c  sensitivity    adaptive @ --aspera-efficiency {0.5,0.7,0.9}
#
# Usage:  bash bench/e5/run_e5.sh <panel> [reps]
#         PANELS="5a 5b" bash bench/e5/run_e5.sh all
#
# Real ascp only; the manifest is the judge; ascp killed between arms so no stray
# session leaks into the next arm's throughput meter. Arms strictly sequential.

set -uo pipefail

E5_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E5_DIR/../.." && pwd)"
E3_DIR="$REPO_DIR/bench/e3"
source "$E5_DIR/e5_lib.sh"

PANEL="${1:-5a}"
REPS_ARG="${2:-}"

export E5_PYTHON="${E5_PYTHON:-python3}"
export E5_WORK="${E5_WORK:-/tmp/e5_work}"
export E5_OUT="${E5_OUT:-$REPO_DIR/e5_results}"
export E5_MD5_JOBS="${E5_MD5_JOBS:-8}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
export E5_TIMEOUT="${E5_TIMEOUT:-1800}"

mkdir -p "$E5_WORK" "$E5_OUT"
export E5_LOGS="$E5_OUT/logs"; mkdir -p "$E5_LOGS"

_e5_cleanup() {
    local rc=$?; trap - EXIT INT TERM
    pkill -9 ascp 2>/dev/null || true
    [[ -n "${E5_WORK:-}" && -d "$E5_WORK" ]] && rm -rf "${E5_WORK:?}"/* 2>/dev/null || true
    exit $rc
}
trap _e5_cleanup EXIT INT TERM
pkill -9 ascp 2>/dev/null || true
[[ -n "$(ls -A "$E5_WORK" 2>/dev/null)" ]] && rm -rf "${E5_WORK:?}"/* 2>/dev/null || true

export E5_TSV="$E5_OUT/e5_results.tsv"
e5_init "$E5_TSV"
[[ -f "$E5_LOGS/trajectories.tsv" ]] || printf 'arm\trep\tworkers\tthroughput\tefficiency\n' > "$E5_LOGS/trajectories.tsv"

# Aspera CLI through the trajectory-logging wrapper (same core.run path).
ASEQ="${ASEQ:-$E5_PYTHON $E5_DIR/aspera_run.py}"
DATASET="${E5_DATASET:-E5_aspera_PRJNA916347}"
LIST="$DATASETS/${DATASET}.txt"
MAN="$DATASETS/${DATASET}.manifest"

run_panel() {
    local panel="$1" reps="$2"; shift 2
    local arms=("$@")
    if [[ ! -f "$LIST" || ! -f "$MAN" ]]; then
        echo "[ERROR] missing $LIST / $MAN" >&2; return 1
    fi
    echo "############ panel $panel  reps=$reps  arms=${#arms[@]} ############" >&2
    for rep in $(seq 1 "$reps"); do
        for entry in "${arms[@]}"; do
            IFS='|' read -r arm cmd <<< "$entry"
            run_aspera_arm "$panel" "$arm" "$rep" "$LIST" "$MAN" "$cmd"
        done
    done
}

ADAPT="$ASEQ -a -g -i \$LIST --adaptive -j 8 --aspera-efficiency 0.7 --probe-window 15 -Q -o ."

case "$PANEL" in
  smoke)  # 1 rep adaptive only -- validate the whole path cheaply
      run_panel smoke "${REPS_ARG:-1}" "adaptive|$ADAPT" ;;
  5a)
      run_panel 5a "${REPS_ARG:-2}" "adaptive|$ADAPT" ;;
  5b)
      run_panel 5b "${REPS_ARG:-2}" \
        "fixed-j1|$ASEQ -a -g -i \$LIST --no-adaptive -j 1 -Q -o ." \
        "fixed-j2|$ASEQ -a -g -i \$LIST --no-adaptive -j 2 -Q -o ." \
        "fixed-j4|$ASEQ -a -g -i \$LIST --no-adaptive -j 4 -Q -o ." \
        "fixed-j8|$ASEQ -a -g -i \$LIST --no-adaptive -j 8 -Q -o ." \
        "adaptive|$ADAPT" ;;
  5c)
      run_panel 5c "${REPS_ARG:-2}" \
        "eff-0.5|$ASEQ -a -g -i \$LIST --adaptive -j 8 --aspera-efficiency 0.5 --probe-window 15 -Q -o ." \
        "eff-0.7|$ASEQ -a -g -i \$LIST --adaptive -j 8 --aspera-efficiency 0.7 --probe-window 15 -Q -o ." \
        "eff-0.9|$ASEQ -a -g -i \$LIST --adaptive -j 8 --aspera-efficiency 0.9 --probe-window 15 -Q -o ." ;;
  all)
      for p in ${PANELS:-5a 5b 5c}; do bash "$E5_DIR/run_e5.sh" "$p" "$REPS_ARG"; done ;;
  *) echo "unknown panel: $PANEL (want smoke|5a|5b|5c|all)" >&2; exit 2 ;;
esac

echo >&2; echo "=== E5 results: $E5_TSV ===" >&2
column -t -s $'\t' "$E5_TSV" 2>/dev/null | tail -14 >&2 || true
