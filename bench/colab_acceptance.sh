#!/usr/bin/env bash
# =============================================================================
# adaptiSeq — Colab acceptance test
# -----------------------------------------------------------------------------
# Exercises every feature documented in README.md + docs/ against the LIVE
# databases, using small accessions so it finishes on a Colab box. It checks
# both the CLI and the Python API, asserts on the artifacts each command should
# produce, and prints a PASS/FAIL summary at the end.
#
# Usage:
#   TIER=quick bash bench/colab_acceptance.sh     # default; small downloads only
#   TIER=full  bash bench/colab_acceptance.sh     # + merge (~1 GB) + aspera (~1 GB)
#   ASPERA=1   bash bench/colab_acceptance.sh      # force the aspera tests on
#
# Env knobs:
#   TIER   quick|full   (default quick)
#   ASPERA 0|1          run the aspera tests (default: on only in TIER=full)
#   WORK   <dir>        scratch dir (default: ./adaptiseq_accept)
#   REPO   <dir>        repo root, for the bench/inputs/*.txt lists
# =============================================================================
set -u

TIER="${TIER:-quick}"
WORK="${WORK:-$(pwd)/adaptiseq_accept}"
REPO="${REPO:-$(pwd)}"
if [[ "$TIER" == "full" ]]; then ASPERA="${ASPERA:-1}"; else ASPERA="${ASPERA:-0}"; fi

MEDIUM_LIST="$REPO/bench/inputs/accessions_medium_PRJNA353374.txt"
MIXED_LIST="$REPO/bench/inputs/colab_batch_mixed.txt"
ASPERA_LIST="$REPO/bench/inputs/colab_aspera_ena.txt"

mkdir -p "$WORK"
PASS=0; FAIL=0; SKIP=0
declare -a RESULTS

c_green=$'\e[32m'; c_red=$'\e[31m'; c_yel=$'\e[33m'; c_dim=$'\e[2m'; c_off=$'\e[0m'

hr(){ printf '%s\n' "----------------------------------------------------------------------"; }

# ok <name> <condition-cmd...>   -> run condition, record PASS/FAIL
# We separate "run the tool" from "assert the artifacts": a test wraps the tool
# invocation itself in run_cli/expect_fail, then calls pass/fail directly.
record_pass(){ PASS=$((PASS+1)); RESULTS+=("${c_green}PASS${c_off}  $1"); printf '%sPASS%s  %s\n' "$c_green" "$c_off" "$1"; }
record_fail(){ FAIL=$((FAIL+1)); RESULTS+=("${c_red}FAIL${c_off}  $1"); printf '%sFAIL%s  %s\n' "$c_red" "$c_off" "$1"; }
record_skip(){ SKIP=$((SKIP+1)); RESULTS+=("${c_yel}SKIP${c_off}  $1"); printf '%sSKIP%s  %s\n' "$c_yel" "$c_off" "$1"; }

# assert: name + boolean expression already evaluated by caller via $?
assert(){ # assert "<name>" <rc-of-test>
  local name="$1" rc="$2"
  if [[ "$rc" -eq 0 ]]; then record_pass "$name"; else record_fail "$name"; fi
}

have(){ command -v "$1" >/dev/null 2>&1; }

banner(){ hr; printf '%s>>> %s%s\n' "$c_yel" "$1" "$c_off"; hr; }

# ---- preflight: what tools are present (some tests skip without them) --------
banner "Environment"
adaptiseq --version || { echo "adaptiseq not importable/installed — aborting"; exit 2; }
for t in wget md5sum srapath fasterq-dump vdb-validate pigz ascp; do
  if have "$t"; then printf '  %-14s %sfound%s\n' "$t" "$c_green" "$c_off"
  else printf '  %-14s %smissing%s\n' "$t" "$c_yel" "$c_off"; fi
done
echo "TIER=$TIER  ASPERA=$ASPERA  WORK=$WORK"

# =============================================================================
# 1. CLI smoke: --version / --help
# =============================================================================
banner "1. CLI smoke (--version, --help)"
adaptiseq --version | grep -q "adaptiSeq"; assert "1.1 --version prints banner" $?
adaptiseq --help    | grep -q "Usage"; assert "1.2 --help prints usage" $?

