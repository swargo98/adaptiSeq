#!/bin/bash
#SBATCH --job-name=aseq_flaky_diag
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=slurm_flaky_diag_%j.out
# diag.py 30 times with 4 busy loops on the job's 4 CPUs, request timings for low peaks.
set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u; source "$(conda info --base)/etc/profile.d/conda.sh"; conda activate adaptiseq_e3_sub || exit 1; set -u
TMP=/scratch/$USER/job_$SLURM_JOB_ID; mkdir -p $TMP
export PYTHONDONTWRITEBYTECODE=1 ADAPTISEQ_NO_NETWORK=1
cd /home/rswargo/adaptiSeq || exit 1
for k in 1 2 3 4; do ( while :; do :; done ) & done
for i in $(seq 30); do d=$TMP/r$i; mkdir -p $d; python plans_and_experiments/flaky_repeat_check/diag.py 0.3 $d 2>&1 | grep -v "^\[notice"; rm -rf $d; done
kill $(jobs -p) 2>/dev/null
