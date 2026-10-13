#!/bin/bash
#SBATCH --job-name=adaptiseq_e7
#SBATCH --account=umr115
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --time=16:00:00
#SBATCH --output=slurm_e7_%j.out
#SBATCH --error=slurm_e7_%j.err
#
# E7 -- Reliability & resumability (Table 3) on SDSC Expanse.
#
# Same discipline as E3 (see bench/e3/e3_expanse.sbatch): ONE exclusive node, ONE
# job, arms STRICTLY SEQUENTIAL. E7 has an extra reason never to run arms
# concurrently: the circuit-breaker sub-experiment (7d) would cross-trip if two
# arms hit the same host at once.
#
# Walltime 16 h: reliability transfer is far smaller than E3's, but iseq's 241
# sequential per-run RTTs (7a) dominate and can be slow from San Diego -> EBI.
#
# Submit:  sbatch bench/e7/e7_expanse.sbatch
#          PANELS="7a 7b" sbatch --export=ALL,PANELS="7a 7b" bench/e7/e7_expanse.sbatch

set -uo pipefail
export PS1="${PS1:-}"

module purge
module load slurm cpu/0.17.3b anaconda3/2021.05

CONDA_BASE="$(conda info --base 2>/dev/null || true)"
if [[ -z "$CONDA_BASE" || ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
    echo "[ERROR] Could not locate conda.sh after loading the anaconda module." >&2; exit 1
fi
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate adaptiseq_e3 || { echo "[ERROR] conda env 'adaptiseq_e3' missing. Run bench/e3/setup_env.sh first." >&2; exit 1; }
export PATH="${CONDA_PREFIX}/bin:$PATH"

REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_DIR" || exit 1
export E7_PYTHON="${CONDA_PREFIX}/bin/python3"

# Payload on node-local NVMe, results on Lustre (identical rationale to E3).
pick_local_scratch() {
    local c
    for c in "${LOCAL_SCRATCH:-}" "${SLURM_TMPDIR:-}" \
             "/scratch/$USER/job_$SLURM_JOB_ID" "/tmp/$USER/job_$SLURM_JOB_ID"; do
        [[ -z "$c" ]] && continue
        mkdir -p "$c" 2>/dev/null && { echo "$c"; return 0; }
    done
    return 1
}
NVME_DIR="$(pick_local_scratch)" || { echo "[ERROR] no writable local scratch." >&2; exit 1; }

LUSTRE_ROOT="${LUSTRE_ROOT:-/expanse/lustre/scratch/$USER/temp_project}"
[[ -d "$LUSTRE_ROOT" ]] || LUSTRE_ROOT="$(dirname "$REPO_DIR")"
RUN_OUT="${LUSTRE_ROOT}/adaptiseq_e7/e7_${SLURM_JOB_ID:-manual}"
mkdir -p "$RUN_OUT" || { echo "[ERROR] cannot create $RUN_OUT" >&2; exit 1; }

export E7_WORK="$NVME_DIR/e7_payload"
export E7_OUT="$RUN_OUT"
export E7_MD5_JOBS="${E7_MD5_JOBS:-64}"
export DATASETS="$REPO_DIR/datasets"
export E7_LIVE_THROTTLE=0     # Expanse does not throttle; the synthetic 7d panel carries it
mkdir -p "$E7_WORK"

_e7_job_cleanup() {
    local rc=$?; trap - EXIT INT TERM
    echo "[cleanup] removing payload $E7_WORK ($(du -sh "$E7_WORK" 2>/dev/null | cut -f1))"
    rm -rf "$E7_WORK" 2>/dev/null || true
    exit $rc
}
trap _e7_job_cleanup EXIT INT TERM

echo "=== adaptiSeq E7 (reliability & resumability, Table 3) ==="
echo "node    : $(hostname -s)"
echo "python  : $E7_PYTHON  ($(python3 --version 2>&1))"
echo "payload : $E7_WORK   ($(df -h "$NVME_DIR" | awk 'NR==2{print $4}') free)"
echo "results : $RUN_OUT"
echo "panels  : ${PANELS:-7a 7b 7c 7d 7e}"

# ─── GATE 1: outbound egress (gate everything, parent §16.1) ───────────────
echo; echo "=== egress check ==="
egress_ok=1
for host in https://ftp.sra.ebi.ac.uk https://www.ebi.ac.uk https://ftp.ncbi.nlm.nih.gov; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -I "$host" 2>&1) \
        && echo "  OK   $host -> $code" \
        || { echo "  FAIL $host ($code)"; egress_ok=0; }
done
[[ $egress_ok -ne 1 ]] && { echo "[ERROR] no egress; every E7a/b/e number would be a proxy artefact." >&2; exit 1; }

# ─── GATE 2: tools (md5 checking is ON, so sra-tools is mandatory) ─────────
echo; echo "=== tool check ==="
missing=0
for t in adaptiseq iseq kingfisher srapath vdb-validate md5sum curl; do
    command -v "$t" >/dev/null 2>&1 && printf '  OK   %-14s\n' "$t" || { printf '  MISS %-14s\n' "$t"; missing=1; }
done
[[ $missing -eq 1 ]] && { echo "[ERROR] missing tools; run bench/e3/setup_env.sh" >&2; exit 1; }

echo; echo "=== versions ==="
{ echo "date: $(date -Is)"; adaptiseq -v 2>&1 | head -1; iseq -v 2>&1 | head -2 | tail -1
  kingfisher --version 2>&1 | head -1; python3 --version; conda list --export 2>/dev/null; } > "$RUN_OUT/versions.txt"
head -6 "$RUN_OUT/versions.txt"

echo; echo "=== datasets (re-pull sizes/md5s on the day of the run) ==="
"$E7_PYTHON" "$REPO_DIR/bench/e3/make_datasets.py" --outdir "$DATASETS" 2>&1 | tee "$RUN_OUT/datasets_build.log"
cp -r "$DATASETS" "$RUN_OUT/datasets_used" 2>/dev/null || true

echo; echo "=== running sub-experiments ==="
status=0
PANELS="${PANELS:-7a 7b 7c 7d 7e}" bash "$REPO_DIR/bench/e7/run_e7.sh" all || status=$?

echo; echo "=== aggregating ==="
"$E7_PYTHON" "$REPO_DIR/bench/e7/aggregate_e7.py" --outdir "$RUN_OUT" 2>&1 | tee "$RUN_OUT/summary.txt" || true

cp "$REPO_DIR/bench/e7/"*.sh "$REPO_DIR/bench/e7/"*.py "$REPO_DIR/bench/e7/"*.sbatch "$RUN_OUT/" 2>/dev/null || true
for f in "slurm_e7_${SLURM_JOB_ID}.out" "slurm_e7_${SLURM_JOB_ID}.err"; do [[ -f "$f" ]] && cp "$f" "$RUN_OUT/"; done

echo "=== done (status=$status). Results: $RUN_OUT ==="
exit "$status"
