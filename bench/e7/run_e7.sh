#!/usr/bin/env bash
# E7 -- Reliability & resumability (Table 3). Driver.
#
# Sub-experiments (see docs/EXPERIMENT_PLAN_E7.md):
#   7a  corpus success/integrity   (D1_full, 241 runs)      iseq vs kingfisher vs adaptiseq
#   7b  resume correctness         (D3_seg, 1 x ~11.5 GB)   kill -> restart, .part offset
#   7c  never-truncate / corrupt   (local origin + 1 ENA)   deterministic engine checks
#   7d  circuit breaker            (local origin [+ Fabric live 429s])
#   7e  3-file-run completion      (D1_threefile)           iseq drops, adaptiseq completes
#
# Usage:  bash bench/e7/run_e7.sh <subexp> [reps]
#         PANELS="7a 7b" bash bench/e7/run_e7.sh all
#
# Fairness: one node, one job, strictly sequential; manifest is the judge; payload
# deleted after every trial. ≤5 reps (default 3; reps guard transient network, not
# build a distribution -- reliability is near-deterministic).

set -uo pipefail

E7_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E7_DIR/../.." && pwd)"
E3_DIR="$REPO_DIR/bench/e3"
source "$E7_DIR/e7_lib.sh"

PANEL="${1:-7a}"
REPS_ARG="${2:-}"

export E7_PYTHON="${E7_PYTHON:-python3}"
export E7_WORK="${E7_WORK:-/tmp/e7_work}"
export E7_OUT="${E7_OUT:-$REPO_DIR/e7_results}"
export E7_MD5_JOBS="${E7_MD5_JOBS:-16}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
E7_LIVE_THROTTLE="${E7_LIVE_THROTTLE:-0}"   # 1 on Fabric: capture live ENA 429s
E7_LIVE_CORRUPT="${E7_LIVE_CORRUPT:-1}"     # end-to-end md5-retry check (needs egress)

mkdir -p "$E7_WORK" "$E7_OUT"
export E7_LOGS="$E7_OUT/logs"; mkdir -p "$E7_LOGS"

