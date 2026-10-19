#!/bin/bash
#SBATCH --job-name=aseq_ctrl_trace
#SBATCH --account=umr115
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --time=03:00:00
#SBATCH --output=slurm_ctrl_trace_%j.out
#
# The 0.1.5 check (55061121) had the adaptive default 4.2x slower than fixed -j 20
# on panel 3b (1611 s vs 379 s): the controller held 1 worker for the last 20 min.
# This reruns that arm with the controller's INFO log (every probe and commit,
# timestamped) and the gate's worker count every 0.4 s, then fixed -j 20 as the
# reference, so the controller's decisions can be read against the throughput.
#   sbatch diag_ctrl/ctrl_trace.sbatch     # from plans_and_experiments/
#   MODES="adaptive" LIST=datasets/D1_full_PRJNA916347.txt sbatch --export=ALL diag_ctrl/ctrl_trace.sbatch
set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME:-adaptiseq_e3_sub}" || exit 1
set -u
export PATH="${CONDA_PREFIX}/bin:$PATH"
REPO_DIR="$SLURM_SUBMIT_DIR"
OUT="$REPO_DIR/diag_ctrl/out_${SLURM_JOB_ID}"
WORK="/scratch/$USER/job_${SLURM_JOB_ID}/ctrl"
mkdir -p "$OUT" "$WORK"
trap 'rm -rf "$WORK"' EXIT
exec > >(tee -a "$OUT/trace.txt") 2>&1
LIST="${LIST:-datasets/D2_subset_PRJNA762469.txt}"
MANIFEST="$REPO_DIR/${LIST%.txt}.manifest"
echo "date: $(date -Is)  node: $(hostname -s)  list: $LIST"
python "$REPO_DIR/bench/e3/aseq_fingerprint.py" --wheel "$REPO_DIR/wheels/adaptiseq-0.1.5-py3-none-any.whl"
for mode in ${MODES:-adaptive fixed}; do
    d="$WORK/$mode"; mkdir -p "$d"; cd "$d" || exit 1
    if [[ "$mode" == adaptive ]]; then flags=(); else flags=(--no-adaptive -j 20); fi
    t0=$(date +%s.%N)
    ASEQ_WORKER_TRACE="$OUT/workers_${mode}.tsv" python "$REPO_DIR/bench/e3/aseq_run.py" \
        -i "$REPO_DIR/$LIST" -g "${flags[@]}" -o . > "$OUT/run_${mode}.log" 2>&1 &
    ap=$!
    python "$REPO_DIR/bench/e3/sample_concurrency.py" --pid $ap --out "$OUT/conc_${mode}.tsv" --hz 2 >/dev/null 2>&1 &
    wait $ap; rc=$?
    t1=$(date +%s.%N)
    wait
    echo "== $mode: rc=$rc wall=$(echo "$t1 - $t0" | bc) s"
    python "$REPO_DIR/bench/e3/verify_output.py" --manifest "$MANIFEST" --outdir . 2>&1 | tail -2
    cd "$WORK" && rm -rf "$d"
done
echo "=== done $(date -Is) ==="
