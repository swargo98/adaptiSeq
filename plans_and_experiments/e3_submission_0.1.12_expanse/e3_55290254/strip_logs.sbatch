#!/bin/bash
#SBATCH --job-name=aseq_strip_logs
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=slurm_strip_logs_%j.out
#
# Shrink arm logs written before e3_lib.sh stripped progress bars (gate job
# 54902879: the 3r iseq-p8 log is 26 GB of axel redraws). For each log given:
# keep the raw file as <log>.raw.gz (not committed; *.raw.gz is git-ignored) and
# replace <log> with the output of strip_progress.pl.
#
#   sbatch bench/e3/strip_logs.sbatch e3_submission_expanse/e3_54902879/logs/<arm>.log ...
#
# Do not run on the log of an arm that is still writing it.

set -uo pipefail
cd "$SLURM_SUBMIT_DIR" || exit 1
for f in "$@"; do
  [[ -f "$f" ]] || { echo "missing: $f"; continue; }
  echo "$(date -Is) $f: $(stat -c %s "$f") bytes"
  gzip -1 -c "$f" > "$f.raw.gz" || { echo "gzip failed: $f"; continue; }
  perl bench/e3/strip_progress.pl < "$f" > "$f.clean" || { echo "strip failed: $f"; rm -f "$f.clean"; continue; }
  mv "$f.clean" "$f"
  echo "$(date -Is) $f: now $(stat -c %s "$f") bytes; raw kept as $f.raw.gz ($(stat -c %s "$f.raw.gz") bytes)"
  tail -1 "$f"
done
