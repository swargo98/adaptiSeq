#!/bin/bash
#SBATCH --job-name=adaptiseq_e8
#SBATCH --account=umr115
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --time=10:00:00
#SBATCH --output=slurm_e8_%j.out
#SBATCH --error=slurm_e8_%j.err
#
# E8 -- Resource profile (Fig 6, mirrors iSeq Fig 1D) on SDSC Expanse.
#
# Same discipline as E3/E7: ONE exclusive node, ONE job, arms STRICTLY SEQUENTIAL.
# E8's extra reason to serialise is that a co-scheduled arm would contaminate the
# CPU/I/O trace of its neighbour -- the whole point of the figure is a clean
# per-tool resource envelope. --exclusive also keeps a noisy neighbour off the NIC
# and cores so the psutil traces reflect the tool, not the node.
#
# Cheap experiment (single-file fetches): ~1.5-2.5 h for both panels x 5 reps.
#
# Submit:  sbatch bench/e8/e8_expanse.sbatch
#          E8_SRA_ACC=SRRxxxxxxx sbatch --export=ALL,E8_SRA_ACC=SRRxxxxxxx bench/e8/e8_expanse.sbatch

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
export E8_PYTHON="${CONDA_PREFIX}/bin/python3"

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
RUN_OUT="${LUSTRE_ROOT}/adaptiseq_e8/e8_${SLURM_JOB_ID:-manual}"
mkdir -p "$RUN_OUT" || { echo "[ERROR] cannot create $RUN_OUT" >&2; exit 1; }

export E8_WORK="$NVME_DIR/e8_payload"
export E8_OUT="$RUN_OUT"
export E8_MD5_JOBS="${E8_MD5_JOBS:-16}"
export DATASETS="$REPO_DIR/datasets"
export E8_SRA_ACC="${E8_SRA_ACC:-SRR1031060}"
mkdir -p "$E8_WORK"

_e8_job_cleanup() {
    local rc=$?; trap - EXIT INT TERM
    echo "[cleanup] removing payload $E8_WORK ($(du -sh "$E8_WORK" 2>/dev/null | cut -f1))"
    rm -rf "$E8_WORK" 2>/dev/null || true
    exit $rc
}
trap _e8_job_cleanup EXIT INT TERM

echo "=== adaptiSeq E8 (resource profile, Fig 6) ==="
echo "node    : $(hostname -s)"
echo "python  : $E8_PYTHON  ($(python3 --version 2>&1))"
echo "results : $RUN_OUT"
echo "panels  : ${PANELS:-8-ENA 8-SRA}   SRA_ACC=$E8_SRA_ACC"

echo; echo "=== egress check ==="
egress_ok=1
for host in https://ftp.sra.ebi.ac.uk https://www.ebi.ac.uk https://ftp.ncbi.nlm.nih.gov; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -I "$host" 2>&1) \
        && echo "  OK   $host -> $code" || { echo "  FAIL $host ($code)"; egress_ok=0; }
done
[[ $egress_ok -ne 1 ]] && { echo "[ERROR] no egress; profiles would be proxy artefacts." >&2; exit 1; }

echo; echo "=== tool check ==="
missing=0
for t in adaptiseq iseq kingfisher prefetch fasterq-dump vdb-validate srapath md5sum curl; do
    command -v "$t" >/dev/null 2>&1 && printf '  OK   %-14s\n' "$t" || { printf '  MISS %-14s\n' "$t"; missing=1; }
done
[[ $missing -eq 1 ]] && { echo "[ERROR] missing tools; run bench/e3/setup_env.sh" >&2; exit 1; }

echo; echo "=== versions ==="
{ echo "date: $(date -Is)"; adaptiseq -v 2>&1 | head -1; iseq -v 2>&1 | head -2 | tail -1
  kingfisher --version 2>&1 | head -1; prefetch --version 2>&1 | head -2 | tail -1
  python3 --version; python3 -c "import psutil;print('psutil',psutil.__version__)"; } > "$RUN_OUT/versions.txt"
head -6 "$RUN_OUT/versions.txt"

echo; echo "=== datasets ==="
"$E8_PYTHON" "$REPO_DIR/bench/e3/make_datasets.py" --outdir "$DATASETS" 2>&1 | tee "$RUN_OUT/datasets_build.log"

echo; echo "=== running panels ==="
status=0
PANELS="${PANELS:-8-ENA 8-SRA}" bash "$REPO_DIR/bench/e8/run_e8.sh" all || status=$?

echo; echo "=== aggregating ==="
"$E8_PYTHON" "$REPO_DIR/bench/e8/aggregate_e8.py" --outdir "$RUN_OUT" 2>&1 | tee "$RUN_OUT/summary.txt" || true

cp "$REPO_DIR/bench/e8/"*.sh "$REPO_DIR/bench/e8/"*.py "$REPO_DIR/bench/e8/"*.sbatch "$RUN_OUT/" 2>/dev/null || true
for f in "slurm_e8_${SLURM_JOB_ID}.out" "slurm_e8_${SLURM_JOB_ID}.err"; do [[ -f "$f" ]] && cp "$f" "$RUN_OUT/"; done

echo "=== done (status=$status). Results: $RUN_OUT ==="
exit "$status"