# =============================================================================
# 2. Metadata only (-m) from every source  (cheap — no sequence data)
# =============================================================================
banner "2. Metadata-only (-m) across all 5 databases"
md(){ # md <name> <accession> <expected-glob> [extra adaptiseq args]
  local name="$1" acc="$2" glob="$3"; shift 3
  local d="$WORK/meta_$acc"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i "$acc" -m -Q -o "$d" "$@" >"$d/log.txt" 2>&1
  compgen -G "$d/$glob" >/dev/null; assert "$name" $?
}
md "2.1 SRA  metadata (.tsv)"  SRR1553469 "SRR1553469*.metadata.tsv"
md "2.2 ENA  metadata (.tsv)"  ERR1726497 "ERR1726497*.metadata.tsv"
md "2.3 DDBJ metadata (.tsv)"  DRR291041  "DRR291041*.metadata.tsv"
md "2.4 GEO  metadata (->SRA)" GSM7417667 "GSM7417667*.metadata.tsv"
# GSA writes CSV + project XLSX. The China endpoint can be flaky/slow from Colab.
d="$WORK/meta_CRR311377"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i CRR311377 -m -Q -o "$d" >"$d/log.txt" 2>&1
if compgen -G "$d/*.metadata.csv" >/dev/null; then record_pass "2.5 GSA metadata (.csv)"; else record_skip "2.5 GSA metadata (.csv) — GSA endpoint unreachable?"; fi
if compgen -G "$d/CRA*.metadata.xlsx" >/dev/null; then record_pass "2.6 GSA project XLSX"; else record_skip "2.6 GSA project XLSX — GSA endpoint unreachable?"; fi

# Project-level resolution (the medium list's parent project) — metadata only,
# so the full 12-run project is exercised without downloading ~54 GB.
d="$WORK/meta_project"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i PRJNA353374 -m -Q -o "$d" >"$d/log.txt" 2>&1
runs=$(grep -c "SRR50171" "$d"/PRJNA353374*.metadata.tsv 2>/dev/null || echo 0)
[[ "$runs" -ge 12 ]]; assert "2.7 Project PRJNA353374 resolves >=12 runs ($runs found)" $?

# =============================================================================
# 3. Raw SRA download (default: no -g/-q)  — non-batch, single accession
# =============================================================================
banner "3. Raw .sra download (default engine, single accession)"
d="$WORK/raw_sra"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR1553469 -o "$d" -Q >"$d/log.txt" 2>&1
{ compgen -G "$d/**/*.sra" >/dev/null || find "$d" -name '*.sra' | grep -q .; }
assert "3.1 raw .sra file present" $?
grep -q "SRR1553469" "$d/success.log" 2>/dev/null; assert "3.2 success.log records the run" $?

# =============================================================================
# 4. Compressed FASTQ download (-g)  — non-batch
# =============================================================================
banner "4. Direct gzip FASTQ (-g)"
d="$WORK/gzip"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR1553469 -g -o "$d" -Q >"$d/log.txt" 2>&1
find "$d" -name '*_1.fastq.gz' | grep -q . && find "$d" -name '*_2.fastq.gz' | grep -q .
assert "4.1 paired *_1/_2.fastq.gz present" $?
grep -q "SRR1553469" "$d/success.log" 2>/dev/null; assert "4.2 success.log records the run" $?

# =============================================================================
# 5. SRA -> FASTQ conversion (-q) and combined (-q -g)
# =============================================================================
banner "5. SRA->FASTQ conversion (-q, -q -g)"
if have fasterq-dump; then
  d="$WORK/fastq"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i SRR1553469 -q -t 4 -o "$d" -Q >"$d/log.txt" 2>&1
  find "$d" -name '*.fastq' ! -name '*.fastq.gz' | grep -q .
  assert "5.1 uncompressed *.fastq produced (-q)" $?

  d="$WORK/fastq_gz"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i SRR1553469 -q -g -t 4 -o "$d" -Q >"$d/log.txt" 2>&1
  find "$d" -name '*.fastq.gz' | grep -q .
  assert "5.2 converted + gzipped *.fastq.gz (-q -g)" $?
else
  record_skip "5.1 -q conversion — fasterq-dump (sra-tools) missing"
  record_skip "5.2 -q -g conversion — fasterq-dump (sra-tools) missing"
fi

# =============================================================================
# 6. Sources / transport selection  (-d, -r)
# =============================================================================
banner "6. Force database / transport (-d, -r https, -r ftp)"
d="$WORK/https"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR1553469 -g -r https -o "$d" -Q >"$d/log.txt" 2>&1
find "$d" -name '*.fastq.gz' | grep -q .; assert "6.1 ENA over forced HTTPS (-r https)" $?

