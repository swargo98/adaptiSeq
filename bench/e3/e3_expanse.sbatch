#!/bin/bash
#SBATCH --job-name=adaptiseq_e3
#SBATCH --account=umr115
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=128          # whole node: E3 must not share a NIC (see below)
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --time=48:00:00
#SBATCH --output=slurm_e3_%j.out
#SBATCH --error=slurm_e3_%j.err
#
# E3 -- Batch download (headline, Fig 3) on SDSC Expanse.
#
# WHY A WHOLE EXCLUSIVE NODE, AND WHY NOT A JOB ARRAY
# ---------------------------------------------------
# The instinct is to fan (tool x dataset x rep) out over a job array. Do not.
# Every arm of E3 measures download throughput over the SAME shared external
# link. Concurrent array tasks would contend with each other for that link, and
# each arm's measured MB/s would then depend on what happened to be co-scheduled
# beside it -- the one confound that would invalidate the entire figure.
# iSeq (btae641) benchmarked "under consistent conditions: the same computing
# cluster, at the same time, with identical network settings" for exactly this
# reason. So: ONE node, ONE job, arms run STRICTLY SEQUENTIALLY, order reshuffled
# per rep. --exclusive keeps a noisy neighbour off our NIC.
#
# Corollary: do not submit 3a/3b/3c simultaneously either. Use `--dependency`
# (see submit_e3.sh) or run panel `all` in one job.
#
# Submit:  sbatch bench/e3/e3_expanse.sbatch          # runs every panel
#          PANELS="3a 3b" sbatch bench/e3/e3_expanse.sbatch

set -uo pipefail
export PS1="${PS1:-}"

# ─── Environment ───────────────────────────────────────────────────────────
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
module load singularitypro 2>/dev/null || true   # only needed if ENABLE_FETCHNGS=1

