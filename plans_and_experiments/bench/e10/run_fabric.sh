#!/usr/bin/env bash
# E10 on Fabric (Node-FIU) -- run directly, no Slurm. Smoke first, then full.
# Resolution-only (no sequencing bytes); 10c is fully local.
#
#   bash bench/e10/run_fabric.sh          # smoke then all panels
#   bash bench/e10/run_fabric.sh full     # skip smoke
set -uo pipefail
E10_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E10_DIR/../.." && pwd)"
cd "$REPO_DIR"

export E10_OUT="${E10_OUT:-$REPO_DIR/e10_results_fabric}"
export E10_PYTHON="${E10_PYTHON:-python3}"

MODE="${1:-smoke}"

echo "=== egress check (ENA + GSA) ===" >&2
curl -sI --max-time 15 https://www.ebi.ac.uk/ena/portal/api/ >/dev/null \
    && echo "  ENA reachable" >&2 || echo "  WARN: ENA unreachable (10a/10b will fail; 10c still runs)" >&2

if [[ "$MODE" == "smoke" ]]; then
    echo "=== E10 SMOKE ===" >&2
    bash "$E10_DIR/run_e10.sh" smoke || true
fi

echo "=== E10 FULL (10a, 10b, 10c) ===" >&2
PANELS="10a 10b 10c" bash "$E10_DIR/run_e10.sh" all

echo "=== aggregate ===" >&2
"$E10_PYTHON" "$E10_DIR/aggregate_e10.py" --out "$E10_OUT" || true
echo "=== done: $E10_OUT ===" >&2
