#!/usr/bin/env bash
# Shared measurement machinery for E7 (reliability). Sourced by run_e7.sh.
#
# Reuses E3's judge (bench/e3/verify_output.py): success and bytes are decided by
# md5 against the ENA manifest, never by a tool's exit code. run_corpus_arm handles
# the corpus sub-experiments (E7a success/integrity, E7e 3-file completion); the
# resume (E7b) and engine (E7c/E7d) sub-experiments have their own harnesses.
#
# Payload is deleted after every arm -- bounded disk AND the cold-cache control.

set -uo pipefail

E3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../e3" && pwd)"   # reuse verify_output.py

E7_CORPUS_HEADER=$'subexp\tdataset\tarm\ttool\trep\twall_s\texit_code\tstatus\truns_complete\truns_partial\truns_expected\tfiles_verified\tfiles_expected\tbytes_verified\tbytes_expected\tmd5_pass_rate\tretries\tfail_log_n\tformat\thost\tstamp'
E7_RESUME_HEADER=$'subexp\ttool\tfile_bytes\tkill_frac\toffset_at_kill\tresume_start_bytes\tbytes_wasted\tresumed\tfinal_md5_ok\twall_resume_s\tverdict\tkill_status\trep\thost\tstamp'
E7_ENGINE_HEADER=$'subexp\tcheck\tmode\tpassed\tdetail\trep\thost\tstamp'

e7_init() {
    [[ -f "$1" ]] || printf '%s\n' "$2" > "$1"
}

# run_corpus_arm <subexp> <dataset> <arm> <tool> <rep> <list> <manifest> <cmd>
run_corpus_arm() {
    local subexp="$1" dataset="$2" arm="$3" tool="$4" rep="$5"
    local list="$6" manifest="$7" cmd="$8"

    local safe_arm="${arm//[^A-Za-z0-9_.-]/_}"
    local dir="$E7_WORK/${subexp}_${dataset}_${safe_arm}_rep${rep}"
    local logf="$E7_LOGS/${subexp}_${dataset}_${safe_arm}_rep${rep}.log"
    rm -rf "$dir"; mkdir -p "$dir"

    echo "[$(date +%H:%M:%S)] $subexp rep=$rep arm=$arm dataset=$dataset (timeout ${E7_TIMEOUT}s)" >&2

    local t0 t1 rc
    t0=$(date +%s.%N)
    (
        cd "$dir" || exit 127
        export LIST="$list"
        timeout --kill-after=60 "$E7_TIMEOUT" bash -c "$cmd"
    ) > "$logf" 2>&1
    rc=$?
    t1=$(date +%s.%N)

    local wall status
    wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.2f", b-a}')
    status="ok"
    if   [[ $rc -eq 124 || $rc -eq 137 ]]; then status="TIMEOUT"
    elif [[ $rc -ne 0 ]];                  then status="rc=$rc"; fi

    # The manifest is the judge (reused from E3).
    local v
    v=$("$E7_PYTHON" "$E3_DIR/verify_output.py" \
            --manifest "$manifest" --outdir "$dir" --jobs "$E7_MD5_JOBS" 2>>"$logf")
    [[ -z "$v" ]] && v="runs_complete=0 runs_partial=0 runs_expected=0 files_verified=0 files_expected=0 bytes_verified=0 bytes_expected=0 bytes_on_disk=0 files_on_disk=0 extra_files=0 format=-"
    local runs_complete runs_partial runs_expected files_verified files_expected
    local bytes_verified bytes_expected bytes_on_disk files_on_disk extra_files format
    eval "$v"

    # md5 pass rate = verified files / expected files (the integrity number for Table 3).
    local md5_rate
    md5_rate=$(awk -v a="$files_verified" -v b="$files_expected" \
               'BEGIN{printf "%.4f", (b>0)? a/b : 0}')

    # Retry rounds + fail.log entries: both adaptiSeq and iseq write these. Count
    # re-download rounds from the log, and fail.log lines from the arm's dir.
    local retries fail_n
    retries=$(grep -ci "re-download\|retry\|retrying\|round [0-9]" "$logf" 2>/dev/null || echo 0)
    fail_n=$(find "$dir" -maxdepth 3 -name 'fail.log' -exec cat {} \; 2>/dev/null | grep -c . || echo 0)

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$subexp" "$dataset" "$arm" "$tool" "$rep" "$wall" "$rc" "$status" \
        "$runs_complete" "$runs_partial" "$runs_expected" \
        "$files_verified" "$files_expected" "$bytes_verified" "$bytes_expected" \
        "$md5_rate" "$retries" "$fail_n" "$format" \
        "$(hostname -s)" "$(date -Is)" \
        >> "$E7_CORPUS_TSV"

    echo "    -> ${wall}s  runs=${runs_complete}/${runs_expected}  md5=${md5_rate}  retries=${retries}  fail.log=${fail_n}  ${status}" >&2
    rm -rf "$dir"
}
