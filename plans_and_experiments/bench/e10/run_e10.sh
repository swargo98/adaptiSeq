#!/usr/bin/env bash
# E10 -- Parallel metadata resolution & rate-limit etiquette (Fig 8 + Table 4).
# Driver. Mirrors run_e8.sh / run_e5.sh structure.
#
# Panels (see docs/EXPERIMENT_PLAN_E10.md):
#   10a  resolution throughput   adaptiseq resolve_all sweep + iseq/pysradb/ffq/kingfisher
#   10b  overlap value           resolution wall as fraction of end-to-end (mj 1 vs 8)
#   10c  etiquette proof         real RateLimiter, meta-jobs sweep, limiter vs naive (local)
#
# Usage:  bash bench/e10/run_e10.sh <panel> [reps]
#         PANELS="10a 10c" bash bench/e10/run_e10.sh all
#
# Resolution only -- NO sequencing bytes are transferred. 10c needs no network.

set -uo pipefail

E10_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E10_DIR/../.." && pwd)"

PANEL="${1:-10a}"
REPS_ARG="${2:-}"

export E10_PYTHON="${E10_PYTHON:-python3}"
export E10_OUT="${E10_OUT:-$REPO_DIR/e10_results}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
export E10_ENA_LIST="${E10_ENA_LIST:-$DATASETS/E10_ena_PRJNA916347.txt}"
export E10_MIXED_LIST="${E10_MIXED_LIST:-$DATASETS/D4_mixed.txt}"
# N for the adaptiseq sweep; Expanse overrides to "100,500,2000".
export E10_NS="${E10_NS:-50,150}"
export E10_META_JOBS="${E10_META_JOBS:-1,3,8,16}"
export E10_REPS="${E10_REPS:-${REPS_ARG:-3}}"
export E10_COMP_TOOLS="${E10_COMP_TOOLS:-iseq,pysradb,ffq,kingfisher}"
export E10_N_COMP="${E10_N_COMP:-20}"
export E10_COMP_REPS="${E10_COMP_REPS:-2}"

mkdir -p "$E10_OUT"
export E10_LOGS="$E10_OUT/logs"; mkdir -p "$E10_LOGS"

RESOLVE_TSV="$E10_OUT/e10_resolve.tsv"
ETIQ_TSV="$E10_OUT/e10_etiquette.tsv"
R_HDR=$'panel\tdataset\ttool\tmeta_jobs\tn_acc\trep\twall_s\tacc_per_s\tn_tasks\tn_unresolved\tena_reqs\tgsa_reqs\tncbi_reqs\thost\tstamp'
E_HDR=$'arm\tncbi_key\tmeta_jobs\tendpoint\tcap_rps\tn_requests\twall_s\tmean_rps\tpeak_rps_1s\tover_cap\thost\tstamp'
[[ -f "$RESOLVE_TSV" ]] || printf '%s\n' "$R_HDR" > "$RESOLVE_TSV"
[[ -f "$ETIQ_TSV" ]]    || printf '%s\n' "$E_HDR"  > "$ETIQ_TSV"

run_10a() {
    echo "[10a] resolution throughput: adaptiseq sweep + competitors" >&2
    local IFS=,
    for n in $E10_NS; do
        echo "[10a] adaptiseq N=$n meta_jobs={$E10_META_JOBS} reps=$E10_REPS" >&2
        "$E10_PYTHON" "$E10_DIR/resolve_bench.py" --panel 10a \
            --dataset "$E10_ENA_LIST" --n "$n" --meta-jobs "$E10_META_JOBS" \
            --reps "$E10_REPS" --tools adaptiseq \
            >> "$RESOLVE_TSV" 2>> "$E10_LOGS/10a_adaptiseq_N${n}.log"
    done
    # competitors (serial CLIs) on the small comparable N, once
    echo "[10a] competitors: $E10_COMP_TOOLS N=$E10_N_COMP reps=$E10_COMP_REPS" >&2
    "$E10_PYTHON" "$E10_DIR/resolve_bench.py" --panel 10a \
        --dataset "$E10_ENA_LIST" --n "$E10_N_COMP" --tools "$E10_COMP_TOOLS" \
        --n-comp "$E10_N_COMP" --comp-reps "$E10_COMP_REPS" \
        >> "$RESOLVE_TSV" 2>> "$E10_LOGS/10a_competitors.log"
    # mixed multi-DB list (adaptiseq only) -- exercises the preference chain
    echo "[10a] adaptiseq mixed multi-DB list (D4_mixed)" >&2
    "$E10_PYTHON" "$E10_DIR/resolve_bench.py" --panel 10a-mixed \
        --dataset "$E10_MIXED_LIST" --n 20 --meta-jobs "$E10_META_JOBS" \
        --reps 2 --tools adaptiseq \
        >> "$RESOLVE_TSV" 2>> "$E10_LOGS/10a_mixed.log"
    tail -1 "$RESOLVE_TSV" >/dev/null
}

run_10b() {
    echo "[10b] overlap value: resolution wall mj=1 vs mj=8 (N=150)" >&2
    "$E10_PYTHON" "$E10_DIR/resolve_bench.py" --panel 10b \
        --dataset "$E10_ENA_LIST" --n 150 --meta-jobs 1,8 \
        --reps "$E10_REPS" --tools adaptiseq \
        >> "$RESOLVE_TSV" 2>> "$E10_LOGS/10b.log"
}

run_10c() {
    echo "[10c] etiquette proof: real RateLimiter, limiter vs naive (local)" >&2
    "$E10_PYTHON" "$E10_DIR/etiquette_probe.py" \
        --n 120 --meta-jobs "$E10_META_JOBS" --latency 0.05 \
        --arms limiter,naive --key-modes nokey,key \
        >> "$ETIQ_TSV" 2>> "$E10_LOGS/10c.log"
    column -t -s $'\t' "$ETIQ_TSV" 2>/dev/null | tail -n +1 | sed -n '1,40p' >&2 || true
}

case "$PANEL" in
  smoke)
      E10_NS=20 E10_META_JOBS="1,8" E10_REPS=1 E10_COMP_TOOLS=iseq \
        E10_N_COMP=8 E10_COMP_REPS=1 run_10a
      E10_META_JOBS="1,8" run_10c ;;
  10a) run_10a ;;
  10b) run_10b ;;
  10c) run_10c ;;
  all)
      for p in ${PANELS:-10a 10b 10c}; do
          bash "$E10_DIR/run_e10.sh" "$p" "$REPS_ARG"
      done ;;
  *) echo "unknown panel: $PANEL (want smoke|10a|10b|10c|all)" >&2; exit 2 ;;
esac

echo >&2
echo "=== E10 resolve: $RESOLVE_TSV ===" >&2
column -t -s $'\t' "$RESOLVE_TSV" 2>/dev/null | tail -14 >&2 || true
echo "=== E10 etiquette: $ETIQ_TSV ===" >&2
column -t -s $'\t' "$ETIQ_TSV" 2>/dev/null | tail -14 >&2 || true
