#!/bin/bash
#SBATCH --job-name=aseq_pytest
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:30:00
#SBATCH --output=slurm_pytest_%j.out
#
# The test suite from the checkout, offline and with network, without building
# or installing anything (setup_expanse.sbatch reinstalls the wheel into the
# benchmark env, which must not happen while a benchmark job is using it).
#
#   sbatch bench/e3/pytest_expanse.sbatch        # from plans_and_experiments/
#   PYTEST_ARGS="tests/test_list_resilience.py" sbatch --export=ALL bench/e3/pytest_expanse.sbatch

set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME:-adaptiseq_e3_sub}" || exit 1
set -u
export PATH="${CONDA_PREFIX}/bin:$PATH"

REPO_DIR="$SLURM_SUBMIT_DIR"
SRC_DIR="$(cd "$REPO_DIR/.." && pwd)"
OUT="$REPO_DIR/pytest_expanse_${SLURM_JOB_ID}"
TMP="/scratch/$USER/job_${SLURM_JOB_ID}"
mkdir -p "$OUT" "$TMP"
trap 'rm -rf "$TMP"' EXIT

python -m venv --system-site-packages "$TMP/venv_test" \
    && "$TMP/venv_test/bin/pip" -q install "pytest>=7.0" pytest-timeout \
    || { echo "[ERROR] could not create the test venv" >&2; exit 1; }
cd "$SRC_DIR" || exit 1
export PYTHONDONTWRITEBYTECODE=1
echo "checkout: $(git rev-parse --short HEAD)$(git diff --quiet -- adaptiseq tests || echo ' + uncommitted changes')  node: $(hostname -s)" | tee "$OUT/checkout.txt"
"$TMP/venv_test/bin/python" -c 'import adaptiseq, sys; print("adaptiseq imported from", adaptiseq.__file__)' | tee -a "$OUT/checkout.txt"

status=0
echo; echo "=== tests, offline (ADAPTISEQ_NO_NETWORK=1) ==="
ADAPTISEQ_NO_NETWORK=1 "$TMP/venv_test/bin/python" -m pytest -q -p no:cacheprovider --timeout=600 -rfEs ${PYTEST_ARGS:-} \
    > "$OUT/pytest_offline.txt" 2>&1 || status=1
tail -15 "$OUT/pytest_offline.txt"

if [[ "${OFFLINE_ONLY:-0}" != "1" ]]; then
    echo; echo "=== tests, with network ==="
    timeout 4500 "$TMP/venv_test/bin/python" -m pytest -q -p no:cacheprovider --timeout=900 -rfEs ${PYTEST_ARGS:-} \
        > "$OUT/pytest_network.txt" 2>&1 || status=1
    tail -15 "$OUT/pytest_network.txt"
fi
echo "=== pytest done (status=$status). Output: $OUT ==="
exit $status
