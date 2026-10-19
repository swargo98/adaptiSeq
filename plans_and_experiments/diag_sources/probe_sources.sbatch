#!/bin/bash
#SBATCH --job-name=aseq_probe_src
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:40:00
#SBATCH --output=slurm_probe_src_%j.out
#
# How fast does each archive the paper names deliver to an Expanse compute node,
# at 1 and 8 connections (20 s each)? Sizes the controller tournament's panels.
# ENA is measured by every benchmark job already; this covers NCBI's AWS copy of
# .sra files (what -d sra and SRA-only runs fetch) and GSA (download.cncb.ac.cn).
set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME:-adaptiseq_e3_sub}" || exit 1
set -u
export PATH="${CONDA_PREFIX}/bin:$PATH"
OUT="$SLURM_SUBMIT_DIR/diag_sources/out_${SLURM_JOB_ID}"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/probe.txt") 2>&1
echo "date: $(date -Is)  node: $(hostname -s)"
probe() {   # url size label
    local url=$1 size=$2 label=$3
    for P in 1 8; do
        tmp=$(mktemp)
        for i in $(seq 0 $((P - 1))); do
            s=$(( (size / 8) * i )); e=$(( s + 99999999 ))
            curl -so /dev/null -r "$s-$e" -w '%{speed_download}\n' --max-time 20 "$url" >> "$tmp" &
        done
        wait
        awk -v p=$P -v l="$label" '{s+=$1; n++} END{printf "  %-22s P=%d  total %.1f MB/s (%.2f per conn, %d reported)\n", l, p, s/1e6, (n?s/1e6/n:0), n}' "$tmp"
        rm -f "$tmp"
    done
}
echo "=== NCBI .sra locations (srapath) for panel 3b's runs ==="
for r in $(cat "$SLURM_SUBMIT_DIR/datasets/D2_subset_PRJNA762469.txt"); do
    u=$(srapath "$r" 2>/dev/null | head -1)
    sz=$(curl -sI --max-time 20 "$u" | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}')
    echo "$r  $sz  $u"
    echo -e "$r\t$sz\t$u" >> "$OUT/sra_urls.tsv"
done
u=$(head -1 "$OUT/sra_urls.tsv" | cut -f3); sz=$(head -1 "$OUT/sra_urls.tsv" | cut -f2)
[ -n "$u" ] && probe "$u" "${sz:-1000000000}" "NCBI ($(echo "$u" | cut -d/ -f3))"
echo "=== GSA ==="
g=https://download.cncb.ac.cn/gsa3/CRA002399/CRR120307/CRR120307.fastq.gz
probe "$g" 2131874963 "GSA (download.cncb.ac.cn)"
echo "=== ENA (reference) ==="
probe https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR158/000/SRR15852400/SRR15852400_1.fastq.gz 1324320996 "ENA (ftp.sra.ebi.ac.uk)"
echo "=== done $(date -Is) ==="