# Purge payload on any exit -- a scancel / timeout / crash must not strand an
# 11.5 GB resume file. Only $E7_WORK is touched; $E7_OUT (results) is never removed.
_e7_cleanup() {
    local rc=$?; trap - EXIT INT TERM
    [[ -n "${E7_WORK:-}" && -d "$E7_WORK" ]] && rm -rf "${E7_WORK:?}"/* 2>/dev/null || true
    exit $rc
}
trap _e7_cleanup EXIT INT TERM
[[ -n "$(ls -A "$E7_WORK" 2>/dev/null)" ]] && rm -rf "${E7_WORK:?}"/* 2>/dev/null || true

export E7_CORPUS_TSV="$E7_OUT/e7_results.tsv"
export E7_RESUME_TSV="$E7_OUT/e7_resume.tsv"
export E7_ENGINE_TSV="$E7_OUT/e7_engine.tsv"
e7_init "$E7_CORPUS_TSV" "$E7_CORPUS_HEADER"
e7_init "$E7_RESUME_TSV" "$E7_RESUME_HEADER"
e7_init "$E7_ENGINE_TSV" "$E7_ENGINE_HEADER"

ISEQ_BIN="${ISEQ_BIN:-iseq}"
# Same INFO-logging wrapper as E3, so HostGuard trip lines are captured.
ASEQ="${ASEQ:-$E7_PYTHON $E3_DIR/aseq_run.py}"

emit_engine() {  # <check> <mode> <PASS|FAIL> <detail> <rep>
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "E7c-d" "$1" "$2" "$3" "$4" "$5" "$(hostname -s)" "$(date -Is)" \
        >> "$E7_ENGINE_TSV"
}

# ---- 7a: corpus success / integrity -----------------------------------------
run_7a() {
    local reps="${1:-3}"
    local list="$DATASETS/D1_full_PRJNA916347.txt"
    local man="$DATASETS/D1_full_PRJNA916347.manifest"
    export E7_TIMEOUT="${E7_TIMEOUT_7A:-7200}"
    declare -a arms=(
      "iseq|iseq|$ISEQ_BIN -i \$LIST -g -o ."
      "kingfisher|kingfisher|kingfisher get --run-identifiers-list \$LIST -m ena-ftp --output-directory . --check-md5sums"
      "adaptiseq|adaptiseq|$ASEQ -i \$LIST -g -j 8 --meta-jobs 8 -Q -o ."
    )
    for rep in $(seq 1 "$reps"); do
        for entry in "${arms[@]}"; do
            IFS='|' read -r arm tool cmd <<< "$entry"
            run_corpus_arm 7a D1_full "$arm" "$tool" "$rep" "$list" "$man" "$cmd"
        done
    done
}

# ---- 7e: 3-file-run completion ----------------------------------------------
run_7e() {
    local reps="${1:-3}"
    local list="$DATASETS/D1_threefile_PRJNA916347.txt"
    local man="$DATASETS/D1_threefile_PRJNA916347.manifest"
    export E7_TIMEOUT="${E7_TIMEOUT_7E:-3600}"
    declare -a arms=(
      "iseq|iseq|$ISEQ_BIN -i \$LIST -g -o ."
      "adaptiseq|adaptiseq|$ASEQ -i \$LIST -g -j 8 --meta-jobs 8 -Q -o ."
    )
    for rep in $(seq 1 "$reps"); do
        for entry in "${arms[@]}"; do
            IFS='|' read -r arm tool cmd <<< "$entry"
            run_corpus_arm 7e D1_threefile "$arm" "$tool" "$rep" "$list" "$man" "$cmd"
        done
    done
}

# ---- 7b: resume correctness -------------------------------------------------
# Build a single-run list+manifest from D3_seg (one ~11.5 GB file) so the judge
# scores exactly the file under test, then kill/restart at 3 fractions per tool.
make_single_run() {
    local base="$DATASETS/D3_seg_PRJNA540705"
    local run; run=$(head -1 "$base.txt")
    SINGLE_LIST="$E7_WORK/single_run.txt"
    SINGLE_MAN="$E7_WORK/single_run.manifest"
    echo "$run" > "$SINGLE_LIST"
    head -1 "$base.manifest" > "$SINGLE_MAN"
    grep -P "^${run}\t" "$base.manifest" >> "$SINGLE_MAN"
    # file_bytes = sum of that run's file sizes (single-file run => one number)
    SINGLE_BYTES=$(awk -F'\t' -v r="$run" 'NR>1 && $1==r {s+=$3} END{print s+0}' "$base.manifest")
}

run_7b() {
    local reps="${1:-3}"
    make_single_run
    if [[ -z "${SINGLE_BYTES:-}" || "$SINGLE_BYTES" -eq 0 ]]; then
        echo "[7b] could not size the resume file -- run make_datasets.py first" >&2; return 1
    fi
    echo "[7b] resume file: $(cat "$SINGLE_LIST")  ${SINGLE_BYTES} bytes" >&2
    local to="${E7_TIMEOUT_7B:-2400}"
    # --max-segments 1 forces single-stream so .part grows contiguously (§3).
    declare -a arms=(
      "adaptiseq|$ASEQ -i \$SINGLE_LIST -g -j 1 --max-segments 1 --meta-jobs 1 -Q -o ."
      "iseq|$ISEQ_BIN -i \$SINGLE_LIST -g -o ."
    )
    [[ "${E7_RESUME_KINGFISHER:-0}" == "1" ]] && arms+=(
      "kingfisher|kingfisher get --run-identifiers-list \$SINGLE_LIST -m ena-ftp --output-directory . --check-md5sums")
    for rep in $(seq 1 "$reps"); do
        for frac in 0.25 0.50 0.75; do
            for entry in "${arms[@]}"; do
                IFS='|' read -r tool cmd <<< "$entry"
                # Expand the arm command with SINGLE_LIST resolved in this shell.
                local ecmd; ecmd=$(SINGLE_LIST="$SINGLE_LIST" eval "echo \"$cmd\"")
                echo "[$(date +%H:%M:%S)] 7b rep=$rep frac=$frac tool=$tool" >&2
                "$E7_PYTHON" "$E7_DIR/resume_probe.py" \
                    --cmd "$ecmd" \
                    --workdir "$E7_WORK/7b_${tool}_${frac}_rep${rep}" \
                    --file-bytes "$SINGLE_BYTES" --kill-frac "$frac" \
                    --manifest "$SINGLE_MAN" --verify "$E3_DIR/verify_output.py" \
                    --python "$E7_PYTHON" --jobs "$E7_MD5_JOBS" \
                    --timeout "$to" --tool "$tool" --rep "$rep" \
                    >> "$E7_RESUME_TSV" 2>> "$E7_LOGS/7b_${tool}_${frac}_rep${rep}.log"
                tail -1 "$E7_RESUME_TSV" | awk -F'\t' '{print "    -> "$11" wasted="$7"/"$5" md5ok="$9}' >&2
            done
        done
    done
}

# ---- 7c: never-truncate / corruption ----------------------------------------
run_7c() {
    local reps="${1:-2}"
    for rep in $(seq 1 "$reps"); do
        for check in never_truncate short_read; do
            out=$("$E7_PYTHON" "$E7_DIR/engine_probe.py" --check "$check" \
                    --workdir "$E7_WORK/7c_${check}_rep${rep}" --python "$E7_PYTHON" \
                    2>>"$E7_LOGS/7c_${check}_rep${rep}.log") || true
            echo "  $out" >&2
            IFS=$'\t' read -r _tag ck mode verdict detail <<< "$out"
            emit_engine "$ck" "$mode" "$verdict" "$detail" "$rep"
        done
    done
    # End-to-end corruption -> md5 retry (needs live ENA; skips cleanly if no egress).
    [[ "$E7_LIVE_CORRUPT" == "1" ]] && run_7c_corrupt_live 1 || true
}

# Download the smallest SMOKE run, flip a byte, drop it from success.log, re-run:
# adaptiSeq's md5 check must detect the mismatch and re-download to a passing md5.
run_7c_corrupt_live() {
    local rep="${1:-1}"
    local dir="$E7_WORK/7c_corrupt_rep${rep}"; rm -rf "$dir"; mkdir -p "$dir"
    local run; run=$(head -1 "$DATASETS/SMOKE_D1.txt" 2>/dev/null)
    [[ -z "$run" ]] && { echo "  (7c-corrupt: no SMOKE list; skip)" >&2; return 0; }
    echo "$run" > "$dir/one.txt"
    ( cd "$dir" && timeout 300 $ASEQ -i one.txt -g -j 1 -Q -o . ) \
        >"$E7_LOGS/7c_corrupt_rep${rep}.log" 2>&1 || true
    local f; f=$(find "$dir" -name '*.fastq.gz' | head -1)
    if [[ -z "$f" ]]; then emit_engine "corruption" "live-ena" "FAIL" "download failed" "$rep"; rm -rf "$dir"; return 0; fi
    # Flip one byte and force re-verification.
    printf '\xff' | dd of="$f" bs=1 seek=100 count=1 conv=notrunc 2>/dev/null
    find "$dir" -name success.log -delete 2>/dev/null || true
    ( cd "$dir" && timeout 300 $ASEQ -i one.txt -g -j 1 -Q -o . ) \
        >>"$E7_LOGS/7c_corrupt_rep${rep}.log" 2>&1 || true
    # Judge: does the file now match the manifest md5 again?
    local v; v=$("$E7_PYTHON" "$E3_DIR/verify_output.py" \
        --manifest "$DATASETS/SMOKE_D1.manifest" --outdir "$dir" --jobs 4 2>/dev/null)
    local rc; rc=$(echo "$v" | grep -o 'runs_complete=[0-9]*' | cut -d= -f2)
    if [[ "${rc:-0}" -ge 1 ]]; then
        emit_engine "corruption" "live-ena" "PASS" "corrupt byte detected; re-downloaded to valid md5" "$rep"
    else
        emit_engine "corruption" "live-ena" "FAIL" "corruption not repaired ($v)" "$rep"
    fi
    rm -rf "$dir"
}

# ---- 7d: circuit breaker ----------------------------------------------------
run_7d() {
    local reps="${1:-2}"
    for rep in $(seq 1 "$reps"); do
        local trace="$E7_LOGS/hostguard_synth_rep${rep}.tsv"
        out=$("$E7_PYTHON" "$E7_DIR/engine_probe.py" --check circuit_breaker \
                --workdir "$E7_WORK/7d_rep${rep}" --python "$E7_PYTHON" \
                --trace "$trace" 2>>"$E7_LOGS/7d_rep${rep}.log") || true
        echo "  $out" >&2
        IFS=$'\t' read -r _tag ck mode verdict detail <<< "$out"
        emit_engine "$ck" "$mode" "$verdict" "$detail" "$rep"
    done
    # Fabric-only: the live ENA link 429/550s under high concurrency (E3 analysis).
    [[ "$E7_LIVE_THROTTLE" == "1" ]] && run_7d_live 1 || true
}

run_7d_live() {
    local rep="${1:-1}"
    local dir="$E7_WORK/7d_live_rep${rep}"; rm -rf "$dir"; mkdir -p "$dir"
    local logf="$E7_LOGS/7d_live_rep${rep}.log"
    echo "[7d-live] adaptiseq -j 40 vs live ENA (Fabric throttling)" >&2
    ( cd "$dir" && timeout "${E7_TIMEOUT_7D_LIVE:-1800}" \
        $ASEQ -i "$DATASETS/D1_fair_PRJNA916347.txt" -g -j 40 --meta-jobs 8 -Q -o . ) \
        > "$logf" 2>&1 || true
    # HostGuard trips surface as "Host pushback" / "pushback" / cap-lowering logs.
    local trips; trips=$(grep -ci "pushback\|429\|503\|breaker\|backoff" "$logf" 2>/dev/null || echo 0)
    local v; v=$("$E7_PYTHON" "$E3_DIR/verify_output.py" \
        --manifest "$DATASETS/D1_fair_PRJNA916347.manifest" --outdir "$dir" --jobs "$E7_MD5_JOBS" 2>/dev/null)
    local rc; rc=$(echo "$v" | grep -o 'runs_complete=[0-9]*' | cut -d= -f2)
    if [[ "${trips:-0}" -gt 0 ]]; then
        emit_engine "circuit_breaker" "live-ena-fabric" "PASS" "live pushbacks=$trips completed_runs=${rc:-0}" "$rep"
    else
        emit_engine "circuit_breaker" "live-ena-fabric" "INFO" "no throttling observed this window (pushbacks=0)" "$rep"
    fi
    rm -rf "$dir"
}

case "$PANEL" in
  smoke)
      # 2-minute end-to-end check of the local (network-free) machinery.
      run_7c "${REPS_ARG:-1}" ;;
  7a) run_7a "${REPS_ARG:-3}" ;;
  7b) run_7b "${REPS_ARG:-3}" ;;
  7c) run_7c "${REPS_ARG:-2}" ;;
  7d) run_7d "${REPS_ARG:-2}" ;;
  7e) run_7e "${REPS_ARG:-3}" ;;
  all)
      for p in ${PANELS:-7a 7b 7c 7d 7e}; do
          bash "$E7_DIR/run_e7.sh" "$p" "$REPS_ARG"
      done ;;
  *) echo "unknown sub-experiment: $PANEL (want smoke|7a|7b|7c|7d|7e|all)" >&2; exit 2 ;;
esac

echo >&2
echo "=== E7 results in $E7_OUT ===" >&2
for f in "$E7_CORPUS_TSV" "$E7_RESUME_TSV" "$E7_ENGINE_TSV"; do
    [[ -s "$f" ]] && { echo "--- $(basename "$f") ---" >&2; column -t -s $'\t' "$f" 2>/dev/null | tail -12 >&2; }
done
