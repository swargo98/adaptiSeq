#!/bin/bash
#SBATCH --job-name=docbuild
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=slurm_docbuild_%j.out
#SBATCH --error=slurm_docbuild_%j.out
# Rebuilds the figures, numbers and PDF of the methodology document from the
# benchmark result directories. Submit from this directory:
#   sbatch build.sbatch
set -uo pipefail
export PS1="${PS1:-}"
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate docenv || exit 1
cd "${SLURM_SUBMIT_DIR:-.}" || exit 1
python make_figures.py --root ../.. --portal data/ena_portal_status.tsv || exit 1
tectonic --keep-logs adaptiseq_methodology.tex || exit 1
ls -la adaptiseq_methodology.pdf
