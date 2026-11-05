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
# One rep per invocation on Fabric: E3_REP_FIRST=$r REPS=1 E3_OUT=<dir> bash run_submission.sh full
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

ENV_NAME="${ENV_NAME:-adaptiseq_e3}"
if command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -qE "^${ENV_NAME}\s"; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "$ENV_NAME"
fi

export E3_PYTHON="${E3_PYTHON:-python3}"
export PANELS="${PANELS:-3r 3b}"
export DATASETS="${DATASETS:-$REPO_DIR/datasets}"
export E3_WORK="${E3_WORK:-/tmp/e3_payload_$USER}"
export E3_OUT="${E3_OUT:-$REPO_DIR/e3_submission_$(hostname -s)_${MODE}_$(date +%Y%m%d_%H%M%S)}"
export E3_MD5_JOBS="${E3_MD5_JOBS:-8}"
mkdir -p "$E3_WORK" "$E3_OUT"

echo "=== adaptiSeq submission benchmark: $MODE on $(hostname -s) ==="
echo "panels  : $PANELS   reps=$REPS from rep ${E3_REP_FIRST:-1}   arm set=${ARM_SET:-submission}"
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
{
    echo "date: $(date -Is)"; echo "node: $(hostname -s)"; echo "kernel: $(uname -r)"
    lscpu 2>/dev/null | grep -E '^(Model name|Socket\(s\)|Core\(s\) per socket|Thread\(s\) per core|CPU\(s\)):'
    echo "memory: $(free -g | awk '/^Mem:/{print $2}') GB"
    echo "payload disk: $(df -h "$E3_WORK" | awk 'NR==2{print $2" total, "$4" free, "$1}')"
    echo "os: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-?}")"
    echo "routes: $(ip -4 route show default 2>/dev/null | head -1)"
} > "$E3_OUT/machine.txt" 2>&1

# Baseline link capacity, as in e3_expanse.sbatch: ENA at 1, 8 and 20 connections
# (20 s each, 60 MB ranges of one 1.3 GB file), to explain the single-stream arms.
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
} 2>&1 | tee "$E3_OUT/link_probe.txt"

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
    --panels $PANELS --reps "$REPS" --rep-first "${E3_REP_FIRST:-1}" 2>&1 | tee "$E3_OUT/check_run.txt" || status=1

echo "=== done (status=$status). Results: $E3_OUT ==="
exit "$status"
