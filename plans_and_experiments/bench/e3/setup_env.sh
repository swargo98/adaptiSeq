#!/usr/bin/env bash
# One-time Expanse setup for E3. Run on a LOGIN node (it only installs; it must
# never benchmark -- EXPERIMENT_PLAN §13).
#
#   bash bench/e3/setup_env.sh
#
# Creates the `adaptiseq_e3` conda env with every E3 competitor pinned, then
# exports the env so the paper can ship an exact reproduction recipe (§12.4).

set -euo pipefail
# Anaconda's conda.sh dereferences $PS1, which is unbound in a non-interactive
# shell -- fatal under `set -u`. e3_expanse.sbatch guards the same way.
export PS1="${PS1:-}"

ENV_NAME="${ENV_NAME:-adaptiseq_e3}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
source "$(conda info --base)/etc/profile.d/conda.sh"

if conda env list | grep -qE "^${ENV_NAME}\s"; then
    echo "env ${ENV_NAME} already exists; activating."
else
    echo "=== creating ${ENV_NAME} ==="
    # mamba resolves this stack far faster than classic conda; fall back if absent.
    SOLVER="conda"
    command -v mamba >/dev/null 2>&1 && SOLVER="mamba"
    $SOLVER create -y -n "$ENV_NAME" -c conda-forge -c bioconda \
        python=3.11 \
        iseq \
        kingfisher \
        fastq-dl \
        sra-tools \
        pysradb \
        ffq \
        entrez-direct \
        aria2 axel wget pigz curl \
        "aiohttp>=3.8" "aioftp>=0.21" "numpy>=1.21" openpyxl psutil \
        pandas matplotlib
fi

conda activate "$ENV_NAME"

# The benchmark must run the released wheel, the same file on every machine --
# never an editable install. The wheel is kept so run_e3.sh can record its sha256
# (export E3_ASEQ_WHEEL=<path printed below>). Set E3_ASEQ_WHEEL beforehand to
# install a local wheel instead (e.g. a dry run before the release is on PyPI).
ASEQ_VERSION="${ASEQ_VERSION:-0.1.4}"
echo "=== installing adaptiSeq ${ASEQ_VERSION} (release wheel) ==="
cd "$REPO_DIR"
if [[ -z "${E3_ASEQ_WHEEL:-}" ]]; then
    mkdir -p "$REPO_DIR/wheels"
    pip download "adaptiseq==${ASEQ_VERSION}" --no-deps --only-binary :all: -d "$REPO_DIR/wheels"
    E3_ASEQ_WHEEL="$(ls "$REPO_DIR"/wheels/adaptiseq-"${ASEQ_VERSION}"-*.whl | head -1)"
fi
pip install --force-reinstall --no-deps "$E3_ASEQ_WHEEL"
python "$REPO_DIR/bench/e3/aseq_fingerprint.py" --wheel "$E3_ASEQ_WHEEL"
echo "export E3_ASEQ_WHEEL=$E3_ASEQ_WHEEL"

# nf-core/fetchngs is optional (ENABLE_FETCHNGS=1). It needs Nextflow +
# Singularity; Expanse ships singularitypro as a module.
if [[ "${WITH_FETCHNGS:-0}" == "1" ]]; then
    echo "=== installing nextflow for fetchngs ==="
    conda install -y -c bioconda nextflow
    module load singularitypro || true
    export NXF_SINGULARITY_CACHEDIR="${NXF_SINGULARITY_CACHEDIR:-/expanse/lustre/scratch/$USER/temp_project/singularity_cache}"
    mkdir -p "$NXF_SINGULARITY_CACHEDIR"
    nextflow pull nf-core/fetchngs -r 1.12.0 || true
fi

echo "=== verifying ==="
fail=0
for t in adaptiseq iseq kingfisher fastq-dl srapath vdb-validate aria2c axel pigz; do
    if command -v "$t" >/dev/null 2>&1; then
        printf '  OK   %-14s\n' "$t"
    else
        printf '  MISS %-14s\n' "$t"; fail=1
    fi
done

echo "=== pinning versions for the paper ==="
conda env export -n "$ENV_NAME" > "$REPO_DIR/bench/e3/env_${ENV_NAME}.yml"
echo "wrote bench/e3/env_${ENV_NAME}.yml"

# iseq's startup CheckSoftware gate insists on ascp even when the ENA path it
# actually takes is wget/axel. On a node without the Aspera SDK, drop a no-op
# stub on PATH purely to clear that gate -- iseq never invokes it for the -g ENA
# route we benchmark, so the comparison stays fair. This is the same device
# BENCHMARK.md documents. For real Aspera (E5) install the IBM SDK instead:
#   bash bench/setup_real_ascp.sh
if ! command -v ascp >/dev/null 2>&1; then
    echo "=== no ascp: installing no-op stub to satisfy iseq's preflight ==="
    cat > "${CONDA_PREFIX}/bin/ascp" <<'STUB'
#!/usr/bin/env bash
# No-op ascp stub -- present ONLY to clear iseq's CheckSoftware gate.
# E3 benchmarks the ENA wget/axel path (-g), which never calls ascp.
echo "ascp stub (adaptiSeq E3): not a real Aspera client" >&2
exit 0
STUB
    chmod +x "${CONDA_PREFIX}/bin/ascp"
fi

[[ $fail -eq 0 ]] && echo "=== env ready: conda activate ${ENV_NAME} ===" \
                  || { echo "[ERROR] some tools missing (see MISS above)"; exit 1; }
