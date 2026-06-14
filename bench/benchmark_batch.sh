#!/bin/bash
# Part 4 batch-USP benchmark: adaptiFetch vs dedicated SRA fetchers (iseq,
# Kingfisher) on a many-files ENA workload. Each method downloads the SAME
# subset; files are REMOVED between runs. Measures wall-clock + throughput.
#
# Competitors run their own per-run resolution + download (sequential); adaptiSeq
# parallelises resolution (--meta-jobs) and downloads in an adaptive batch pool.
set -u
export PATH="/home/ubuntu/.local/bin:$PATH"

REPO=/home/ubuntu/adaptiSeq
ISEQ="$REPO/iSeq-main/bin/iseq"
LIST="$REPO/bench/subset_small.txt"
NRUN=$(grep -c . "$LIST")
WORK=/tmp/bench_p4
RESULTS="$REPO/bench/results_batch.tsv"
mkdir -p "$WORK"
echo -e "method\tseconds\tMB\tMB/s\tfiles\tformats\tstatus" > "$RESULTS"

# Count DATA files (any format a tool might fetch: fastq(.gz)/fq(.gz)/sra/bam),
# excluding metadata, logs, and transient/state files. Different tools download
# different formats/sizes, so bytes + MB/s — not time alone — make it fair.
_data_files() {
  find "$1" -type f 2>/dev/null \
    | grep -vE '\.(metadata\.(tsv|csv|xlsx)|log|part|part\.meta|tmp|st|aria2)$' \
    | grep -vE '/(success\.log|fail\.log|urls\.txt|\.has_failed\.flag)$' \
    | grep -vE '\.md5sum\.txt$'
}
bytes_of() { _data_files "$1" | tr '\n' '\0' | xargs -0 -r stat -c '%s' 2>/dev/null | awk '{s+=$1} END{print s+0}'; }
files_of() { _data_files "$1" | wc -l; }
formats_of() { _data_files "$1" | sed -E 's/.*\.([a-z0-9]+(\.[a-z0-9]+)?)$/\1/' | sort -u | paste -sd, - ; }

METHOD_TIMEOUT=${METHOD_TIMEOUT:-240}
run() {
  local name="$1"; shift
  local dir="$WORK/$(echo "$name" | tr ' /' '__')"
  rm -rf "$dir"; mkdir -p "$dir"
  echo "=== $name (timeout ${METHOD_TIMEOUT}s) ===" >&2
  local t0 t1 rc
  t0=$(date +%s.%N)
  ( cd "$dir" && timeout ${METHOD_TIMEOUT} bash -c "$*" ) > "$dir/.log" 2>&1
  rc=$?
  t1=$(date +%s.%N)
  [ $rc -eq 124 ] && echo "  (TIMED OUT after ${METHOD_TIMEOUT}s)" >&2
  local sec b f mbps
  sec=$(awk -v a=$t0 -v b=$t1 'BEGIN{printf "%.1f", b-a}')
  local b f mbps fmt
  b=$(bytes_of "$dir"); f=$(files_of "$dir"); fmt=$(formats_of "$dir")
  [ -z "$fmt" ] && fmt="-"
  # MB/s (downloaded bytes per second) — the fair cross-tool metric.
  mbps=$(awk -v b=$b -v s=$sec 'BEGIN{printf "%.2f", (s>0)?(b/1e6/s):0}')
  local status="ok"; [ $rc -eq 124 ] && status="TIMEOUT"; [ $rc -ne 0 ] && [ $rc -ne 124 ] && status="rc=$rc"
  echo -e "${name}\t${sec}\t$(awk -v b=$b 'BEGIN{printf "%.0f", b/1e6}')\t${mbps}\t${f}\t${fmt}\t${status}" | tee -a "$RESULTS" >&2
  # capture adaptive trajectory if present
  grep -h "trajectory" "$dir/.log" 2>/dev/null | tail -1 >&2 || true
  rm -rf "$dir"
}

echo "Workload: $NRUN runs from PRJNA916347 (subset), files removed between methods." >&2

# 1. stock iseq (sequential per-run wget, ENA, gzip)
run "iseq" "\"$ISEQ\" -i \"$LIST\" -g -o ."
# 2. iseq -p 8 (sequential per-run, axel 8 connections)
run "iseq -p 8" "\"$ISEQ\" -i \"$LIST\" -g -p 8 -o ."
# 3. Kingfisher (ena-ftp method; per-run resolution + aria2c)
run "kingfisher ena-ftp" "kingfisher get --run-identifiers-list \"$LIST\" -m ena-ftp --output-directory . --check-md5sums"
# 4. adaptiseq fixed concurrency (segmented batch, no controller)
run "adaptiseq --no-adaptive" "adaptiseq -i \"$LIST\" -g --no-adaptive -j 20 -Q -o ."
# 5. adaptiseq adaptive (segmented batch + gradient controller)
run "adaptiseq --adaptive" "adaptiseq -i \"$LIST\" -g --adaptive -j 20 -Q -o ."

echo "" >&2
echo "=== RESULTS ===" >&2
column -t -s $'\t' "$RESULTS" >&2
