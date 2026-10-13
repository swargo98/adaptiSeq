#!/usr/bin/env bash
# E5 -- Adaptive Aspera (Fig 5) on FABRIC (this dev box, Node-FIU). No Slurm.
#
# Fabric's egress allows Aspera UDP 33001 to fasp.sra.ebi.ac.uk (gate-checked
# 2026-07-21), so E5 runs here directly. Installs real ascp if the benchmark stub
# is on PATH.
#
#   bash bench/e5/run_fabric.sh                 # all panels
#   PANELS="5a 5b" bash bench/e5/run_fabric.sh  # subset
#   REPS=1 bash bench/e5/run_fabric.sh 5a

set -uo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR" || exit 1
export PATH="$HOME/.local/bin:$PATH"

export E5_PYTHON="${E5_PYTHON:-python3}"
export E5_WORK="${E5_WORK:-/tmp/e5_payload_$USER}"
export E5_OUT="${E5_OUT:-$REPO_DIR/e5_results_fabric}"
export E5_MD5_JOBS="${E5_MD5_JOBS:-8}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
export E5_TIMEOUT="${E5_TIMEOUT:-1800}"
mkdir -p "$E5_WORK" "$E5_OUT"

PANELS="${PANELS:-5a 5b 5c}"
PANEL_ARG="${1:-all}"
REPS="${REPS:-}"

echo "=== adaptiSeq E5 on Fabric ($(hostname -s)) ==="

# real ascp? (the E8/E7 runs may have left the no-op stub on PATH)
if ! ascp --version 2>/dev/null | grep -qi "ascp version"; then
    echo "[setup] real ascp not on PATH; installing…"
    bash "$REPO_DIR/bench/setup_real_ascp.sh" || { echo "[ERROR] ascp install failed" >&2; exit 1; }
fi
echo "ascp: $(ascp --version 2>&1 | grep -i 'ascp version')"

# ─── Aspera UDP-33001 gate ─────────────────────────────────────────────────
echo; echo "=== Aspera gate (real handshake) ==="
KEY=$("$E5_PYTHON" -c 'from adaptiseq.engine.classic import find_ena_aspera_key as f; print(f())' 2>/dev/null)
[[ -z "$KEY" ]] && { echo "[ERROR] no ENA Aspera key (run setup_real_ascp.sh)"; exit 1; }
APATH=$(curl -sS --max-time 30 "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR22904350&result=read_run&fields=fastq_aspera&format=tsv" | tail -1 | awk '{print $2}' | tr ';' '\n' | head -1 | cut -d: -f2-)
mkdir -p "$E5_WORK/_gate"
if timeout 60 ascp -i "$KEY" -P 33001 -QT -l 100m --policy fair "era-fasp@fasp.sra.ebi.ac.uk:${APATH}" "$E5_WORK/_gate/" 2>&1 | grep -q "Completed:"; then
    echo "  OK — UDP 33001 open, RSA key authenticates."
    rm -rf "$E5_WORK/_gate"
else
    echo "[ERROR] Aspera handshake failed (UDP 33001 blocked or key rejected). E5 can't run." >&2
    exit 1
fi

echo; echo "=== running ==="
if [[ "$PANEL_ARG" == "all" ]]; then
    PANELS="$PANELS" bash "$REPO_DIR/bench/e5/run_e5.sh" all "$REPS"
else
    bash "$REPO_DIR/bench/e5/run_e5.sh" "$PANEL_ARG" "$REPS"
fi

echo; echo "=== aggregating ==="
"$E5_PYTHON" "$REPO_DIR/bench/e5/aggregate_e5.py" --outdir "$E5_OUT" 2>&1 | tee "$E5_OUT/summary.txt" || true
echo "=== done. Results: $E5_OUT ==="
