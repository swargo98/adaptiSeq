#!/usr/bin/env bash
#SBATCH --job-name=aseq-e10
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=01:30:00
#SBATCH --output=e10_%j.out
#SBATCH --error=e10_%j.err
#
# E10 -- parallel metadata resolution & rate-limit etiquette on SDSC Expanse.
# Resolution-only: no large sequencing transfers, so `shared` + modest mem is
# plenty (unlike E8/E9). 10c is fully local (no egress). The live panels (10a/10b)
# are GATED on compute-node egress to ENA/GSA -- if that fails, 10c still runs and
# is reported alone.
#
#   sbatch bench/e10/e10_expanse.sbatch
set -uo pipefail

module reset 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true
conda activate adaptiseq 2>/dev/null || true

REPO_DIR="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$REPO_DIR"

export E10_PYTHON="${E10_PYTHON:-python3}"
export E10_OUT="$REPO_DIR/e10_results_expanse_${SLURM_JOB_ID:-local}"
# Expanse gets the spec-target N and more reps.
export E10_NS="100,500,2000"
export E10_META_JOBS="1,3,8,16"
export E10_REPS="5"
export E10_N_COMP="40"
export E10_COMP_REPS="3"

echo "== node: $(hostname)  cpus: ${SLURM_CPUS_PER_TASK:-?} =="

# ---- egress gate for the live panels --------------------------------------
EGRESS_OK=1
curl -sI --max-time 20 https://www.ebi.ac.uk/ena/portal/api/ >/dev/null 2>&1 || EGRESS_OK=0
echo "== ENA egress: $([[ $EGRESS_OK -eq 1 ]] && echo OK || echo BLOCKED) =="

if [[ $EGRESS_OK -eq 1 ]]; then
    PANELS="10a 10b 10c" bash bench/e10/run_e10.sh all
else
    echo "!! compute-node egress blocked -- running the local etiquette panel only." >&2
    echo "!! Re-run 10a/10b on a data-transfer node or with a proxy (see plan §13)." >&2
    bash bench/e10/run_e10.sh 10c
fi

python3 bench/e10/aggregate_e10.py --out "$E10_OUT" || true
echo "== E10 done: $E10_OUT =="
