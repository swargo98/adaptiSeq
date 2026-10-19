#!/usr/bin/env bash
# The submission benchmark on a machine without Slurm (Fabric). On Expanse use
# e3_expanse.sbatch, which runs the same gates and the same driver.
#
#   export E3_ASEQ_WHEEL=$PWD/wheels/adaptiseq-0.1.4-py3-none-any.whl
#   bash bench/e3/run_submission.sh gate     # one rep of 3r + 3b, then the checks
#   nohup bash bench/e3/run_submission.sh full > run_submission.log 2>&1 &   # 5 reps, ~14 h
#
# Both modes: egress check, tool check, by-hand md5 check on 3 runs, the panels
# (arms strictly sequential, order permuted per rep), then check_run.py.
# Results go to a fresh directory per invocation, so a gate run can never be
# mixed into the full run's TSV.

set -uo pipefail
E3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E3_DIR/../.." && pwd)"
cd "$REPO_DIR" || exit 1

MODE="${1:-gate}"
case "$MODE" in
  gate) REPS=1 ;;
  full) REPS="${REPS:-5}" ;;
  *) echo "usage: $0 gate|full" >&2; exit 2 ;;
esac

if command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -qE '^adaptiseq_e3\s'; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate adaptiseq_e3
fi

export E3_PYTHON="${E3_PYTHON:-python3}"
export PANELS="${PANELS:-3r 3b}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
export E3_WORK="${E3_WORK:-/tmp/e3_payload_$USER}"
export E3_OUT="${E3_OUT:-$REPO_DIR/e3_submission_$(hostname -s)_${MODE}_$(date +%Y%m%d_%H%M%S)}"
export E3_MD5_JOBS="${E3_MD5_JOBS:-8}"
mkdir -p "$E3_WORK" "$E3_OUT"

echo "=== adaptiSeq submission benchmark: $MODE on $(hostname -s) ==="
echo "panels  : $PANELS   reps=$REPS"
echo "wheel   : ${E3_ASEQ_WHEEL:-<not set>}"
echo "payload : $E3_WORK   ($(df -h "$E3_WORK" | awk 'NR==2{print $4}') free; 3b needs ~30 GB)"
echo "results : $E3_OUT"

echo; echo "=== egress check ==="
for host in https://ftp.sra.ebi.ac.uk https://www.ebi.ac.uk https://ftp.ncbi.nlm.nih.gov; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -I "$host" 2>&1) \
        && echo "  OK   $host -> $code" \
        || { echo "  FAIL $host ($code)"; echo "[ERROR] no egress to the archives." >&2; exit 1; }
done

echo; echo "=== tool check ==="
missing=0
for t in adaptiseq iseq kingfisher fastq-dl axel wget aria2c srapath vdb-validate md5sum; do
    if command -v "$t" >/dev/null 2>&1; then
        printf '  OK   %-14s %s\n' "$t" "$(command -v "$t")"
    else
        printf '  MISS %-14s\n' "$t"; missing=1
    fi
done
[[ $missing -eq 1 ]] && { echo "[ERROR] missing tools; see bench/e3/setup_env.sh" >&2; exit 1; }

# Same step as e3_expanse.sbatch: refresh sizes/md5s from ENA on the day of the
# run (the lists themselves are seeded, so both machines get the same runs).
echo; echo "=== datasets ==="
"$E3_PYTHON" "$E3_DIR/make_datasets.py" --outdir "$DATASETS" 2>&1 | tee "$E3_OUT/datasets_build.log" | tail -12 \
    || echo "[WARN] dataset rebuild failed; using the committed $DATASETS"

echo; echo "=== manual md5 check ==="
if ! "$E3_PYTHON" "$E3_DIR/manual_md5_check.py" \
        --manifest "$DATASETS/D1_full_PRJNA916347.manifest" 2>&1 | tee "$E3_OUT/manual_md5_check.txt"; then
    echo "[ERROR] manual md5 check failed; not starting the benchmark." >&2
    exit 1
fi
cp -r "$DATASETS" "$E3_OUT/datasets_used" 2>/dev/null || true

echo; echo "=== running panels ==="
status=0
bash "$E3_DIR/run_e3.sh" all "$REPS" || status=$?

echo; echo "=== check ==="
"$E3_PYTHON" "$E3_DIR/check_run.py" --tsv "$E3_OUT/e3_results.tsv" \
    --panels $PANELS --reps "$REPS" 2>&1 | tee "$E3_OUT/check_run.txt" || status=1

echo "=== done (status=$status). Results: $E3_OUT ==="
exit "$status"
