#!/usr/bin/env bash
# Submit E3 on Expanse.
#
# Default: ONE job runs every panel sequentially (the safest, most defensible
# layout -- see the header of e3_expanse.sbatch for why arms must never run
# concurrently).
#
#   bash bench/e3/submit_e3.sh                  # one 48 h job, all panels
#   bash bench/e3/submit_e3.sh --split          # one job per panel, CHAINED
#   PANELS="3a 3b" bash bench/e3/submit_e3.sh   # subset
#
# --split gives shorter, individually-requeueable jobs. It chains them with
# --dependency=afterany so they still never overlap: two panels hammering the
# same link at once would corrupt both. It is a scheduling convenience, not a
# parallelisation.

set -euo pipefail
E3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SBATCH_FILE="$E3_DIR/e3_expanse.sbatch"
PANELS="${PANELS:-3a 3r 3b 3c 3d}"

# Per-panel walltimes, sized from the transfer budget in docs/EXPERIMENT_PLAN_E3.md §6.
declare -A WALL=( [3a]="12:00:00" [3r]="06:00:00" [3b]="16:00:00" [3c]="04:00:00" [3d]="10:00:00" )

if [[ "${1:-}" != "--split" ]]; then
    echo "Submitting a single job for panels: $PANELS"
    sbatch --export=ALL,PANELS="$PANELS" "$SBATCH_FILE"
    exit 0
fi

dep=""
for p in $PANELS; do
    args=(--export=ALL,PANELS="$p" --job-name="e3_$p" --time="${WALL[$p]:-12:00:00}")
    [[ -n "$dep" ]] && args+=(--dependency=afterany:"$dep")
    jid=$(sbatch --parsable "${args[@]}" "$SBATCH_FILE")
    echo "  panel $p -> job $jid (walltime ${WALL[$p]:-12:00:00}${dep:+, after $dep})"
    dep="$jid"
done
echo "Chained. Monitor: squeue -u \$USER"