CONDA_BASE="$(conda info --base 2>/dev/null || true)"
if [[ -z "$CONDA_BASE" || ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
    echo "[ERROR] Could not locate conda.sh after loading the anaconda module." >&2
    exit 1
fi
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate adaptiseq_e3 || { echo "[ERROR] conda env 'adaptiseq_e3' missing. Run bench/e3/setup_env.sh first." >&2; exit 1; }
export PATH="${CONDA_PREFIX}/bin:$PATH"

REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_DIR" || exit 1
E3_PYTHON="${CONDA_PREFIX}/bin/python3"
export E3_PYTHON

# ─── Storage: payload on node-local NVMe, results on Lustre ────────────────
# EXPERIMENT_PLAN §13 says "never $HOME (NFS)". We go one better than Lustre for
# the PAYLOAD: Expanse compute nodes carry ~1 TB of local NVMe, and writing the
# fastq there keeps Lustre metadata/OST contention (a shared, bursty resource)
# out of the download timings entirely. Since every arm's payload is deleted
# straight after it is hashed, we never need the capacity or the persistence.
# RESULTS (TSV/logs) go to Lustre, which survives the job.
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
RESULTS_ROOT="${RESULTS_ROOT:-$LUSTRE_ROOT/adaptiseq_e3}"
RUN_OUT="$RESULTS_ROOT/e3_${SLURM_JOB_ID:-manual}"
mkdir -p "$RUN_OUT" || { echo "[ERROR] cannot create $RUN_OUT" >&2; exit 1; }

export E3_WORK="$NVME_DIR/e3_payload"
export E3_OUT="$RUN_OUT"
export E3_MD5_JOBS="${E3_MD5_JOBS:-64}"     # 128-core node: hash the tree fast
export DATASETS="$REPO_DIR/datasets"
mkdir -p "$E3_WORK"

# Slurm sends SIGTERM before SIGKILL at the walltime limit, and scancel sends it
# immediately -- so hitting the 48 h cap mid-transfer must not strand hundreds of
# GB of fastq on the node's NVMe. Purge payload on any exit path. Results
# ($RUN_OUT, on Lustre) are deliberately untouched: those are the experiment.
_e3_job_cleanup() {
    local rc=$?
    trap - EXIT INT TERM
    echo "[cleanup] removing payload $E3_WORK ($(du -sh "$E3_WORK" 2>/dev/null | cut -f1))"
    rm -rf "$E3_WORK" 2>/dev/null || true
    exit $rc
}
trap _e3_job_cleanup EXIT INT TERM

# Higher NCBI rate limit if a key is present (E10 also depends on this).
# export NCBI_API_KEY="..."
# export NCBI_EMAIL="..."

echo "=== adaptiSeq E3 (batch download, Fig 3) ==="
echo "node        : $(hostname -s)"
echo "repo        : $REPO_DIR"
echo "python      : $E3_PYTHON  ($(python3 --version 2>&1))"
echo "payload     : $E3_WORK   ($(df -h "$NVME_DIR" | awk 'NR==2{print $4}') free)"
echo "results     : $RUN_OUT"
echo "panels      : ${PANELS:-3a 3r 3b 3c 3d}"

# ─── GATE 1: outbound egress (EXPERIMENT_PLAN §16.1 -- gate everything) ────
echo; echo "=== egress check ==="
egress_ok=1
for host in https://ftp.sra.ebi.ac.uk https://www.ebi.ac.uk https://ftp.ncbi.nlm.nih.gov; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -I "$host" 2>&1) \
        && echo "  OK   $host -> $code" \
        || { echo "  FAIL $host ($code)"; egress_ok=0; }
done
if [[ $egress_ok -ne 1 ]]; then
    cat >&2 <<'EOF'
[ERROR] Compute node cannot reach the public archives.
        Every E3 number would be an artefact of the proxy, not the tools.
        Fix before running: set https_proxy/ftp_proxy IDENTICALLY for all tools
        (fairness, §13) and document it, or move to a node/DTN with egress.
EOF
    exit 1
fi

# ─── GATE 2: every tool present ───────────────────────────────────────────
echo; echo "=== tool check ==="
missing=0
for t in adaptiseq iseq kingfisher fastq-dl axel wget aria2c srapath vdb-validate md5sum; do
    if command -v "$t" >/dev/null 2>&1; then
        printf '  OK   %-14s %s\n' "$t" "$(command -v "$t")"
    else
        printf '  MISS %-14s\n' "$t"; missing=1
    fi
done
# adaptiSeq's preflight requires srapath+vdb-validate whenever md5 checking is ON
# (cli.py::_cli_preflight). We deliberately run WITH md5 checking, so these are
# not optional -- a missing sra-tools would silently push us onto -k and quietly
# drop integrity from the headline figure.
[[ $missing -eq 1 ]] && { echo "[ERROR] missing tools; run bench/e3/setup_env.sh" >&2; exit 1; }

echo; echo "=== versions (pinned for the paper) ==="
{
    echo "date: $(date -Is)"; echo "node: $(hostname -s)"
    adaptiseq -v 2>&1 | head -1
    iseq -v 2>&1 | head -2 | tail -1
    kingfisher --version 2>&1 | head -1
    fastq-dl --version 2>&1 | head -1
    python3 --version
    conda list --export 2>/dev/null
} > "$RUN_OUT/versions.txt"
head -8 "$RUN_OUT/versions.txt"

# ─── Datasets: re-pull sizes/md5s on the day of the run ───────────────────
echo; echo "=== datasets ==="
"$E3_PYTHON" "$REPO_DIR/bench/e3/make_datasets.py" --outdir "$DATASETS" \
    2>&1 | tee "$RUN_OUT/datasets_build.log"
cp -r "$DATASETS" "$RUN_OUT/datasets_used" 2>/dev/null || true

# ─── Baseline link capacity (context for §11 / E9, and for reading Fig 3) ──
echo; echo "=== link ceiling probe (single + 8-stream, ENA) ==="
{
    PROBE="https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR229/053/SRR22904253/SRR22904253.fastq.gz"
    echo "single-stream:"
    curl -so /dev/null -w '  %{speed_download} B/s (%{size_download} B)\n' --max-time 120 "$PROBE"
    if command -v aria2c >/dev/null; then
        echo "aria2c -x8 -s8:"
        ( cd "$E3_WORK" && timeout 180 aria2c -x8 -s8 -q --allow-overwrite=true -d . "$PROBE" \
            && echo "  ok" ; rm -f "$E3_WORK"/SRR22904253.fastq.gz* )
    fi
} 2>&1 | tee "$RUN_OUT/link_probe.txt"

# ─── Run ───────────────────────────────────────────────────────────────────
echo; echo "=== running panels ==="
status=0
PANELS="${PANELS:-3a 3r 3b 3c 3d}" bash "$REPO_DIR/bench/e3/run_e3.sh" all || status=$?

# ─── Aggregate ─────────────────────────────────────────────────────────────
echo; echo "=== aggregating ==="
"$E3_PYTHON" "$REPO_DIR/bench/e3/aggregate.py" \
    --tsv "$RUN_OUT/e3_results.tsv" --outdir "$RUN_OUT" 2>&1 | tee "$RUN_OUT/summary.txt" || true

cp "$REPO_DIR/bench/e3/"*.sh "$REPO_DIR/bench/e3/"*.py "$REPO_DIR/bench/e3/"*.sbatch "$RUN_OUT/" 2>/dev/null || true
for f in "slurm_e3_${SLURM_JOB_ID}.out" "slurm_e3_${SLURM_JOB_ID}.err"; do
    [[ -f "$f" ]] && cp "$f" "$RUN_OUT/"
done
# payload purge is handled by the EXIT trap

echo "=== done (status=$status). Results: $RUN_OUT ==="
echo "kept: TSV + logs + manifests + versions (a few MB). Downloaded fastq: discarded."
exit "$status"