d="$WORK/ftp"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g -r ftp -o "$d" -Q >"$d/log.txt" 2>&1
find "$d" -name '*.fastq.gz' | grep -q .; assert "6.2 ENA over forced FTP (-r ftp)" $?

d="$WORK/force_sra"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR1553469 -d sra -o "$d" -Q >"$d/log.txt" 2>&1
find "$d" -name '*.sra' | grep -q .; assert "6.3 forced SRA database (-d sra)" $?

# =============================================================================
# 7. Batch + adaptive (-j, --adaptive / --no-adaptive, --meta-jobs)
# =============================================================================
banner "7. Batch download (mixed SRA/ENA/DDBJ list)"
d="$WORK/batch_adaptive"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i "$MIXED_LIST" -g -o "$d" -Q >"$d/log.txt" 2>&1
n=$(grep -c . "$d/success.log" 2>/dev/null || echo 0)
[[ "$n" -ge 3 ]]; assert "7.1 adaptive batch: 3 runs in success.log ($n)" $?

d="$WORK/batch_fixed"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i "$MIXED_LIST" -g -j 2 --no-adaptive -o "$d" -Q >"$d/log.txt" 2>&1
n=$(grep -c . "$d/success.log" 2>/dev/null || echo 0)
[[ "$n" -ge 3 ]]; assert "7.2 fixed pool (-j 2 --no-adaptive): 3 runs ($n)" $?

# Parallel metadata resolution over the full 12-run medium list (cheap).
d="$WORK/batch_meta"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i "$MEDIUM_LIST" -m --meta-jobs 5 -o "$d" -Q >"$d/log.txt" 2>&1
n=$(find "$d" -name '*.metadata.tsv' | wc -l | tr -d ' ')
[[ "$n" -ge 12 ]]; assert "7.3 parallel metadata (--meta-jobs 5): 12 tsv ($n)" $?

# =============================================================================
# 8. Resume / skip-if-done  (re-run is idempotent)
# =============================================================================
banner "8. Resume / skip already-completed runs"
d="$WORK/resume"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g -o "$d" -Q >"$d/log1.txt" 2>&1
adaptiseq -i ERR1726497 -g -o "$d" -Q >"$d/log2.txt" 2>&1
rc=$?
# second run must succeed and must not re-download (success.log already has it)
{ [[ "$rc" -eq 0 ]] && grep -q "ERR1726497" "$d/success.log"; }
assert "8.1 re-run is idempotent (run stays in success.log)" $?

# =============================================================================
# 9. Flags: speed cap (-s), skip-md5 (-k), quiet (-Q)
# =============================================================================
banner "9. Misc flags (-s, -k, -Q)"
d="$WORK/flags"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g -k -Q -s 50 -o "$d" >"$d/log.txt" 2>&1
{ [[ $? -eq 0 ]] && find "$d" -name '*.fastq.gz' | grep -q .; }
assert "9.1 -s 50 -k -Q combined download" $?

# =============================================================================
# 10. Merge (-e ex)   [TIER=full: multi-run experiment ~1 GB]
# =============================================================================
banner "10. Merge FASTQ per Experiment (-e ex)"
if [[ "$TIER" == "full" ]]; then
  if have fasterq-dump; then
    d="$WORK/merge"; rm -rf "$d"; mkdir -p "$d"
    adaptiseq -i SRX003906 -g -e ex -o "$d" -Q >"$d/log.txt" 2>&1
    find "$d" -name 'SRX003906*.fastq.gz' | grep -q .
    assert "10.1 SRX003906 merged to SRX003906*.fastq.gz" $?
  else
    record_skip "10.1 merge — fasterq-dump missing"
  fi
else
  record_skip "10.1 merge (-e ex) — TIER=full only (~1 GB, 5 runs)"
fi

