#!/bin/bash
#SBATCH --job-name=docenv
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:30:00
#SBATCH --output=slurm_docenv_%j.out
#SBATCH --error=slurm_docenv_%j.out
# Builds the env that renders the methodology document's figures and PDF
# (tectonic fetches its TeX packages on first use, so warm its cache here).
set -uo pipefail
export PS1="${PS1:-}"
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
source "$(conda info --base)/etc/profile.d/conda.sh"
conda create -y -n docenv -c conda-forge --override-channels python=3.11 tectonic matplotlib pandas numpy scipy || exit 1
conda activate docenv
tectonic --version
cd "$(mktemp -d)"
cat > t.tex <<'TEX'
\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}\usepackage{booktabs,graphicx,amsmath,amssymb,hyperref,xcolor,caption,subcaption,siunitx,algorithm,algpseudocode,microtype,enumitem,multirow,longtable,tabularx,float}
\usepackage{tikz}
\begin{document}warm \(x^2\) \SI{3}{MB/s}\end{document}
TEX
tectonic t.tex && ls -la t.pdf
