#!/usr/bin/env bash
# Sequential benchmark: adaptiSeq (adaptive/fixed) vs iseq on three lists.
# Sequential (no bandwidth contention); each output dir is removed after its
# size/time is recorded, to bound disk use. Appends to results.tsv (seeded by
# the caller with the header + the already-done small_adaptive row).
set -u
B=/home/ubuntu/benchruns
RES=$B/results.tsv
REPO=/home/ubuntu/adaptiSeq
SM=$REPO/bench/inputs/accessions_small_PRJNA916347.txt
MD=$REPO/bench/inputs/accessions_medium_PRJNA353374.txt
LG=$REPO/bench/inputs/accessions_large_PRJNA251383.txt
cd "$REPO"

record(){ # tag mode dt outdir
  local tag=$1; local mode=$2; local dt=$3; local out=$4
  local bytes; bytes=$(du -sb "$out" 2>/dev/null | cut -f1); bytes=${bytes:-0}
  local mbps; mbps=$(awk "BEGIN{printf \"%.0f\", ($dt>0)?$bytes*8/($dt*1e6):0}")
  printf '%s\t%s\t%ss\t%s\t%sMbps\n' "$tag" "$mode" "$dt" "$(numfmt --to=iec "$bytes")" "$mbps" >> "$RES"
}

run_aseq(){ # mode list tag
  local mode=$1; local list=$2; local tag=$3; local out=$B/$tag
  rm -rf "$out"; mkdir -p "$out"
  local t0; t0=$(date +%s)
  python3 -u bench/_run_one.py "$mode" "$list" "$out" > "$B/$tag.log" 2>&1
  record "$tag" "aseq-$mode" "$(( $(date +%s) - t0 ))" "$out"
  rm -rf "$out"
}
run_iseq(){ # list tag
  local list=$1; local tag=$2; local out=$B/$tag
  rm -rf "$out"; mkdir -p "$out"
  local t0; t0=$(date +%s)
  # stock iseq = wget, sequential (its default). NOTE: iseq's -p (axel) is
  # ~100 s/file on this host regardless of transport, so we use iseq's default
  # wget path, which is its fast/representative mode here.
  iseq -i "$list" -g -k -r https -o "$out" > "$B/$tag.log" 2>&1
  record "$tag" "iseq-wget-https" "$(( $(date +%s) - t0 ))" "$out"
  rm -rf "$out"
}

run_iseq          "$SM" small_iseq
run_aseq adaptive "$LG" large_adaptive
run_iseq          "$LG" large_iseq
run_aseq adaptive "$MD" medium_adaptive
run_iseq          "$MD" medium_iseq
printf 'ALL DONE\n' >> "$RES"
