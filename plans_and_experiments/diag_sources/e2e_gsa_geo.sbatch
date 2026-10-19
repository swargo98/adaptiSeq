#!/bin/bash
#SBATCH --job-name=aseq_e2e_gsa_geo
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:30:00
#SBATCH --output=slurm_e2e_gsa_geo_%j.out
#
# End-to-end downloads from the archives whose web pages now block scripts
# (GSA browse page: JS browser check; GEO acc.cgi: reCAPTCHA), with adaptiSeq
# from the checkout: GSA over HTTPS, GSA over FTP (-r ftp), a mixed GSA + ENA
# list in one batch, a GEO sample, a GEO series (metadata only), a DDBJ run.
# Every download is checked with md5sum against the archive's own md5.
set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME:-adaptiseq_e3_sub}" || exit 1
set -u
export PATH="${CONDA_PREFIX}/bin:$PATH"
REPO_DIR="$SLURM_SUBMIT_DIR"; export SRC_DIR="$(cd "$REPO_DIR/.." && pwd)"
OUT="$REPO_DIR/diag_sources/e2e_${SLURM_JOB_ID}"; WORK="/scratch/$USER/job_${SLURM_JOB_ID}/e2e"
mkdir -p "$OUT" "$WORK"; trap 'rm -rf "$WORK"' EXIT
exec > >(tee -a "$OUT/e2e.txt") 2>&1
aseq() { python -I -c "import sys; sys.path.insert(0, '$SRC_DIR'); from adaptiseq import cli; sys.exit(cli.main(sys.argv[1:]))" "$@"; }
echo "date: $(date -Is)  node: $(hostname -s)  checkout: $(git -C "$SRC_DIR" rev-parse --short HEAD)$(git -C "$SRC_DIR" diff --quiet -- adaptiseq || echo ' + uncommitted')"
case_() {   # name timeout_s args...
    local name=$1 to=$2; shift 2
    local d="$WORK/$name"; mkdir -p "$d"; cd "$d" || return
    local t0=$(date +%s)
    timeout "$to" bash -c "$(declare -f aseq); aseq $*" > "$OUT/$name.log" 2>&1; local rc=$?
    local t1=$(date +%s)
    echo "== $name: rc=$rc  $((t1 - t0)) s  files: $(ls | grep -vE 'metadata|\.log$|md5sum' | tr '\n' ' ')"
    grep -aE "md5 check successful|download successful|failed|Error|MD5 mismatch|no usable|belongs to" "$OUT/$name.log" | sed 's/\x1b\[[0-9;]*m//g' | sort | uniq -c | head -8
    cd "$WORK"
}
# GSA, smallest run of CRA002399 (1.78 GB), HTTPS (default)
case_ gsa_https 1200 -i CRR120304 -o .
# GSA over FTP from download.big.ac.cn
case_ gsa_ftp 1200 -i CRR120304 -r ftp -o .
# One list, two archives: the GSA run and a GEO sample's ENA run, one batch
printf 'CRR120304\nGSM7417667\n' > "$WORK/mixed.txt"
case_ mixed_gsa_geo 1500 -i "$WORK/mixed.txt" -g -o .
# GEO sample on its own, and a GEO series (metadata only: 29 samples)
case_ geo_gsm 900 -i GSM7417667 -g -o .
case_ geo_gse_meta 300 -i GSE233000 -m -o .
# DDBJ run (0.78 GB), served by ENA
case_ ddbj_drr 900 -i DRR421224 -g -o .
echo "=== done $(date -Is) ==="
