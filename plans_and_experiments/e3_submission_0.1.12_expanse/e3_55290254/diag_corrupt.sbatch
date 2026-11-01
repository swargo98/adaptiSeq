#!/bin/bash
#SBATCH --job-name=aseq_diag_corrupt
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=06:00:00
#SBATCH --output=slurm_diag_corrupt_%j.out
#
# Were the md5 mismatches on SRR15852411 (gate 54902879, 3b adaptiseq-default)
# served by ENA or written by adaptiSeq? See diag_corrupt.py.
#
# Submit from plans_and_experiments/:  sbatch bench/e3/diag_corrupt.sbatch
#   ITERS=3 RUNS="SRR15852411 SRR15852406" sbatch --export=ALL bench/e3/diag_corrupt.sbatch

set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME:-adaptiseq_e3_sub}" || exit 1
set -u

REPO_DIR="$SLURM_SUBMIT_DIR"
OUT="$REPO_DIR/diag_corrupt_${SLURM_JOB_ID}"
WORK="/scratch/$USER/job_${SLURM_JOB_ID}/diag"
mkdir -p "$OUT" "$WORK"
trap 'rm -rf "$WORK"' EXIT
exec > >(tee -a "$OUT/diag.txt") 2>&1

echo "date: $(date -Is)  node: $(hostname -s)  public ip: $(curl -s --max-time 10 https://ifconfig.me || echo ?)"
echo "checkout: $(git -C "$REPO_DIR" rev-parse --short HEAD)"
specs=()
for r in ${RUNS:-SRR15852411}; do
    curl -s --max-time 60 "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=$r&result=read_run&fields=run_accession,fastq_ftp,fastq_bytes,fastq_md5" \
        > "$OUT/${r}.filereport.tsv"
    cat "$OUT/${r}.filereport.tsv"
    # manifest md5 (what the gate checked against) next to ENA's md5 now
    grep -P "^$r\t" "$REPO_DIR/datasets/D2_subset_PRJNA762469.manifest" || true
    IFS=$'\t' read -r _ ftp bytes md5s < <(tail -n +2 "$OUT/${r}.filereport.tsv")
    IFS=';' read -ra U <<< "$ftp"; IFS=';' read -ra M <<< "$md5s"; IFS=';' read -ra B <<< "$bytes"
    for k in "${!U[@]}"; do
        specs+=("$(basename "${U[$k]}")=${M[$k]}=${B[$k]}=https://${U[$k]}")
    done
done
python -u "$REPO_DIR/bench/e3/diag_corrupt.py" --out "$OUT" --work "$WORK" \
    --iters "${ITERS:-4}" "${specs[@]}"
echo "=== done $(date -Is) ==="
