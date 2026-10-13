#!/bin/bash
#SBATCH --job-name=adaptiseq_e5
#SBATCH --account=umr115
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --time=06:00:00
#SBATCH --output=slurm_e5_%j.out
#SBATCH --error=slurm_e5_%j.err
#
# E5 -- Adaptive Aspera, efficiency hysteresis (Fig 5) on SDSC Expanse.
#
# CRITICAL GATE (parent plan §13): Aspera uses UDP port 33001 outbound. Many HPC
# compute nodes block outbound UDP. This job HARD-GATES on a real ascp handshake to
# fasp.sra.ebi.ac.uk before spending walltime -- if UDP 33001 is blocked, E5 cannot
# run here and must move to a data-transfer node (DTN) or a cloud VM (reported
# separately). Do NOT silently fall back to a stub: that would make Fig 5 meaningless.
#
# Arms strictly sequential (they share the same ENA Aspera session budget).
#
# Submit:  sbatch bench/e5/e5_expanse.sbatch
#          PANELS="5a 5b" sbatch --export=ALL,PANELS="5a 5b" bench/e5/e5_expanse.sbatch

set -uo pipefail
export PS1="${PS1:-}"

module purge
module load slurm cpu/0.17.3b anaconda3/2021.05

CONDA_BASE="$(conda info --base 2>/dev/null || true)"
if [[ -z "$CONDA_BASE" || ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
    echo "[ERROR] Could not locate conda.sh." >&2; exit 1
fi
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate adaptiseq_e3 || { echo "[ERROR] conda env 'adaptiseq_e3' missing. Run bench/e3/setup_env.sh first." >&2; exit 1; }
export PATH="${CONDA_PREFIX}/bin:$PATH"

REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_DIR" || exit 1
export E5_PYTHON="${CONDA_PREFIX}/bin/python3"

# real ascp on PATH (installs to ~/.aspera/sdk, symlink in ~/.local/bin)
export PATH="$HOME/.local/bin:$PATH"
if ! ascp --version 2>/dev/null | grep -qi "ascp version"; then
    echo "[setup] real ascp not found; installing…"
    bash "$REPO_DIR/bench/setup_real_ascp.sh" || { echo "[ERROR] ascp install failed" >&2; exit 1; }
fi

pick_local_scratch() {
    local c
    for c in "${LOCAL_SCRATCH:-}" "${SLURM_TMPDIR:-}" "/scratch/$USER/job_$SLURM_JOB_ID" "/tmp/$USER/job_$SLURM_JOB_ID"; do
        [[ -z "$c" ]] && continue
        mkdir -p "$c" 2>/dev/null && { echo "$c"; return 0; }
    done
    return 1
}
NVME_DIR="$(pick_local_scratch)" || { echo "[ERROR] no writable local scratch." >&2; exit 1; }
LUSTRE_ROOT="${LUSTRE_ROOT:-/expanse/lustre/scratch/$USER/temp_project}"
[[ -d "$LUSTRE_ROOT" ]] || LUSTRE_ROOT="$(dirname "$REPO_DIR")"
RUN_OUT="${LUSTRE_ROOT}/adaptiseq_e5/e5_${SLURM_JOB_ID:-manual}"
mkdir -p "$RUN_OUT" || exit 1

export E5_WORK="$NVME_DIR/e5_payload"
export E5_OUT="$RUN_OUT"
export E5_MD5_JOBS="${E5_MD5_JOBS:-16}"
export DATASETS="$REPO_DIR/datasets"
mkdir -p "$E5_WORK"

_e5_job_cleanup() { local rc=$?; trap - EXIT INT TERM; pkill -9 ascp 2>/dev/null; rm -rf "$E5_WORK" 2>/dev/null; exit $rc; }
trap _e5_job_cleanup EXIT INT TERM

echo "=== adaptiSeq E5 (adaptive Aspera, Fig 5) ==="
echo "node: $(hostname -s)   ascp: $(ascp --version 2>&1 | grep -i 'ascp version')"
echo "results: $RUN_OUT   panels: ${PANELS:-5a 5b 5c}"

# ─── GATE: real Aspera handshake over UDP 33001 (parent §13) ───────────────
echo; echo "=== Aspera UDP-33001 gate ==="
KEY=$("$E5_PYTHON" -c 'from adaptiseq.engine.classic import find_ena_aspera_key as f; print(f())' 2>/dev/null)
[[ -z "$KEY" ]] && { echo "[ERROR] no ENA Aspera key found (run setup_real_ascp.sh)"; exit 1; }
APATH=$(curl -sS --max-time 30 "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR22904350&result=read_run&fields=fastq_aspera&format=tsv" | tail -1 | awk '{print $2}' | tr ';' '\n' | head -1 | cut -d: -f2-)
mkdir -p "$E5_WORK/_gate"
if timeout 60 ascp -i "$KEY" -P 33001 -QT -l 100m --policy fair "era-fasp@fasp.sra.ebi.ac.uk:${APATH}" "$E5_WORK/_gate/" 2>&1 | tee "$RUN_OUT/aspera_gate.log" | grep -q "Completed:"; then
    echo "  OK — Aspera transfer completed; UDP 33001 is open."
    rm -rf "$E5_WORK/_gate"
else
    cat >&2 <<'EOF'
[ERROR] Aspera handshake FAILED — UDP 33001 is blocked or the key is rejected.
        E5 cannot run on this node. Move to a DTN (data-transfer node) that allows
        outbound UDP 33001, or run E5 on a cloud VM and report it separately
        (parent plan §13). Do NOT substitute a stub.
EOF
    exit 1
fi

echo; echo "=== versions ==="
{ echo "date: $(date -Is)"; adaptiseq -v 2>&1 | head -1; ascp --version 2>&1 | grep -i version | head -1; } > "$RUN_OUT/versions.txt"

echo; echo "=== running panels ==="
status=0
PANELS="${PANELS:-5a 5b 5c}" bash "$REPO_DIR/bench/e5/run_e5.sh" all || status=$?

echo; echo "=== aggregating ==="
"$E5_PYTHON" "$REPO_DIR/bench/e5/aggregate_e5.py" --outdir "$RUN_OUT" 2>&1 | tee "$RUN_OUT/summary.txt" || true
cp "$REPO_DIR/bench/e5/"*.sh "$REPO_DIR/bench/e5/"*.py "$REPO_DIR/bench/e5/"*.sbatch "$RUN_OUT/" 2>/dev/null || true

echo "=== done (status=$status). Results: $RUN_OUT ==="
exit "$status"
