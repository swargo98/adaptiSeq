#!/bin/bash
#SBATCH --job-name=adaptiseq_setup
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=slurm_setup_%j.out
#SBATCH --error=slurm_setup_%j.err
#
# Everything the benchmark needs that is not the benchmark, run on a compute
# node (the login nodes cap virtual memory at 8 GB, which kills the conda
# install step, and they are not for this kind of work anyway):
#
#   1. create the benchmark conda env from pinned builds;
#   2. build the adaptiSeq wheel and sdist from this checkout and install it;
#   3. run the test suite, offline and then with the network;
#   4. run the README's CLI and Python examples from the wheel in a clean venv;
#   5. measure ENA throughput at 1, 8, and 20 connections from a compute node.
#
# Submit from the directory that contains bench/ and datasets/:
#   sbatch bench/e3/setup_expanse.sbatch
#
# Knobs: ENV_NAME (default adaptiseq_e3_sub), ENV_FILE (default the yml exported
# on the Fabric node, so both machines get the same builds), SKIP_BUILD=1 to
# keep the wheel already in wheels/, SKIP_TESTS=1, SKIP_README=1.

set -uo pipefail
export PS1="${PS1:-}"

module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
export PATH="$HOME/bin:$PATH"          # mamba, if the user has one

REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_DIR" || exit 1
[[ -f "$REPO_DIR/bench/e3/setup_env.sh" ]] || { echo "[ERROR] submit from the directory that contains bench/e3 (got $REPO_DIR)" >&2; exit 1; }
SRC_DIR="$(cd "$REPO_DIR/.." && pwd)"   # the adaptiSeq checkout (pyproject.toml)

export ENV_NAME="${ENV_NAME:-adaptiseq_e3_sub}"
export ENV_FILE="${ENV_FILE:-$REPO_DIR/bench/e3/env_adaptiseq_e3.yml}"
OUT="${SETUP_OUT:-$REPO_DIR/setup_expanse_${SLURM_JOB_ID:-manual}}"
mkdir -p "$OUT"

TMP="${SLURM_TMPDIR:-/scratch/$USER/job_${SLURM_JOB_ID:-manual}}"
mkdir -p "$TMP" 2>/dev/null || TMP="$(mktemp -d)"
trap 'rm -rf "$TMP/venv" "$TMP/venv_test" "$TMP/build" "$TMP/dist" 2>/dev/null' EXIT

source "$(conda info --base)/etc/profile.d/conda.sh"

echo "=== setup on $(hostname -s) at $(date -Is) ==="
echo "checkout : $SRC_DIR  ($(git -C "$SRC_DIR" rev-parse --short HEAD 2>/dev/null), $(git -C "$SRC_DIR" status --porcelain 2>/dev/null | wc -l) uncommitted paths)"
echo "env      : $ENV_NAME  from  $ENV_FILE"
echo "output   : $OUT"
status=0

# ─── 1. environment ────────────────────────────────────────────────────────
# First, because the wheel is built with the env's Python (the build backend
# needs Python >= 3.9; the anaconda module's is older). setup_env.sh installs
# whatever wheel is already in wheels/; step 2 replaces it.
VERSION="$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' "$SRC_DIR/adaptiseq/__init__.py" | head -1)"
export E3_ASEQ_WHEEL="$REPO_DIR/wheels/adaptiseq-${VERSION}-py3-none-any.whl"
[[ -f "$E3_ASEQ_WHEEL" ]] || unset E3_ASEQ_WHEEL      # setup_env.sh then tries PyPI
echo; echo "=== environment ==="
bash "$REPO_DIR/bench/e3/setup_env.sh" > "$OUT/setup_env.log" 2>&1 \
    || { echo "[ERROR] setup_env.sh failed; tail of $OUT/setup_env.log:" >&2; tail -20 "$OUT/setup_env.log" >&2; exit 1; }
grep -E '^(  OK|  MISS|=== env ready)' "$OUT/setup_env.log"
conda activate "$ENV_NAME" || exit 1
export PATH="${CONDA_PREFIX}/bin:$PATH"
E3_PYTHON_FOR_VERIFY="${CONDA_PREFIX}/bin/python"

