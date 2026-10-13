#!/usr/bin/env bash
# E8 -- Resource profile on FABRIC (this dev box, Node-FIU). No Slurm.
#
# Fabric is a plain 8-core Linux box, so E8 runs the driver directly -- the same
# code Expanse runs under sbatch. The value of profiling on both machines: iSeq's
# Fig 1D is single-machine, but the resource envelope (esp. fasterq-dump CPU on the
# SRA panel, and RSS under an 8-core vs 128-core box) differs, and reporting both is
# a spread iSeq never shows.
#
#   bash bench/e8/run_fabric.sh                    # both panels
#   PANELS="8-ENA" bash bench/e8/run_fabric.sh     # subset
#   E8_SRA_ACC=SRRxxxxxxx bash bench/e8/run_fabric.sh
#
# Cheap (~1.5-3 h): single-file fetches; fasterq-dump conversion is the cost driver
# on 8 cores.

set -uo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR" || exit 1

if command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -qE '^adaptiseq_e3\s'; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate adaptiseq_e3
fi

export E8_PYTHON="${E8_PYTHON:-python3}"
export E8_WORK="${E8_WORK:-/tmp/e8_payload_$USER}"
export E8_OUT="${E8_OUT:-$REPO_DIR/e8_results_fabric}"
export E8_MD5_JOBS="${E8_MD5_JOBS:-8}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
export E8_SRA_ACC="${E8_SRA_ACC:-SRR1031060}"
mkdir -p "$E8_WORK" "$E8_OUT"

PANELS="${PANELS:-8-ENA 8-SRA}"
PANEL_ARG="${1:-all}"
REPS="${REPS:-}"

echo "=== adaptiSeq E8 on Fabric ($(hostname -s)) ==="
echo "python  : $(python3 --version 2>&1)   psutil $(python3 -c 'import psutil;print(psutil.__version__)' 2>/dev/null)"
echo "results : $E8_OUT"
echo "panels  : $PANELS   SRA_ACC=$E8_SRA_ACC"

echo; echo "=== egress check ==="
egress_ok=1
for host in https://ftp.sra.ebi.ac.uk https://www.ebi.ac.uk; do
    curl -sS -o /dev/null -w "  %{http_code} $host\n" --max-time 30 -I "$host" || egress_ok=0
done
[[ $egress_ok -ne 1 ]] && echo "[WARN] no egress -- E8 needs live downloads; results will be empty." >&2

echo; echo "=== tool check ==="
for t in adaptiseq iseq kingfisher prefetch fasterq-dump vdb-validate md5sum curl; do
    command -v "$t" >/dev/null 2>&1 && printf '  OK   %-14s\n' "$t" || printf '  MISS %-14s (that arm is skipped/fails)\n' "$t"
done

echo; echo "=== datasets ==="
"$E8_PYTHON" "$REPO_DIR/bench/e3/make_datasets.py" --outdir "$DATASETS" 2>&1 | tail -12 || \
    echo "[WARN] dataset rebuild failed; using committed $DATASETS"

echo; echo "=== running ==="
if [[ "$PANEL_ARG" == "all" ]]; then
    PANELS="$PANELS" bash "$REPO_DIR/bench/e8/run_e8.sh" all "$REPS"
else
    bash "$REPO_DIR/bench/e8/run_e8.sh" "$PANEL_ARG" "$REPS"
fi

echo; echo "=== aggregating ==="
"$E8_PYTHON" "$REPO_DIR/bench/e8/aggregate_e8.py" --outdir "$E8_OUT" 2>&1 | tee "$E8_OUT/summary.txt" || true

echo "=== done. Results: $E8_OUT ==="
