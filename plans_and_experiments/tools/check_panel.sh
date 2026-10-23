#!/bin/bash
# check_panel.sh RESULTDIR PANEL: per-arm log/conc checks for one panel (the per-row routine).
D=$1; P=$2
awk -F'\t' -v p=$P 'NR==1{for(i=1;i<=NF;i++)h[$i]=i; next} $1==p{printf "%s rep%s %s %.0f s %s/%s unverified=%s\n", $1, $(h["rep"]), $(h["arm"]), $(h["wall_s"]), $(h["runs_complete"]), $(h["runs_expected"]), $(h["runs_present_unverified"])}' $D/e3_results.tsv
for f in $D/logs/${P}_*_rep*.log; do
  b=$(basename $f .log); a=${b#*adaptiseq-}
  L=$(sed 's/\x1b\[[0-9;]*m//g' $f)
  c=$D/logs/conc_$b.tsv
  cn=$(awk -F'\t' 'NR>1{n++;s+=$4;if($4>m)m=$4}END{if(n)printf "%.1f/%d",s/n,m}' $c 2>/dev/null)
  sum=$(grep -o 'adaptive worker summary: .*' <<<"$L" | sed -E 's/; recent:.*//; s/adaptive worker summary: //')
  echo "$a: conns=$cn mm=$(grep -c 'MD5 mismatch' <<<"$L") probe=$(grep -c 'probe attempt' <<<"$L") single=$(grep -c 'Single-conn' <<<"$L") fail=$(grep -cE 'failed after|attempt 3/3 failed' <<<"$L") cut=$(grep -c ContentLengthError <<<"$L") refused=$(grep -c 'attempt .* refused' <<<"$L") ceiling=$(grep -c 'connection ceiling' <<<"$L") sra=$(grep -c 'no usable ENA' <<<"$L") | $sum"
done
