#!/bin/bash
#SBATCH --job-name=aseq_diag_batch
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=slurm_diag_batch_%j.out
#
# Panel 3b's download phase replayed with adaptiSeq (segmented HTTPS and FTP)
# and plain curl (HTTPS and FTP), every file md5-checked. See diag_batch.py.
#
# Submit from plans_and_experiments/:  sbatch diag_batch/diag_batch.sbatch
#   ROUNDS=1 METHODS=aseq-https,curl-ftp sbatch --export=ALL diag_batch/diag_batch.sbatch
#   LIST=datasets/SMOKE_D1.txt ROUNDS=1 sbatch --export=ALL --time=00:30:00 diag_batch/diag_batch.sbatch  # smoke

set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME:-adaptiseq_e3_sub}" || exit 1
set -u

REPO_DIR="$SLURM_SUBMIT_DIR"
OUT="$REPO_DIR/diag_batch/out_${SLURM_JOB_ID}"
WORK="/scratch/$USER/job_${SLURM_JOB_ID}/diag"
mkdir -p "$OUT" "$WORK"
trap 'rm -rf "$WORK"' EXIT
exec > >(tee -a "$OUT/diag.txt") 2>&1

echo "date: $(date -Is)  node: $(hostname -s)  public ip: $(curl -s --max-time 10 https://api.ipify.org || echo ?)"
echo "checkout: $(git -C "$REPO_DIR" rev-parse --short HEAD)  (adaptiSeq imported from the checkout, not the wheel)"
echo "scratch free: $(df -h "$WORK" | awk 'NR==2{print $4}')"
specs=()
LIST="${LIST:-datasets/D2_subset_PRJNA762469.txt}"
MANIFEST="${LIST%.txt}.manifest"
for r in $(cat "$REPO_DIR/$LIST"); do
    curl -s --max-time 60 "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=$r&result=read_run&fields=run_accession,fastq_ftp,fastq_bytes,fastq_md5" \
        > "$OUT/${r}.filereport.tsv"
    IFS=$'\t' read -r _ ftp bytes md5s < <(tail -n +2 "$OUT/${r}.filereport.tsv")
    IFS=';' read -ra U <<< "$ftp"; IFS=';' read -ra M <<< "$md5s"; IFS=';' read -ra B <<< "$bytes"
    for k in "${!U[@]}"; do
        n="$(basename "${U[$k]}")"
        # the manifest the benchmark checks against must agree with ENA today
        grep -qP "\t$n\t${B[$k]}\t${M[$k]}$" "$REPO_DIR/$MANIFEST" \
            || echo "[WARN] $n: ENA now reports ${B[$k]} ${M[$k]}, not the manifest's"
        specs+=("$n=${M[$k]}=${B[$k]}=${U[$k]}")
    done
done
echo "files: ${#specs[@]}"
python -u "$REPO_DIR/diag_batch/diag_batch.py" --out "$OUT" --work "$WORK" \
    --rounds "${ROUNDS:-2}" --methods "${METHODS:-aseq-https,curl-ftp,aseq-ftp,curl-https}" "${specs[@]}"
echo "=== done $(date -Is) ==="
