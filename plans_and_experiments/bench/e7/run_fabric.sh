#!/usr/bin/env bash
# E7 -- Reliability & resumability on FABRIC (this dev box, Node-FIU). No Slurm.
#
# Fabric is a plain Linux box (8 cores, 62 GB), so E7 just runs the driver
# directly -- the same code Expanse runs under sbatch. Two Fabric-specific things:
#   * payload goes to /tmp (no Lustre/NVMe split needed);
#   * E7_LIVE_THROTTLE=1 -- Fabric's egress to EBI throttles high concurrency
#     (429/550), so 7d captures the circuit breaker firing on REAL infrastructure,
#     which Expanse cannot (it never throttles). This is the cross-machine payoff,
#     exactly as it was for E3.
#
#   bash bench/e7/run_fabric.sh                 # all sub-experiments
#   PANELS="7c 7d" bash bench/e7/run_fabric.sh  # subset
#   REPS=2 bash bench/e7/run_fabric.sh 7a       # single sub-exp, custom reps
#
# NOTE: this monopolises the box for several hours (see the walltime table in
# docs/EXPERIMENT_PLAN_E7.md §6). Run it when nothing else needs the machine.

set -uo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR" || exit 1

# Prefer the E3 conda env if present; otherwise fall back to whatever python3 is
# active (adaptiSeq installed editable). iseq/kingfisher must be on PATH.
if command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -qE '^adaptiseq_e3\s'; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate adaptiseq_e3
fi

export E7_PYTHON="${E7_PYTHON:-python3}"
export E7_WORK="${E7_WORK:-/tmp/e7_payload_$USER}"
export E7_OUT="${E7_OUT:-$REPO_DIR/e7_results_fabric}"
export E7_MD5_JOBS="${E7_MD5_JOBS:-8}"       # 8-core box
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
export E7_LIVE_THROTTLE=1                     # the Fabric-only live circuit-breaker panel
mkdir -p "$E7_WORK" "$E7_OUT"

PANELS="${PANELS:-7a 7b 7c 7d 7e}"
PANEL_ARG="${1:-all}"
REPS="${REPS:-}"

echo "=== adaptiSeq E7 on Fabric ($(hostname -s)) ==="
echo "python  : $(python3 --version 2>&1)"
echo "payload : $E7_WORK   ($(df -h "$E7_WORK" | awk 'NR==2{print $4}') free)"
echo "results : $E7_OUT"
echo "panels  : $PANELS"

# ─── egress gate (7a/7b/7e need it; 7c/7d-synthetic do not) ────────────────
echo; echo "=== egress check ==="
egress_ok=1
for host in https://ftp.sra.ebi.ac.uk https://www.ebi.ac.uk; do
    curl -sS -o /dev/null -w "  %{http_code} $host\n" --max-time 30 -I "$host" || egress_ok=0
done
if [[ $egress_ok -ne 1 ]]; then
    echo "[WARN] no egress -- only the local sub-experiments (7c, 7d-synthetic) will produce data." >&2
fi

# ─── tools ─────────────────────────────────────────────────────────────────
echo; echo "=== tool check ==="
for t in adaptiseq iseq kingfisher srapath vdb-validate md5sum curl; do
    command -v "$t" >/dev/null 2>&1 && printf '  OK   %-14s\n' "$t" || printf '  MISS %-14s (some arms will be skipped/fail)\n' "$t"
done

echo; echo "=== datasets ==="
"$E7_PYTHON" "$REPO_DIR/bench/e3/make_datasets.py" --outdir "$DATASETS" 2>&1 | tail -12 || \
    echo "[WARN] dataset rebuild failed; using whatever is committed in $DATASETS"

echo; echo "=== running ==="
if [[ "$PANEL_ARG" == "all" ]]; then
    PANELS="$PANELS" bash "$REPO_DIR/bench/e7/run_e7.sh" all "$REPS"
else
    bash "$REPO_DIR/bench/e7/run_e7.sh" "$PANEL_ARG" "$REPS"
fi

echo; echo "=== aggregating ==="
"$E7_PYTHON" "$REPO_DIR/bench/e7/aggregate_e7.py" --outdir "$E7_OUT" 2>&1 | tee "$E7_OUT/summary.txt" || true

echo "=== done. Results: $E7_OUT ==="
