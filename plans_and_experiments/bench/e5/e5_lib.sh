#!/usr/bin/env bash
# Shared measurement machinery for E5 (adaptive Aspera). Sourced by run_e5.sh.
#
# One function: run_aspera_arm. Runs one (arm x rep) real-ascp download, times it,
# judges the output against the ENA manifest (reused verify_output.py), scrapes the
# controller's settle point + per-probe trajectory, appends one TSV row, purges the
# payload, and -- crucially -- kills any stray ascp so it cannot leak into the next
# arm's DirGrowthMeter.

set -uo pipefail

E3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../e3" && pwd)"   # reuse verify_output.py

E5_HEADER=$'panel\tarm\trep\twall_s\texit_code\tstatus\truns_complete\truns_expected\tbytes_verified\tbytes_expected\tMBps_verified\tsettle_workers\tsettle_efficiency\thost\tstamp'

e5_init() { [[ -f "$1" ]] || printf '%s\n' "$E5_HEADER" > "$1"; }

# run_aspera_arm <panel> <arm> <rep> <list> <manifest> <cmd>
run_aspera_arm() {
    local panel="$1" arm="$2" rep="$3" list="$4" manifest="$5" cmd="$6"

    local safe="${arm//[^A-Za-z0-9_.-]/_}"
    local dir="$E5_WORK/${panel}_${safe}_rep${rep}"
    local logf="$E5_LOGS/${panel}_${safe}_rep${rep}.log"
    rm -rf "$dir"; mkdir -p "$dir"
    pkill -9 ascp 2>/dev/null; sleep 1     # no stray session from a prior arm

    echo "[$(date +%H:%M:%S)] $panel rep=$rep arm=$arm (timeout ${E5_TIMEOUT}s)" >&2

    local t0 t1 rc
    t0=$(date +%s.%N)
    (
        cd "$dir" || exit 127
        export LIST="$list"
        timeout --kill-after=30 "$E5_TIMEOUT" bash -c "$cmd"
    ) > "$logf" 2>&1
    rc=$?
    t1=$(date +%s.%N)
    pkill -9 ascp 2>/dev/null                # reap anything the timeout left

    local wall status
    wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.2f", b-a}')
    status="ok"
    if   [[ $rc -eq 124 || $rc -eq 137 ]]; then status="TIMEOUT"
    elif [[ $rc -ne 0 ]];                  then status="rc=$rc"; fi

    # manifest judge
    local v
    v=$("$E5_PYTHON" "$E3_DIR/verify_output.py" \
            --manifest "$manifest" --outdir "$dir" --jobs "$E5_MD5_JOBS" 2>>"$logf")
    [[ -z "$v" ]] && v="runs_complete=0 runs_expected=0 bytes_verified=0 bytes_expected=0"
    local runs_complete runs_partial runs_expected files_verified files_expected
    local bytes_verified bytes_expected bytes_on_disk files_on_disk extra_files format
    eval "$v"

    local mbps
    mbps=$(awk -v b="$bytes_verified" -v s="$wall" 'BEGIN{printf "%.2f", (s>0)? b/1e6/s : 0}')

    # settle point + efficiency from the trajectory log (adaptive arms only)
    local settle_w settle_e
    settle_w=$(grep -oE "aspera settled: workers=[0-9]+" "$logf" 2>/dev/null | tail -1 | grep -oE "[0-9]+" || true)
    settle_w=${settle_w:-}
    # efficiency at the settled worker count = last probe whose workers==settle_w
    settle_e=""
    if [[ -n "$settle_w" ]]; then
        settle_e=$(grep -E "aspera probe: workers=${settle_w} " "$logf" 2>/dev/null | tail -1 \
                   | grep -oE "efficiency=[0-9.]+" | cut -d= -f2 || true)
    fi
    settle_w=${settle_w:-NA}; settle_e=${settle_e:-NA}

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$panel" "$arm" "$rep" "$wall" "$rc" "$status" \
        "$runs_complete" "$runs_expected" "$bytes_verified" "$bytes_expected" \
        "$mbps" "$settle_w" "$settle_e" "$(hostname -s)" "$(date -Is)" \
        >> "$E5_TSV"

    # trajectory: (arm rep workers throughput efficiency) for Fig 5a
    grep -oE "aspera probe: workers=[0-9]+ throughput=[0-9.]+ efficiency=[0-9.]+" "$logf" 2>/dev/null \
      | sed -E "s/aspera probe: workers=([0-9]+) throughput=([0-9.]+) efficiency=([0-9.]+)/${arm}\trep${rep}\t\1\t\2\t\3/" \
      >> "$E5_LOGS/trajectories.tsv" || true

    echo "    -> ${wall}s  ${mbps} MB/s  runs=${runs_complete}/${runs_expected}  settle=${settle_w}w eff=${settle_e}  ${status}" >&2
    rm -rf "$dir"
}
