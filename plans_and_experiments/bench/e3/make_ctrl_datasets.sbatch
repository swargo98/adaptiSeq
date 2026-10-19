#!/bin/bash
#SBATCH --job-name=aseq_ctrl_data
#SBATCH --account=umr115
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=slurm_ctrl_data_%j.out
#
# Lists and md5 manifests for the controller tournament's non-ENA panels
# (run_e3.sh 4s / 4g / 4x), written to datasets/:
#   S1_sra_PRJNA762469  panel 3b's 8 runs as NCBI .sra files (adaptiSeq -d sra
#                       keeps the .sra). NCBI publishes no md5 for its AWS copy,
#                       so each file is fetched once here with curl and hashed;
#                       the arms are then checked against those reference copies.
#   G1_gsa_CRA002399    GSA project CRA002399 (rice RNA-seq, 6 runs, 12 GB);
#                       md5 and sizes from GSA's md5sum.txt and run-info table.
#                       GSA_RUNS (default 3) limits how many runs go in.
#   X1_routing          a DDBJ run (DRR421224) and a GEO sample (GSM7417667):
#                       both resolve to ENA files, so this checks routing only.
# Submit from plans_and_experiments/:  sbatch bench/e3/make_ctrl_datasets.sbatch
set -uo pipefail
module purge
module load slurm cpu/0.17.3b anaconda3/2021.05
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME:-adaptiseq_e3_sub}" || exit 1
set -u
export PATH="${CONDA_PREFIX}/bin:$PATH"
REPO_DIR="$SLURM_SUBMIT_DIR"
SRC_DIR="$(cd "$REPO_DIR/.." && pwd)"
DS="$REPO_DIR/datasets"
OUT="$REPO_DIR/ctrl_datasets_${SLURM_JOB_ID}"
WORK="/scratch/$USER/job_${SLURM_JOB_ID}/data"
mkdir -p "$OUT" "$WORK"
trap 'rm -rf "$WORK"' EXIT
exec > >(tee -a "$OUT/make.txt") 2>&1
# adaptiSeq from the checkout (metadata only), not whatever wheel the env has
aseq() { python -I -c "import sys; sys.path.insert(0, '$SRC_DIR'); from adaptiseq import cli; sys.exit(cli.main(sys.argv[1:]))" "$@"; }
echo "date: $(date -Is)  node: $(hostname -s)  checkout: $(git -C "$SRC_DIR" rev-parse --short HEAD)"

echo "=== S1: NCBI .sra reference copies ==="
: > "$WORK/S1.manifest"
for r in $(cat "$DS/D2_subset_PRJNA762469.txt"); do
    u=$(srapath "$r" 2>/dev/null | head -1)
    [[ -n "$u" ]] || { echo "[ERROR] srapath gave no URL for $r"; exit 1; }
    curl -sS --retry 5 -o "$WORK/$r" "$u" || { echo "[ERROR] download failed: $u"; exit 1; }
    vdb-validate "$WORK/$r" > "$WORK/$r.vdb" 2>&1 || { echo "[ERROR] vdb-validate failed for $r"; cat "$WORK/$r.vdb"; exit 1; }
    sz=$(stat -c %s "$WORK/$r"); m=$(md5sum "$WORK/$r" | cut -d' ' -f1)
    echo -e "$r\t$r\t$sz\t$m" >> "$WORK/S1.manifest"
    echo "  $r  $sz  $m  $u"
    rm -f "$WORK/$r"
done
cp "$DS/D2_subset_PRJNA762469.txt" "$DS/S1_sra_PRJNA762469.txt"
{ printf 'run_accession\tfile_name\tbytes\tmd5\n'; cat "$WORK/S1.manifest"; } > "$DS/S1_sra_PRJNA762469.manifest"

echo "=== G1: GSA CRA002399 ==="
( cd "$WORK" && aseq -i CRA002399 -m -Q -o . >/dev/null 2>&1 )
curl -sS --retry 5 -o "$WORK/md5sum.txt" https://download.cncb.ac.cn/gsa3/CRA002399/md5sum.txt
python - "$WORK/CRA002399.metadata.csv" "$WORK/md5sum.txt" "${GSA_RUNS:-3}" "$DS/G1_gsa_CRA002399" <<'PY'
import csv, sys
meta, md5f, n, base = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
md5 = {}
for line in open(md5f):
    p = line.split()
    if len(p) >= 2:
        md5[p[-1].rsplit("/", 1)[-1]] = p[0].lower()
rows = sorted(csv.DictReader(open(meta)), key=lambda r: r["Run"])[:n]
with open(base + ".txt", "w") as fh:
    for r in rows:
        fh.write(r["Run"] + "\n")
with open(base + ".manifest", "w") as fh:
    fh.write("run_accession\tfile_name\tbytes\tmd5\n")
    for r in rows:
        for name, size in zip(r["FileName"].split("|"), r["FileSize"].split("|")):
            fh.write(f"{r['Run']}\t{name}\t{size}\t{md5[name]}\n")
print(f"  {len(rows)} runs, {sum(int(s) for r in rows for s in r['FileSize'].split('|'))/1e9:.1f} GB")
PY

echo "=== X1: DDBJ + GEO routing ==="
printf 'DRR421224\nGSM7417667\n' > "$DS/X1_routing.txt"
( cd "$WORK" && aseq -i GSM7417667 -m -Q -o . >/dev/null 2>&1 )
python - "$DS/X1_routing.manifest" "$WORK"/*.metadata.tsv <<'PY'
import csv, sys, urllib.request
out, tsvs = sys.argv[1], sys.argv[2:]
rows = []
url = ("https://www.ebi.ac.uk/ena/portal/api/filereport?accession=DRR421224"
       "&result=read_run&fields=run_accession,fastq_ftp,fastq_bytes,fastq_md5&format=tsv")
text = urllib.request.urlopen(url, timeout=60).read().decode()
tables = [text] + [open(t).read() for t in tsvs]
for t in tables:
    for r in csv.DictReader(t.splitlines(), delimiter="\t"):
        for f, b, m in zip(r["fastq_ftp"].split(";"), r["fastq_bytes"].split(";"),
                           r["fastq_md5"].split(";")):
            if f:
                rows.append((r["run_accession"], f.rsplit("/", 1)[-1], b, m))
rows = sorted(set(rows))
with open(out, "w") as fh:
    fh.write("run_accession\tfile_name\tbytes\tmd5\n")
    for r in rows:
        fh.write("\t".join(r) + "\n")
print(f"  {len(rows)} files: " + ", ".join(r[1] for r in rows))
PY
cp "$DS"/S1_sra_PRJNA762469.* "$DS"/G1_gsa_CRA002399.* "$DS"/X1_routing.* "$OUT/"
echo "=== done $(date -Is) ==="