# =============================================================================
# 11. Aspera (-a)   [ENA adaptive pool; needs real ascp; UDP 33001]
# =============================================================================
banner "11. Aspera high-speed download (-a, ENA)"
if [[ "$ASPERA" == "1" ]]; then
  if have ascp; then
    d="$WORK/aspera"; rm -rf "$d"; mkdir -p "$d"
    # small ENA pool -> exercises the adaptive (efficiency-hysteresis) controller
    adaptiseq -i "$ASPERA_LIST" -a -g --aspera-efficiency 0.8 -o "$d" -Q >"$d/log.txt" 2>&1
    rc=$?
    n=$(grep -c . "$d/success.log" 2>/dev/null || echo 0)
    if [[ "$rc" -eq 0 && "$n" -ge 3 ]]; then
      record_pass "11.1 ENA aspera pool: 3 runs ($n)"
    else
      echo "    (tail of aspera log)"; tail -n 15 "$d/log.txt" | sed 's/^/    /'
      record_fail "11.1 ENA aspera pool (rc=$rc, runs=$n) — Colab often blocks UDP 33001"
    fi
  else
    record_skip "11.1 aspera — ascp not on PATH (install aspera-cli)"
  fi
else
  record_skip "11.1 aspera (-a) — set ASPERA=1 or TIER=full to run"
fi

# =============================================================================
# 12. Python API: get_metadata / resolve / fetch / typed exceptions
# =============================================================================
banner "12. Python API"
PYWORK="$WORK/api" REPO="$REPO" MIXED_LIST="$MIXED_LIST" python3 - <<'PY'
import os, sys
from pathlib import Path
work = Path(os.environ["PYWORK"]); work.mkdir(parents=True, exist_ok=True)
import adaptiseq
from adaptiseq import fetch, resolve, get_metadata, FetchResult
from adaptiseq.errors import InvalidAccessionError

def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond

ok = True
# get_metadata -> list[dict]
rows = get_metadata("SRR1553469")
ok &= check("12.1 get_metadata returns non-empty list[dict]",
            isinstance(rows, list) and len(rows) > 0 and isinstance(rows[0], dict))

# resolve -> list[str] of fastq.gz URLs (no download)
urls = resolve("SRR1553469", database="ena", gzip=True)
ok &= check("12.2 resolve returns fastq.gz URLs",
            isinstance(urls, list) and any("fastq.gz" in u for u in urls))

# fetch a tiny batch -> FetchResult with success_ids
batch = os.environ.get("MIXED_LIST", "")
if not (batch and os.path.exists(batch)):
    batch = "ERR1726497"   # fall back to a single tiny accession
res = fetch(batch, outdir=str(work/"fetch"), gzip=True, quiet=True)
ok &= check("12.3 fetch returns FetchResult with success_ids",
            isinstance(res, FetchResult) and len(res.success_ids) >= 1 and res.failed is False)

# typed exception on a bogus accession
try:
    get_metadata("NOT_AN_ACCESSION_123")
    ok &= check("12.4 invalid accession raises InvalidAccessionError", False)
except InvalidAccessionError:
    ok &= check("12.4 invalid accession raises InvalidAccessionError", True)
except adaptiseq.AdaptiSeqError:
    ok &= check("12.4 invalid accession raises AdaptiSeqError subclass", True)

sys.exit(0 if ok else 1)
PY
assert "12.x Python API block" $?

# =============================================================================
# 13. Error handling / preflight  (these MUST exit non-zero)
# =============================================================================
banner "13. Error handling (expected non-zero exits)"
expect_fail(){ local name="$1"; shift; "$@" >/dev/null 2>&1; [[ $? -ne 0 ]]; assert "$name" $?; }
expect_fail "13.1 no -i input rejected"            adaptiseq -Q
expect_fail "13.2 unknown option rejected"         adaptiseq -i SRR1553469 --bogus-flag
expect_fail "13.3 invalid -e value rejected"       adaptiseq -i SRX003906 -e zzz
expect_fail "13.4 merge on a Run ID rejected"      adaptiseq -i SRR1553469 -g -e ex
expect_fail "13.5 aspera + -d sra rejected"        adaptiseq -i SRR1553469 -a -d sra

# =============================================================================
# Summary
# =============================================================================
hr; printf '%sSUMMARY%s   PASS=%d  FAIL=%d  SKIP=%d\n' "$c_yel" "$c_off" "$PASS" "$FAIL" "$SKIP"; hr
for r in "${RESULTS[@]}"; do printf '  %s\n' "$r"; done
hr
echo "Artifacts under: $WORK"
[[ "$FAIL" -eq 0 ]] && { echo "${c_green}ALL GREEN${c_off}"; exit 0; } || { echo "${c_red}$FAIL test(s) failed${c_off}"; exit 1; }