# ─── 2. wheel ──────────────────────────────────────────────────────────────
# Built in a throwaway venv so build tools never enter the benchmark env, from a
# copy of the tracked and untracked-but-not-ignored files, which keeps build/ and
# *.egg-info out of the checkout.
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
    echo; echo "=== building adaptiSeq $VERSION ==="
    python -m venv "$TMP/venv" && "$TMP/venv/bin/pip" -q install --upgrade pip build twine \
        || { echo "[ERROR] could not create the build venv" >&2; exit 1; }
    mkdir -p "$TMP/build"
    git -C "$SRC_DIR" ls-files -z --cached --others --exclude-standard -- \
            adaptiseq tests LICENSE README.md pyproject.toml MANIFEST.in \
        | (cd "$SRC_DIR" && xargs -0 cp --parents -t "$TMP/build")
    ( cd "$TMP/build" && "$TMP/venv/bin/python" -m build --outdir "$TMP/dist" . ) > "$OUT/build.log" 2>&1 \
        || { echo "[ERROR] build failed; see $OUT/build.log" >&2; exit 1; }
    "$TMP/venv/bin/twine" check "$TMP"/dist/* 2>&1 | tee "$OUT/twine_check.txt"
    mkdir -p "$REPO_DIR/wheels"
    cp "$TMP"/dist/adaptiseq-"$VERSION"* "$REPO_DIR/wheels/"
fi
export E3_ASEQ_WHEEL="$REPO_DIR/wheels/adaptiseq-${VERSION}-py3-none-any.whl"
[[ -f "$E3_ASEQ_WHEEL" ]] || { echo "[ERROR] no wheel at $E3_ASEQ_WHEEL" >&2; exit 1; }
( cd "$REPO_DIR/wheels" && sha256sum adaptiseq-"$VERSION"* ) | tee "$OUT/wheel_sha256.txt"
pip install -q --force-reinstall --no-deps "$E3_ASEQ_WHEEL" || exit 1
conda env export -n "$ENV_NAME" > "$REPO_DIR/bench/e3/env_${ENV_NAME}.yml"

{
    echo "date: $(date -Is)"; echo "node: $(hostname -s)"
    python "$REPO_DIR/bench/e3/aseq_fingerprint.py" --wheel "$E3_ASEQ_WHEEL"
    echo "iseq: $(iseq -v 2>&1 | grep -m1 -i version)"
    echo "kingfisher: $(kingfisher --version 2>&1 | head -1)"
    echo "fastq-dl: $(fastq-dl --version 2>&1 | head -1)"
    echo "sra-tools: $(prefetch --version 2>&1 | grep -m1 -o '[0-9][0-9.]*')"
    echo "aria2c: $(aria2c --version 2>&1 | head -1)"
    echo "axel: $(axel --version 2>&1 | head -1)"
    echo "wget: $(wget --version 2>&1 | head -1)"
    echo "curl: $(curl --version 2>&1 | head -1)"
    python --version
} 2>&1 | tee "$OUT/versions.txt"
grep -q '^aseq_version=' "$OUT/versions.txt" || { echo "[ERROR] installed adaptiSeq is not the wheel just built" >&2; exit 1; }

# ─── 3. tests ──────────────────────────────────────────────────────────────
# Run from the checkout, which the tests expect (tests/conftest.py puts the
# repository root on sys.path). The wheel above was built from these same files.
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
    python -m venv --system-site-packages "$TMP/venv_test" \
        && "$TMP/venv_test/bin/pip" -q install "pytest>=7.0" pytest-timeout \
        || { echo "[ERROR] could not create the test venv" >&2; exit 1; }
    cd "$SRC_DIR" || exit 1
    export PYTHONDONTWRITEBYTECODE=1

    echo; echo "=== tests, offline (ADAPTISEQ_NO_NETWORK=1) ==="
    ADAPTISEQ_NO_NETWORK=1 "$TMP/venv_test/bin/python" -m pytest -q -p no:cacheprovider --timeout=600 \
        > "$OUT/pytest_offline.txt" 2>&1 || status=1
    tail -3 "$OUT/pytest_offline.txt"

    echo; echo "=== tests, with network ==="
    timeout 4500 "$TMP/venv_test/bin/python" -m pytest -q -p no:cacheprovider --timeout=900 -rfEs \
        > "$OUT/pytest_network.txt" 2>&1 || status=1
    tail -25 "$OUT/pytest_network.txt"
    cd "$REPO_DIR" || exit 1
fi

# ─── 4. the README examples, from the wheel alone ──────────────────────────
# Submission checklist: "pip install adaptiseq==0.1.4 in a fresh environment runs
# the README example". A clean venv (no site packages from the conda env) gets
# the wheel and its dependencies from PyPI; wget, sra-tools and pigz come from
# PATH, as the README says they must. Three small runs stand in for the list.
readme_check() {
    local venv="$TMP/venv_clean" work="$TMP/readme_example" v
    python -m venv "$venv" || return 1
    "$venv/bin/pip" -q install "$E3_ASEQ_WHEEL" || return 1
    "$venv/bin/pip" list 2>/dev/null | grep -i -E '^(adaptiseq|aiohttp|aioftp|numpy) '
    rm -rf "$work"; mkdir -p "$work/cli" "$work/api"
    cp "$REPO_DIR/datasets/SMOKE_D1.txt" "$work/accessions.txt"
    "$venv/bin/adaptiseq" --version || return 1

    echo "--- CLI: adaptiseq -i accessions.txt -g"
    ( cd "$work/cli" && "$venv/bin/adaptiseq" -i ../accessions.txt -g ) || { echo "cli exit: $?"; return 1; }
    echo "cli exit: 0"
    v="$("$E3_PYTHON_FOR_VERIFY" "$REPO_DIR/bench/e3/verify_output.py" \
            --manifest "$REPO_DIR/datasets/SMOKE_D1.manifest" --outdir "$work/cli" --jobs 4)"
    echo "cli verify: $v"
    [[ "$v" == *"runs_complete=3 "* ]] || return 1

    echo "--- Python API"
    ( cd "$work/api" && "$venv/bin/python" - <<'PY'
from adaptiseq import fetch, resolve, get_metadata

first = open("../accessions.txt").read().split()[0]
rows = get_metadata(first)
urls = resolve(first, database="ena")
print("get_metadata:", len(rows), "row(s);", "resolve:", urls)
result = fetch("../accessions.txt", outdir="data/", gzip=True, jobs=20, adaptive=True)
print("fetch:", result.success_ids, result.fail_ids, result.failed)
assert not result.failed and not result.fail_ids
PY
    ) || { echo "api exit: $?"; return 1; }
    echo "api exit: 0"
    v="$("$E3_PYTHON_FOR_VERIFY" "$REPO_DIR/bench/e3/verify_output.py" \
            --manifest "$REPO_DIR/datasets/SMOKE_D1.manifest" --outdir "$work/api/data" --jobs 4)"
    echo "api verify: $v"
    [[ "$v" == *"runs_complete=3 "* ]] || return 1
}
if [[ "${SKIP_README:-0}" != "1" ]]; then
    echo; echo "=== README examples in a clean venv ==="
    if readme_check > "$OUT/readme_example.txt" 2>&1; then
        echo "README examples: PASS"
    else
        echo "README examples: FAIL (see $OUT/readme_example.txt)"; status=1
    fi
    grep -E '^(adaptiseq|cli exit|api exit|fetch:|cli verify|api verify)' "$OUT/readme_example.txt" | cut -c1-200
    rm -rf "$TMP/venv_clean" "$TMP/readme_example"
fi

# ─── 5. ENA throughput from a compute node ─────────────────────────────────
echo; echo "=== ENA probe (1 / 8 / 20 connections, 20 s each) ==="
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
} 2>&1 | tee "$OUT/link_probe.txt"

for f in "slurm_setup_${SLURM_JOB_ID:-}.out" "slurm_setup_${SLURM_JOB_ID:-}.err"; do
    [[ -f "$REPO_DIR/$f" ]] && cp "$REPO_DIR/$f" "$OUT/"
done
echo "=== setup done (status=$status) at $(date -Is). Output: $OUT ==="
echo "export E3_ASEQ_WHEEL=$E3_ASEQ_WHEEL"
exit "$status"
