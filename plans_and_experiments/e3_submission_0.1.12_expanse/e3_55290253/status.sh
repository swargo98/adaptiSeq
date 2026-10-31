#!/usr/bin/env bash
# Read an E3 run's health/results without hand-grepping. Point it at a results dir:
#
#   bash bench/e3/status.sh /expanse/lustre/scratch/$USER/temp_project/adaptiseq_e3/e3_<jobid>
#
# Prints: job-done marker, per-panel arm counts, a readable results table, any
# bad rows (timeout / not-ok / short verification), and per-arm health flags
# scraped from the logs (Phase B re-resolutions, connection failures, single-
# stream degradation). Read-only; safe to run any time while the job is live.

set -uo pipefail
R="${1:-.}"
TSV="$R/e3_results.tsv"
LOGS="$R/logs"

[[ -f "$TSV" ]] || { echo "no e3_results.tsv in $R"; exit 1; }

echo "=== run: $R ==="
if [[ -f "$R/summary.txt" ]]; then
    echo "  JOB FINISHED (summary.txt present)"
else
    echo "  job in progress (no summary.txt yet)"
fi

echo "=== arms done per panel ==="
awk -F'\t' 'NR>1{print $1}' "$TSV" | sort | uniq -c | sed 's/^/  /'

echo "=== results (arm | wall | status | runs | verified | MB/s | conc_max | w_max) ==="
awk -F'\t' 'NR==1{for(i=1;i<=NF;i++)h[$i]=i; next}{
  printf "  %-6s %-24s wall=%-7s %-8s runs=%s/%s ver=%s/%s %6s MB/s conc=%-3s w=%-3s\n",
  $h["panel"],$h["arm"],$h["wall_s"],$h["status"],
  $h["runs_complete"],$h["runs_expected"],$h["files_verified"],$h["files_expected"],
  $h["MBps_verified"],$h["conc_max"],$h["workers_max"]}' "$TSV"

echo "=== problems (status!=ok OR verified<expected) ==="
bad=$(awk -F'\t' 'NR==1{for(i=1;i<=NF;i++)h[$i]=i; next}
  ($h["status"]!="ok" || $h["files_verified"]!=$h["files_expected"]){
  print "  "$h["arm"]" ("$h["panel"]"): "$h["status"]", verified="$h["files_verified"]"/"$h["files_expected"]}' "$TSV")
if [[ -n "$bad" ]]; then echo "$bad"; else echo "  none — every completed arm is clean"; fi

echo "=== per-arm health flags (from logs; want 0 / 0 / 0) ==="
if [[ -d "$LOGS" ]]; then
    printf "  %-40s %8s %8s %8s\n" "arm-log" "reresolv" "connfail" "single"
    for L in "$LOGS"/*adaptiseq*.log; do
        [[ -e "$L" ]] || continue
        rr=$(grep -c 'File size:' "$L" 2>/dev/null); rr=${rr:-0}
        cf=$(grep -c 'Connect call failed' "$L" 2>/dev/null); cf=${cf:-0}
        ss=$(grep -c 'no ranges; single-stream' "$L" 2>/dev/null); ss=${ss:-0}
        flag=""
        [[ "$rr" -ne 0 || "$cf" -ne 0 || "$ss" -ne 0 ]] && flag="  <-- check"
        printf "  %-40s %8s %8s %8s%s\n" "$(basename "$L" .log)" "$rr" "$cf" "$ss" "$flag"
    done
    echo "  reresolv = Phase B re-resolutions (fix regressed if >0)"
    echo "  connfail = worker-burst connection refusals (the S7b issue)"
    echo "  single   = files degraded to single-stream (also S7b)"
else
    echo "  no logs/ dir"
fi
