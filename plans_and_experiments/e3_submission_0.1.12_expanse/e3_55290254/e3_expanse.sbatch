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
# Submit from the directory that contains bench/ and datasets/:
#   export E3_ASEQ_WHEEL=$PWD/wheels/adaptiseq-0.1.4-py3-none-any.whl
#   sbatch --export=ALL bench/e3/e3_expanse.sbatch                 # 3r + 3b, 5 reps (the paper run)
#   REPS=1 sbatch --export=ALL bench/e3/e3_expanse.sbatch          # the gate: one rep of both
#   PANELS="3a 3b" ARM_SET=legacy sbatch --export=ALL bench/e3/e3_expanse.sbatch

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
ENV_NAME="${ENV_NAME:-adaptiseq_e3}"
conda activate "$ENV_NAME" || { echo "[ERROR] conda env '$ENV_NAME' missing. Run bench/e3/setup_env.sh first." >&2; exit 1; }
export PATH="${CONDA_PREFIX}/bin:$PATH"

REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_DIR" || exit 1
[[ -f "$REPO_DIR/bench/e3/run_e3.sh" ]] || { echo "[ERROR] submit from the directory that contains bench/e3 (got $REPO_DIR)" >&2; exit 1; }
export PANELS="${PANELS:-3r 3b}"
REPS="${REPS:-5}"
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
echo "panels      : $PANELS  (reps=$REPS from rep ${E3_REP_FIRST:-1}, arm set=${ARM_SET:-submission})"
echo "wheel       : ${E3_ASEQ_WHEEL:-<not set>}"

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

# The machine, for the paper's methods paragraph.
{
    echo "date: $(date -Is)"; echo "node: $(hostname -s)"; echo "kernel: $(uname -r)"
    lscpu 2>/dev/null | grep -E '^(Model name|Socket\(s\)|Core\(s\) per socket|Thread\(s\) per core|CPU\(s\)):'
    echo "memory: $(free -g | awk '/^Mem:/{print $2}') GB"
    echo "local scratch: $(df -h "$NVME_DIR" | awk 'NR==2{print $2" total, "$4" free, "$1}')"
    echo "os: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-?}")"
} > "$RUN_OUT/machine.txt" 2>&1
cat "$RUN_OUT/machine.txt"

echo; echo "=== versions (pinned for the paper) ==="
{
    echo "date: $(date -Is)"; echo "node: $(hostname -s)"
    adaptiseq -v 2>&1 | head -1
    "$E3_PYTHON" "$REPO_DIR/bench/e3/aseq_fingerprint.py" ${E3_ASEQ_WHEEL:+--wheel "$E3_ASEQ_WHEEL"} 2>&1
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
# A 1.3 GB file, so the transfer is still in progress when the 20 s window ends.
# (The 17 KB file used before finished in one round trip and measured nothing.)
# ENA has limited throughput per connection since at least 2026-10, so the rate
# at 1, 8, and 20 connections is what explains the single-stream arms.
echo; echo "=== link ceiling probe (ENA, 1 / 8 / 20 connections, 20 s each) ==="
{
    PROBE="https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR158/000/SRR15852400/SRR15852400_1.fastq.gz"
    echo "date: $(date -Is)  node: $(hostname -s)  public ip: $(curl -s --max-time 10 https://api.ipify.org || echo '?')"
    for P in 1 8 20; do
        tmp="$(mktemp)"
        for i in $(seq 0 $((P - 1))); do
            s=$((i * 60000000)); e=$((s + 59999999))
            curl -so /dev/null -r "$s-$e" -w '%{speed_download}\n' --max-time 20 "$PROBE" >> "$tmp" &
        done
        wait
        awk -v p="$P" '{s+=$1; n++} END{printf "  P=%-2d  total %.1f MB/s  (%.2f MB/s per connection, %d reported)\n", p, s/1e6, (n? s/1e6/n : 0), n}' "$tmp"
        rm -f "$tmp"
    done
} 2>&1 | tee "$RUN_OUT/link_probe.txt"

# ─── GATE 3: the md5 verifier agrees with a by-hand check ─────────────────
# Three runs fetched with curl, hashed, compared with ENA and the manifest, then
# judged by verify_output.py. A stale manifest or a bad mirror stops the job here.
echo; echo "=== manual md5 check ==="
if ! "$E3_PYTHON" "$REPO_DIR/bench/e3/manual_md5_check.py" \
        --manifest "$DATASETS/D1_full_PRJNA916347.manifest" 2>&1 | tee "$RUN_OUT/manual_md5_check.txt"; then
    echo "[ERROR] manual md5 check failed; not starting the benchmark." >&2
    exit 1
fi

# ─── Run ───────────────────────────────────────────────────────────────────
echo; echo "=== running panels ==="
status=0
bash "$REPO_DIR/bench/e3/run_e3.sh" all "$REPS" || status=$?

# ─── Aggregate ─────────────────────────────────────────────────────────────
echo; echo "=== aggregating ==="
"$E3_PYTHON" "$REPO_DIR/bench/e3/aggregate.py" \
    --tsv "$RUN_OUT/e3_results.tsv" --outdir "$RUN_OUT" 2>&1 | tee "$RUN_OUT/summary.txt" || true
"$E3_PYTHON" "$REPO_DIR/bench/e3/check_run.py" --tsv "$RUN_OUT/e3_results.tsv" \
    --panels $PANELS --reps "$REPS" --rep-first "${E3_REP_FIRST:-1}" 2>&1 | tee "$RUN_OUT/check_run.txt" || true

cp "$REPO_DIR/bench/e3/"*.sh "$REPO_DIR/bench/e3/"*.py "$REPO_DIR/bench/e3/"*.sbatch "$RUN_OUT/" 2>/dev/null || true
for f in "slurm_e3_${SLURM_JOB_ID}.out" "slurm_e3_${SLURM_JOB_ID}.err"; do
    [[ -f "$f" ]] && cp "$f" "$RUN_OUT/"
done
# payload purge is handled by the EXIT trap

echo "=== done (status=$status). Results: $RUN_OUT ==="
echo "kept: TSV + logs + manifests + versions (a few MB). Downloaded fastq: discarded."
exit "$status"
