#!/bin/bash
#SBATCH --job-name=aseq_flaky
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:45:00
#SBATCH --output=slurm_flaky_%j.out
# Repeat test_auto_cap_does_not_truncate_intended_concurrency: 40 runs idle,
# then 40 runs with 4 busy-loop processes competing for the job's 4 CPUs.
set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u; source "$(conda info --base)/etc/profile.d/conda.sh"; conda activate adaptiseq_e3_sub || exit 1; set -u
TMP=/scratch/$USER/job_$SLURM_JOB_ID; mkdir -p $TMP; trap 'kill $(jobs -p) 2>/dev/null; rm -rf $TMP' EXIT
python -m venv --system-site-packages $TMP/v && $TMP/v/bin/pip -q install "pytest>=7.0" pytest-timeout || exit 1
cd /home/rswargo/adaptiSeq || exit 1
export PYTHONDONTWRITEBYTECODE=1 ADAPTISEQ_NO_NETWORK=1
T=tests/test_batch.py::test_auto_cap_does_not_truncate_intended_concurrency
echo "checkout: $(git rev-parse --short HEAD)$(git diff --quiet -- tests || echo ' + uncommitted test changes') node: $(hostname -s)"
run() { local p=0 f=0; for i in $(seq 40); do
  if $TMP/v/bin/python -m pytest -q -p no:cacheprovider --timeout=120 "$T" > $TMP/o.txt 2>&1; then p=$((p+1)); else f=$((f+1)); grep -m1 "peak=" $TMP/o.txt; fi
done; echo "$1: $p passed, $f failed"; }
run idle
for k in 1 2 3 4; do ( while :; do :; done ) & done
run loaded
