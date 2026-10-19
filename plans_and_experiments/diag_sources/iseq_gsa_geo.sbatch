#!/bin/bash
#SBATCH --job-name=iseq_gsa_geo
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:40:00
#SBATCH --output=slurm_iseq_gsa_geo_%j.out
#
# Does iSeq 1.9.9 (the benchmark's comparison tool) still reach GSA and GEO, now
# that GSA's browse page and GEO's accession page block scripts? The paper's
# Table 1 lists both for iSeq. Same accessions as e2e_gsa_geo.sbatch.
set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME:-adaptiseq_e3_sub}" || exit 1
set -u
export PATH="${CONDA_PREFIX}/bin:$PATH"
OUT="$SLURM_SUBMIT_DIR/diag_sources/iseq_${SLURM_JOB_ID}"; WORK="/scratch/$USER/job_${SLURM_JOB_ID}/iseq"
mkdir -p "$OUT" "$WORK"; trap 'rm -rf "$WORK"' EXIT
exec > >(tee -a "$OUT/iseq.txt") 2>&1
echo "date: $(date -Is)  node: $(hostname -s)  $(iseq -v 2>&1 | head -1)"
for c in "gsa_crr:-i CRR120304" "geo_gsm:-i GSM7417667 -g" "geo_gse_meta:-i GSE233000 -m"; do
    name=${c%%:*}; args=${c#*:}; d="$WORK/$name"; mkdir -p "$d"; cd "$d"
    t0=$(date +%s); timeout 900 iseq $args -o . > "$OUT/$name.log" 2>&1; rc=$?
    echo "== iseq $args: rc=$rc $(( $(date +%s) - t0 )) s  files: $(ls | tr '\n' ' ')"
    sed 's/\x1b\[[0-9;]*m//g' "$OUT/$name.log" | grep -aiE "error|not valid|success|fail|belongs|no " | sort | uniq -c | head -6
done
echo "=== done $(date -Is) ==="
