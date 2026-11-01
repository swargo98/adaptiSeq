#!/bin/bash
#SBATCH --job-name=aseq_diag_md5
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --output=slurm_diag_md5_%j.out
#SBATCH --error=slurm_diag_md5_%j.err
#
# Why did iSeq 1.9.9 report "MD5 mismatch" three times for SRR22904281 (and
# fail SRR22904283, SRR22904284) in gate job 54902879, when Kingfisher and
# adaptiSeq verified the same files against ENA's md5 in the same job?
#
# For each run: record ENA's file report now; download the FASTQ over FTP with
# iSeq's own command (wget -c ftp://...) and over HTTPS with curl; md5 both;
# then run iSeq itself on each run and keep its metadata.tsv, so we can see which
# md5 it compared against.
#
# Submit from plans_and_experiments/:  sbatch bench/e3/diag_iseq_md5.sbatch

set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
ENV_NAME="${ENV_NAME:-adaptiseq_e3_sub}"
set +u   # conda's activate scripts read unset variables (PS1)
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_NAME" || { echo "conda activate $ENV_NAME failed"; exit 1; }
set -u
command -v iseq >/dev/null || { echo "iseq not on PATH"; exit 1; }

RUNS="${RUNS:-SRR22904281 SRR22904283 SRR22904284}"
OUT="$SLURM_SUBMIT_DIR/diag_iseq_md5_${SLURM_JOB_ID}"
WORK="/scratch/$USER/job_${SLURM_JOB_ID}/diag"
mkdir -p "$OUT" "$WORK"
exec > >(tee -a "$OUT/diag.txt") 2>&1

echo "date: $(date -Is)  node: $(hostname)  public ip: $(curl -s --max-time 10 https://ifconfig.me || echo ?)"
echo "iseq: $(iseq -v)  wget: $(wget --version | head -1)"

for r in $RUNS; do
  echo; echo "=== $r ==="
  d="$WORK/$r"; mkdir -p "$d"; cd "$d" || exit 1
  curl -s --max-time 60 "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=$r&result=read_run&fields=run_accession,library_layout,fastq_ftp,fastq_bytes,fastq_md5" \
    | tee "$OUT/${r}.filereport.tsv"
  links=$(tail -n +2 "$OUT/${r}.filereport.tsv" | cut -f3 | tr ';' '\n' | grep fastq.gz)
  # the biggest file is the one iSeq reported as mismatched
  main=$(echo "$links" | grep -v '_[12]\.fastq\.gz$' | head -1); [[ -z "$main" ]] && main=$(echo "$links" | head -1)
  f=$(basename "$main")
  ( mkdir -p ftp && cd ftp && t0=$(date +%s); wget -c "ftp://$main" -O "$f" --quiet; \
    echo "ftp   $f  exit=$?  $(stat -c %s "$f") bytes  $(( $(date +%s) - t0 )) s  md5=$(md5sum "$f" | cut -d' ' -f1)" ) &
  ( mkdir -p https && cd https && t0=$(date +%s); curl -s -o "$f" "https://$main"; \
    echo "https $f  exit=$?  $(stat -c %s "$f") bytes  $(( $(date +%s) - t0 )) s  md5=$(md5sum "$f" | cut -d' ' -f1)" ) &
  wait
  echo "ena   $f  $(tail -n +2 "$OUT/${r}.filereport.tsv" | cut -f4,5)"
  # iSeq itself, keeping its metadata
  mkdir -p iseq && cd iseq && t0=$(date +%s)
  iseq -i "$r" -g > "$OUT/${r}.iseq.log" 2>&1; rc=$?
  echo "iseq  exit=$rc  $(( $(date +%s) - t0 )) s  success.log: $(cat success.log 2>/dev/null | wc -l)  fail.log: $(cat fail.log 2>/dev/null | wc -l)"
  grep -E "MD5 mismatch|successful|failed" "$OUT/${r}.iseq.log" | sed 's/\x1b\[[0-9;]*m//g'
  cp ./*.metadata.tsv "$OUT/" 2>/dev/null
  for g in ./*.fastq.gz; do [[ -f $g ]] && echo "iseq file $g $(stat -c %s "$g") md5=$(md5sum "$g" | cut -d' ' -f1)"; done
done
echo; echo "=== done $(date -Is). Output: $OUT ==="
rm -rf "$WORK"
