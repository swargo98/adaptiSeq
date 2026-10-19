#!/bin/bash
# watch_rows.sh JOBID: return when the job prints its gate line, MIN_NEW (default 1)
# new result rows land in $ROOT/e3_JOBID/e3_results.tsv, or the job ends. Probes ENA's
# portal every 5 min meanwhile (appends to ena_portal_status_20261015.tsv).
# Usage: ROOT=e3_jsweep_expanse MIN_NEW=4 bash tools/watch_rows.sh 55064912
J=$1
PE=/home/rswargo/adaptiSeq/plans_and_experiments
R=$PE/${ROOT:-e3_submission_expanse}/e3_$J
P=$PE/ena_portal_status_20261015.tsv
rows() { [ -f $R/e3_results.tsv ] && wc -l < $R/e3_results.tsv || echo 0; }
gate() { grep -cE "GATE (PASS|FAIL)" $PE/slurm_e3_$J.out $R/slurm_e3_$J.out 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}'; }
n0=$(rows); g0=$(gate); i=0
while true; do
  if (( i % 5 == 0 )); then
    curl -s -o /dev/null -w "$(date +%FT%T)\t%{http_code}\t%{time_total}\t%{size_download}\n" --max-time 60 \
      "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR22904253&result=read_run&fields=run_accession,fastq_md5&format=tsv&download=true&limit=0" >> $P
  fi
  i=$((i+1))
  s=$(squeue -j $J -h -o '%T')
  if [[ $(rows) -ge $((n0 + ${MIN_NEW:-1})) || $(gate) -gt $g0 || -z "$s" ]]; then break; fi
  sleep 60
done
date; echo "job $J state=${s:-ended}"
squeue -u $USER -o '%i %T %M %R'
grep -hE "GATE (PASS|FAIL)" $PE/slurm_e3_$J.out 2>/dev/null
[ -f $R/e3_results.tsv ] && cut -f1,3,7-12,36 $R/e3_results.tsv | column -t
find $R -size +20M 2>/dev/null
echo; tail -3 $P
