#!/usr/bin/env bash
# Shared measurement machinery for E3. Sourced by run_e3.sh.
#
# One function matters here: `run_arm`. It executes one (arm x dataset x rep),
# times it, traces peak RSS/CPU, judges the output against the ENA manifest via
# verify_output.py, appends exactly one TSV row, and then deletes the payload.
#
# Deleting between every arm is not housekeeping -- it is the experiment's
# cold-cache control (EXPERIMENT_PLAN §12.3). Never "optimize" it away.

set -uo pipefail

E3_TSV_HEADER=$'panel\tdataset\tarm\ttool\trep\torder_idx\twall_s\texit_code\tstatus\truns_complete\truns_partial\truns_expected\tfiles_verified\tfiles_expected\tbytes_verified\tbytes_expected\tbytes_on_disk\tfiles_on_disk\textra_files\tformat\tMBps_verified\tpeak_rss_kb\tcpu_pct\tconc_med\tconc_p95\tconc_max\tconc_per_host_max\tprocs_max\tconc_samples\tworkers_med\tworkers_max\thost\tstamp'

e3_init_results() {
    local tsv="$1"
    if [[ ! -f "$tsv" ]]; then
        printf '%s\n' "$E3_TSV_HEADER" > "$tsv"
    fi
}

# run_arm <panel> <dataset_name> <arm_name> <tool> <rep> <order_idx> <list> <manifest> <cmd>
#
# <cmd> is a shell string executed with CWD set to a fresh scratch dir; it may
# reference $LIST (accession list) and $IDS_CSV (fetchngs-style CSV).
run_arm() {
    local panel="$1" dataset="$2" arm="$3" tool="$4" rep="$5" order_idx="$6"
    local list="$7" manifest="$8" cmd="$9"

    local safe_arm="${arm//[^A-Za-z0-9_.-]/_}"
    local dir="$E3_WORK/${panel}_${dataset}_${safe_arm}_rep${rep}"
    local logf="$E3_LOGS/${panel}_${dataset}_${safe_arm}_rep${rep}.log"
    local timef; timef="$(mktemp)"

    rm -rf "$dir"; mkdir -p "$dir"

    # fetchngs wants a CSV of ids; harmless to provide for every arm.
    local ids_csv="$dir/.ids.csv"
    { echo "id"; cat "$list"; } > "$ids_csv"

    echo "[$(date +%H:%M:%S)] rep=$rep order=$order_idx arm=$arm dataset=$dataset (timeout ${E3_TIMEOUT}s)" >&2

    local concf="$E3_LOGS/conc_${panel}_${dataset}_${safe_arm}_rep${rep}.tsv"
    local wtracef="$E3_LOGS/workers_${panel}_${dataset}_${safe_arm}_rep${rep}.tsv"
    local t0 t1 rc
    t0=$(date +%s.%N)
    # Backgrounded so we can hand the PID to the concurrency sampler and still
    # collect the real exit code via `wait`.
    (
        cd "$dir" || exit 127
        export LIST="$list" IDS_CSV="$ids_csv"
        # Honoured only by aseq_run.py; other tools ignore it.
        export ASEQ_WORKER_TRACE="$wtracef"
        # /usr/bin/time -v gives peak RSS + CPU% for the whole process tree, which
        # is the honest envelope for iseq's subprocess-per-run model AND for
        # adaptiSeq's single-process asyncio pool (EXPERIMENT_PLAN §10).
        timeout --kill-after=60 "$E3_TIMEOUT" \
            /usr/bin/time -v -o "$timef" \
            bash -c "$cmd"
    ) > "$logf" 2>&1 &
    local arm_pid=$!

    # Instantaneous concurrency, sampled identically for every arm (see
    # sample_concurrency.py). Self-terminates when the arm's tree exits.
    local sampf; sampf="$(mktemp)"
    "$E3_PYTHON" "$E3_DIR/sample_concurrency.py" \
        --pid "$arm_pid" --out "$concf" --hz "${E3_CONC_HZ:-5}" > "$sampf" 2>/dev/null &
    local samp_pid=$!

    wait "$arm_pid"; rc=$?
    t1=$(date +%s.%N)
    wait "$samp_pid" 2>/dev/null || true

    # Default first, then let the sampler's line overwrite: a sampler that died,
    # timed out, or emitted a partial line must degrade to zeros, never abort the
    # arm under `set -u`. Concurrency is instrumentation; losing it must not cost
    # us the measurement.
    local conc_med=0 conc_p95=0 conc_max=0 conc_per_host_max=0 procs_max=0 conc_samples=0
    local sampline; sampline="$(cat "$sampf" 2>/dev/null)"
    if [[ "$sampline" == conc_med=* ]]; then
        eval "$sampline" 2>/dev/null || true
    elif [[ -n "$sampline" ]]; then
        echo "    (concurrency sampler: unexpected output, recording zeros)" >&2
    fi
    rm -f "$sampf"

    # Worker count (pool state) -- distinct from conc_* (TCP sockets). Only
    # adaptiSeq emits this; other arms legitimately record 0.
    local workers_med=0 workers_max=0
    if [[ -s "$wtracef" ]]; then
        workers_med=$(awk -F'\t' 'NR>1 && $2>0{a[n++]=$2} END{if(!n){print 0; exit} asort(a); print a[int((n+1)/2)]}' "$wtracef" 2>/dev/null \
                      || awk -F'\t' 'NR>1 && $2>0{s+=$2; n++} END{print (n? int(s/n+0.5) : 0)}' "$wtracef")
        workers_max=$(awk -F'\t' 'NR>1{if($2>m) m=$2} END{print m+0}' "$wtracef")
    fi
    workers_med=${workers_med:-0}; workers_max=${workers_max:-0}

    local wall status
    wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.2f", b-a}')
    status="ok"
    if   [[ $rc -eq 124 || $rc -eq 137 ]]; then status="TIMEOUT"
    elif [[ $rc -ne 0 ]];                  then status="rc=$rc"; fi

    local peak_rss cpu_pct
    peak_rss=$(awk -F': ' '/Maximum resident set size/{print $2}' "$timef" 2>/dev/null)
    cpu_pct=$(awk -F': ' '/Percent of CPU this job got/{gsub(/%/,"",$2); print $2}' "$timef" 2>/dev/null)
    peak_rss=${peak_rss:-0}; cpu_pct=${cpu_pct:-0}

    # The manifest is the judge -- not the tool's exit code (§12.2).
    local v
    v=$("$E3_PYTHON" "$E3_DIR/verify_output.py" \
            --manifest "$manifest" --outdir "$dir" --jobs "$E3_MD5_JOBS" 2>>"$logf")
    [[ -z "$v" ]] && v="runs_complete=0 runs_partial=0 runs_expected=0 files_verified=0 files_expected=0 bytes_verified=0 bytes_expected=0 bytes_on_disk=0 files_on_disk=0 extra_files=0 format=-"

    local runs_complete runs_partial runs_expected files_verified files_expected
    local bytes_verified bytes_expected bytes_on_disk files_on_disk extra_files format
    eval "$v"

    # MB/s is computed from VERIFIED bytes only: a tool gets credit for bytes it
    # actually delivered intact, so a partial/corrupt transfer can never post a
    # flattering throughput number.
    local mbps
    mbps=$(awk -v b="$bytes_verified" -v s="$wall" 'BEGIN{printf "%.2f", (s>0)? b/1e6/s : 0}')

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$panel" "$dataset" "$arm" "$tool" "$rep" "$order_idx" "$wall" "$rc" "$status" \
        "$runs_complete" "$runs_partial" "$runs_expected" "$files_verified" "$files_expected" \
        "$bytes_verified" "$bytes_expected" "$bytes_on_disk" "$files_on_disk" "$extra_files" \
        "$format" "$mbps" "$peak_rss" "$cpu_pct" \
        "$conc_med" "$conc_p95" "$conc_max" "$conc_per_host_max" "$procs_max" "$conc_samples" \
        "$workers_med" "$workers_max" \
        "$(hostname -s)" "$(date -Is)" \
        >> "$E3_TSV"

    # adaptiSeq's INTERNAL view: what the controller intended (gate.active per
    # probe). Complements the sampler's external view of what actually reached
    # the wire; the pair is what E4's Fig 4 plots. Needs the INFO-logging wrapper
    # (aseq_run.py) -- the bare CLI emits only the end-of-run summary line.
    # "worker summary" is the current end-of-run Note; "worker trajectory" was
    # its name before the probe history became bounded -- match both so logs
    # from either build parse.
    grep -h "worker trajectory\|worker summary\|adaptive probe" "$logf" 2>/dev/null \
        | sed "s|^|${arm}\trep${rep}\t|" >> "$E3_LOGS/trajectories.tsv" || true

    echo "    -> ${wall}s  ${mbps} MB/s  runs=${runs_complete}/${runs_expected}  fmt=${format}  conc=${conc_med}/${conc_max} w=${workers_med}/${workers_max}  ${status}" >&2

    rm -rf "$dir" "$timef"
}
