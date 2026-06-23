#!/usr/bin/env bash
# =============================================================================
# adaptiSeq — Colab acceptance test
# -----------------------------------------------------------------------------
# Exercises the features documented in README.md + docs/ against the LIVE
# databases, using small accessions so it finishes on a Colab box. It checks
# both the CLI and the Python API, asserts on the artifacts each command should
# produce, and prints a PASS/FAIL/SKIP summary at the end.
#
# Some claims are intentionally NOT live-tested here because they cannot be
# forced deterministically against the public databases (md5 mismatch -> retry
# -> corrupt-file deletion -> fail.log, 3-file orphan/barcode resolution,
# single-cell I1/R1/R2/R3, merge sa/st byte parity). Those are covered by the
# repo's offline pytest suite — see COLAB_TESTING.md ("Deterministic coverage").
#
# Usage:
#   TIER=quick bash bench/colab_acceptance.sh     # default; small downloads only
#   TIER=full  bash bench/colab_acceptance.sh     # + resume/merge/GEO/GSA/aspera
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

c_green=$'\e[32m'; c_red=$'\e[31m'; c_yel=$'\e[33m'; c_off=$'\e[0m'

hr(){ printf '%s\n' "----------------------------------------------------------------------"; }
banner(){ hr; printf '%s>>> %s%s\n' "$c_yel" "$1" "$c_off"; hr; }

record_pass(){ PASS=$((PASS+1)); RESULTS+=("${c_green}PASS${c_off}  $1"); printf '%sPASS%s  %s\n' "$c_green" "$c_off" "$1"; }
record_fail(){ FAIL=$((FAIL+1)); RESULTS+=("${c_red}FAIL${c_off}  $1"); printf '%sFAIL%s  %s\n' "$c_red" "$c_off" "$1"; }
record_skip(){ SKIP=$((SKIP+1)); RESULTS+=("${c_yel}SKIP${c_off}  $1"); printf '%sSKIP%s  %s\n' "$c_yel" "$c_off" "$1"; }

# assert "<name>" <rc>   (rc==0 -> PASS else FAIL)
assert(){ if [[ "$2" -eq 0 ]]; then record_pass "$1"; else record_fail "$1"; fi; }
have(){ command -v "$1" >/dev/null 2>&1; }

# ---- environment ------------------------------------------------------------
banner "Environment"
adaptiseq --version || { echo "adaptiseq not importable/installed — aborting"; exit 2; }
for t in wget md5sum srapath fasterq-dump vdb-validate pigz axel ascp; do
  if have "$t"; then printf '  %-14s %sfound%s\n' "$t" "$c_green" "$c_off"
  else printf '  %-14s %smissing%s\n' "$t" "$c_yel" "$c_off"; fi
done
echo "TIER=$TIER  ASPERA=$ASPERA  WORK=$WORK"

# =============================================================================
# 1. CLI smoke
# =============================================================================
banner "1. CLI smoke (--version, --help)"
adaptiseq --version | grep -q "adaptiSeq"; assert "1.1 --version prints banner" $?
adaptiseq --help    | grep -q "Usage";    assert "1.2 --help prints usage"    $?

# =============================================================================
# 2. Metadata only (-m) — per database AND per accession-format
# =============================================================================
banner "2. Metadata (-m): all 5 databases + the 6 accession formats"
md(){ # md <name> <accession> <expected-glob>
  local name="$1" acc="$2" glob="$3"
  local d="$WORK/meta_$acc"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i "$acc" -m -Q -o "$d" >"$d/log.txt" 2>&1
  compgen -G "$d/$glob" >/dev/null; assert "$name" $?
}
# --- databases ---
md "2.1 SRA  metadata (.tsv)"  SRR1553469 "SRR1553469*.metadata.tsv"
md "2.2 ENA  metadata (.tsv)"  ERR1726497 "ERR1726497*.metadata.tsv"
md "2.3 DDBJ metadata (.tsv)"  DRR291041  "DRR291041*.metadata.tsv"
md "2.4 GEO  metadata (->SRA)" GSM7417667 "GSM7417667*.metadata.tsv"
# GSA writes CSV + project XLSX; the China endpoint can be flaky/slow from Colab.
d="$WORK/meta_CRR311377"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i CRR311377 -m -Q -o "$d" >"$d/log.txt" 2>&1
if compgen -G "$d/*.metadata.csv"  >/dev/null; then record_pass "2.5 GSA metadata (.csv)"; else record_skip "2.5 GSA metadata (.csv) — GSA endpoint unreachable?"; fi
if compgen -G "$d/CRA*.metadata.xlsx" >/dev/null; then record_pass "2.6 GSA project XLSX";  else record_skip "2.6 GSA project XLSX — GSA endpoint unreachable?"; fi
# --- accession-format matrix (metadata-only, so it stays cheap) ---
md "2.7  format: Project    (PRJDB2759)"  PRJDB2759    "PRJDB2759*.metadata.tsv"
md "2.8  format: Study      (DRP000611)"  DRP000611    "DRP000611*.metadata.tsv"
md "2.9  format: BioSample  (SAMN02951979)" SAMN02951979 "SAMN02951979*.metadata.tsv"
md "2.10 format: Sample     (DRS001566)"  DRS001566    "DRS001566*.metadata.tsv"
md "2.11 format: Experiment (SRX674132)"  SRX674132    "SRX674132*.metadata.tsv"
md "2.12 format: Run        (SRR1553469)" SRR1553469   "SRR1553469*.metadata.tsv"
# project-level resolution over the medium list's parent project (metadata only)
d="$WORK/meta_project"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i PRJNA353374 -m -Q -o "$d" >"$d/log.txt" 2>&1
runs=$(grep -c "SRR50171" "$d"/PRJNA353374*.metadata.tsv 2>/dev/null || echo 0)
if [[ "$runs" -ge 12 ]]; then assert "2.13 project PRJNA353374 resolves >=12 runs ($runs)" 0; else assert "2.13 project PRJNA353374 resolves >=12 runs ($runs)" 1; fi

# =============================================================================
# 3. Raw .sra download (default engine, single accession = non-batch)
# =============================================================================
banner "3. Raw .sra download (default, single accession)"
d="$WORK/raw_sra"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR1553469 -o "$d" -Q >"$d/log.txt" 2>&1
# NCBI delivers the raw SRA file named after the run accession (no .sra suffix)
{ [[ -s "$d/SRR1553469" ]] || find "$d" -name '*.sra' | grep -q .; }
assert "3.1 raw SRA file present" $?
grep -q "SRR1553469" "$d/success.log" 2>/dev/null; assert "3.2 success.log records the run" $?

# =============================================================================
# 4. Direct gzip FASTQ (-g)
# =============================================================================
banner "4. Direct gzip FASTQ (-g)"
d="$WORK/gzip"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR1553469 -g -o "$d" -Q >"$d/log.txt" 2>&1
{ find "$d" -name '*_1.fastq.gz' | grep -q . && find "$d" -name '*_2.fastq.gz' | grep -q .; }
assert "4.1 paired *_1/_2.fastq.gz present" $?
grep -q "SRR1553469" "$d/success.log" 2>/dev/null; assert "4.2 success.log records the run" $?

# 4b. 3-file run: orphan/barcode + _1 + _2 (the run type iseq mishandles)
d="$WORK/threefile"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR22904350 -g -o "$d" -Q >"$d/log.txt" 2>&1
n=$(find "$d" -name 'SRR22904350*.fastq.gz' | wc -l | tr -d ' ')
if [[ "$n" -ge 3 ]]; then assert "4.3 3-file run downloads all 3 parts ($n)" 0; else assert "4.3 3-file run downloads all 3 parts ($n)" 1; fi

# =============================================================================
# 5. SRA -> FASTQ conversion (-q, -q -g)
# =============================================================================
banner "5. SRA->FASTQ conversion (-q, -q -g)"
if have fasterq-dump; then
  d="$WORK/fastq"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i SRR1553469 -q -t 4 -o "$d" -Q >"$d/log.txt" 2>&1
  find "$d" -name '*.fastq' ! -name '*.fastq.gz' | grep -q .; assert "5.1 uncompressed *.fastq (-q)" $?
  d="$WORK/fastq_gz"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i SRR1553469 -q -g -t 4 -o "$d" -Q >"$d/log.txt" 2>&1
  find "$d" -name '*.fastq.gz' | grep -q .; assert "5.2 converted + gzipped (-q -g)" $?
else
  record_skip "5.1 -q conversion — fasterq-dump missing"
  record_skip "5.2 -q -g conversion — fasterq-dump missing"
fi

# =============================================================================
# 6. Source / transport selection (-d, -r)
# =============================================================================
banner "6. Force database / transport (-d sra, -r https, -r ftp)"
d="$WORK/https"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR1553469 -g -r https -o "$d" -Q >"$d/log.txt" 2>&1
find "$d" -name '*.fastq.gz' | grep -q .; assert "6.1 ENA over forced HTTPS (-r https)" $?
d="$WORK/ftp"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g -r ftp -o "$d" -Q >"$d/log.txt" 2>&1
find "$d" -name '*.fastq.gz' | grep -q .; assert "6.2 ENA over forced FTP (-r ftp)" $?
d="$WORK/force_sra"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i SRR1553469 -d sra -o "$d" -Q >"$d/log.txt" 2>&1
{ [[ -s "$d/SRR1553469" ]] || find "$d" -name '*.sra' | grep -q .; }
assert "6.3 forced SRA database (-d sra)" $?
# 6.4 auto transport (default -r): the engine upgrades the ftp:// link to a
# range-capable HTTPS mirror and logs the decision (suppressed by -Q, so omit it).
d="$WORK/httpsfirst"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g -o "$d" >"$d/log.txt" 2>&1
grep -q "HTTPS mirror is range-capable" "$d/log.txt"; assert "6.4 HTTPS-first auto transport selection" $?

# =============================================================================
# 6b. Engine selection + segmented/classic knobs
# =============================================================================
banner "6b. Engine selection & knobs (--engine, --segment-size, --max-*, -p)"
d="$WORK/seg_knobs"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g --engine segmented --segment-size 1 --max-segments 4 \
          --max-conns-per-host 4 -o "$d" -Q >"$d/log.txt" 2>&1
find "$d" -name '*.fastq.gz' | grep -q .; assert "6b.1 segmented engine + knobs" $?
d="$WORK/classic"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g --engine classic -o "$d" -Q >"$d/log.txt" 2>&1
find "$d" -name '*.fastq.gz' | grep -q .; assert "6b.2 classic engine (wget path)" $?
if have axel; then
  d="$WORK/classic_p"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i ERR1726497 -g --engine classic -p 4 -o "$d" -Q >"$d/log.txt" 2>&1
  find "$d" -name '*.fastq.gz' | grep -q .; assert "6b.3 classic engine + -p 4 (axel)" $?
else
  record_skip "6b.3 classic -p (axel) — axel missing"
fi

# =============================================================================
# 7. Batch + adaptive (-j, --adaptive/--no-adaptive, --meta-jobs, knobs)
# =============================================================================
banner "7. Batch download (mixed SRA/ENA/DDBJ list)"
d="$WORK/batch_adaptive"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i "$MIXED_LIST" -g -o "$d" -Q >"$d/log.txt" 2>&1
n=$(grep -c . "$d/success.log" 2>/dev/null || echo 0)
if [[ "$n" -ge 3 ]]; then assert "7.1 adaptive batch: 3 runs ($n)" 0; else assert "7.1 adaptive batch: 3 runs ($n)" 1; fi
d="$WORK/batch_fixed"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i "$MIXED_LIST" -g -j 2 --no-adaptive -o "$d" -Q >"$d/log.txt" 2>&1
n=$(grep -c . "$d/success.log" 2>/dev/null || echo 0)
if [[ "$n" -ge 3 ]]; then assert "7.2 fixed pool (-j 2 --no-adaptive): 3 runs ($n)" 0; else assert "7.2 fixed pool (-j 2 --no-adaptive): 3 runs ($n)" 1; fi
# adaptive tuning knobs are accepted and the batch completes (trajectory only
# logs on long runs, so we don't hard-assert the line on a tiny batch)
d="$WORK/batch_knobs"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i "$MIXED_LIST" -g --probe-window 2 --cc-penalty 1.02 -o "$d" -Q >"$d/log.txt" 2>&1
n=$(grep -c . "$d/success.log" 2>/dev/null || echo 0)
if [[ "$n" -ge 3 ]]; then assert "7.3 adaptive knobs (--probe-window/--cc-penalty)" 0; else assert "7.3 adaptive knobs (--probe-window/--cc-penalty)" 1; fi
if grep -q "adaptive worker trajectory" "$d/log.txt"; then record_pass "7.4 adaptive trajectory logged"; else record_skip "7.4 adaptive trajectory — none logged (batch too short)"; fi
# parallel metadata resolution over the full 12-run medium list (cheap)
d="$WORK/batch_meta"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i "$MEDIUM_LIST" -m --meta-jobs 5 -o "$d" -Q >"$d/log.txt" 2>&1
n=$(find "$d" -name '*.metadata.tsv' | wc -l | tr -d ' ')
if [[ "$n" -ge 12 ]]; then assert "7.5 parallel metadata (--meta-jobs 5): 12 tsv ($n)" 0; else assert "7.5 parallel metadata (--meta-jobs 5): 12 tsv ($n)" 1; fi

# =============================================================================
# 8. Resume / skip
# =============================================================================
banner "8. Resume / skip"
d="$WORK/resume"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g -o "$d" -Q >"$d/log1.txt" 2>&1
adaptiseq -i ERR1726497 -g -o "$d" -Q >"$d/log2.txt" 2>&1; rc=$?
{ [[ "$rc" -eq 0 ]] && grep -q "ERR1726497" "$d/success.log"; }
assert "8.1 re-run idempotent (completed run skipped)" $?
# 8b. partial-transfer resume: interrupt mid-file, confirm .part, then finish
if [[ "$TIER" == "full" ]]; then
  d="$WORK/partial"; rm -rf "$d"; mkdir -p "$d"
  timeout 4 adaptiseq -i SRR7706354 -g -o "$d" -Q >"$d/log1.txt" 2>&1
  if find "$d" -name '*.part' | grep -q .; then
    record_pass "8.2 interrupted download leaves *.part"
    adaptiseq -i SRR7706354 -g -o "$d" -Q >"$d/log2.txt" 2>&1; rc=$?
    { [[ "$rc" -eq 0 ]] && find "$d" -name 'SRR7706354_1.fastq.gz' | grep -q . \
      && ! find "$d" -name '*.part' | grep -q .; }
    assert "8.3 re-run resumes *.part to completion" $?
  else
    record_skip "8.2 partial resume — file completed before interrupt (too fast)"
    record_skip "8.3 partial resume completion"
  fi
else
  record_skip "8.2 partial *.part resume — TIER=full only (~260 MB)"
  record_skip "8.3 partial resume completion — TIER=full only"
fi

# =============================================================================
# 9. Misc flags (-s, -k, -Q)
# =============================================================================
banner "9. Misc flags (-s, -k, -Q)"
d="$WORK/flags"; rm -rf "$d"; mkdir -p "$d"
adaptiseq -i ERR1726497 -g -k -Q -s 50 -o "$d" >"$d/log.txt" 2>&1; rc=$?
{ [[ "$rc" -eq 0 ]] && find "$d" -name '*.fastq.gz' | grep -q .; }
assert "9.1 -s 50 -k -Q combined download" $?

# =============================================================================
# 10. Merge (-e)
# =============================================================================
banner "10. Merge FASTQ (-e ex; sa/st guards)"
if [[ "$TIER" == "full" ]] && have fasterq-dump; then
  d="$WORK/merge"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i SRX003906 -g -e ex -o "$d" -Q >"$d/log.txt" 2>&1
  find "$d" -name 'SRX003906*.fastq.gz' | grep -q .; assert "10.1 -e ex merges SRX003906" $?
elif [[ "$TIER" != "full" ]]; then
  record_skip "10.1 -e ex merge — TIER=full only (~1 GB, 5 runs)"
else
  record_skip "10.1 -e ex merge — fasterq-dump missing"
fi
# positive -e sa: merge a 2-run Sample into one pair (st uses the same code path
# but studies are large, so st stays guard-only + offline byte-parity).
if [[ "$TIER" == "full" ]] && have fasterq-dump; then
  d="$WORK/merge_sa"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i SAMN02951979 -g -e sa -o "$d" -Q >"$d/log.txt" 2>&1
  { find "$d" -name 'SAMN02951979_1.fastq.gz' | grep -q . && find "$d" -name 'SAMN02951979_2.fastq.gz' | grep -q .; }
  assert "10.4 -e sa merges a 2-run Sample (SAMN02951979)" $?
else
  record_skip "10.4 -e sa positive merge — TIER=full only (~175 MB)"
fi
# byte-parity of ex/sa/st merge is covered by the offline pytest suite; here we
# also confirm the accession-type guards (sa/st cannot apply to a Run ID).
if adaptiseq -i SRR1553469 -g -e sa >/dev/null 2>&1; then assert "10.2 -e sa rejects a Run ID" 1; else assert "10.2 -e sa rejects a Run ID" 0; fi
if adaptiseq -i SRR1553469 -g -e st >/dev/null 2>&1; then assert "10.3 -e st rejects a Run ID" 1; else assert "10.3 -e st rejects a Run ID" 0; fi

# =============================================================================
# 11. Aspera (-a, ENA adaptive pool) + GEO/GSA sequence downloads (full tier)
# =============================================================================
banner "11. Aspera (-a) + GEO/GSA sequence (full tier)"
if [[ "$ASPERA" == "1" ]]; then
  if have ascp; then
    d="$WORK/aspera"; rm -rf "$d"; mkdir -p "$d"
    adaptiseq -i "$ASPERA_LIST" -a -g --aspera-efficiency 0.8 -o "$d" -Q >"$d/log.txt" 2>&1; rc=$?
    n=$(grep -c . "$d/success.log" 2>/dev/null || echo 0)
    if [[ "$rc" -eq 0 && "$n" -ge 3 ]]; then record_pass "11.1 ENA aspera pool: 3 runs ($n)"
    else echo "    (tail of aspera log)"; tail -n 12 "$d/log.txt" | sed 's/^/    /'
         record_fail "11.1 ENA aspera (rc=$rc, runs=$n) — Colab often blocks UDP 33001"; fi
  else
    record_skip "11.1 aspera — ascp not on PATH (install aspera-cli)"
  fi
else
  record_skip "11.1 aspera (-a) — set ASPERA=1 or TIER=full to run"
fi
if [[ "$TIER" == "full" ]]; then
  # GEO sequence download (GSE/GSM -> PRJNA/SAMN -> SRA)
  d="$WORK/geo"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i GSM7417667 -g -o "$d" -Q >"$d/log.txt" 2>&1; rc=$?
  { [[ "$rc" -eq 0 ]] && find "$d" -name '*.fastq.gz' | grep -q .; }
  assert "11.2 GEO sequence download (GSM7417667)" $?
  # GSA sequence download (Huawei-Cloud preferred); China endpoint can be flaky
  d="$WORK/gsa"; rm -rf "$d"; mkdir -p "$d"
  adaptiseq -i CRR311377 -o "$d" -Q >"$d/log.txt" 2>&1; rc=$?
  if [[ "$rc" -eq 0 ]] && find "$d" -type f \( -name '*.gz' -o -name '*.bz2' -o -name '*.bam' \) | grep -q .; then
    record_pass "11.3 GSA sequence download (CRR311377)"
  else
    echo "    (tail of GSA log)"; tail -n 8 "$d/log.txt" | sed 's/^/    /'
    record_skip "11.3 GSA sequence download — GSA/Huawei endpoint unreachable from Colab?"
  fi
  # GSA Aspera (-a): best-effort. The docs note this path is NOT yet validated
  # against the live GSA endpoint, so a PASS is genuinely new info; a SKIP (key
  # download / China endpoint / UDP) is expected, never a hard failure.
  if [[ "$ASPERA" == "1" ]] && have ascp; then
    d="$WORK/gsa_aspera"; rm -rf "$d"; mkdir -p "$d"
    adaptiseq -i CRR311377 -a -o "$d" -Q >"$d/log.txt" 2>&1; rc=$?
    if [[ "$rc" -eq 0 ]] && find "$d" -type f \( -name '*.gz' -o -name '*.bz2' -o -name '*.bam' \) | grep -q .; then
      record_pass "11.4 GSA aspera download (CRR311377)"
    else
      record_skip "11.4 GSA aspera — endpoint/key/UDP unavailable (docs: not yet validated live)"
    fi
  else
    record_skip "11.4 GSA aspera — needs ASPERA=1 + ascp"
  fi
else
  record_skip "11.2 GEO sequence download — TIER=full only"
  record_skip "11.3 GSA sequence download — TIER=full only"
  record_skip "11.4 GSA aspera download — TIER=full only"
fi

# =============================================================================
# 12. Python API
# =============================================================================
banner "12. Python API (functions, FetchResult, reporter, py.typed, exceptions)"
PYWORK="$WORK/api" REPO="$REPO" MIXED_LIST="$MIXED_LIST" python3 - <<'PY'
import io, os, sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
work = Path(os.environ["PYWORK"]); work.mkdir(parents=True, exist_ok=True)

import adaptiseq
from adaptiseq import fetch, resolve, get_metadata, FetchResult
from adaptiseq.console import ListReporter
from adaptiseq.errors import (AdaptiSeqError, InvalidAccessionError, MetadataError,
                              DownloadError, IntegrityError, MergeError,
                              PreflightError, EngineUnavailableError)

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS" if cond else "FAIL"), name); return cond

# get_metadata -> list[dict]
rows = get_metadata("SRR1553469")
check("12.1 get_metadata -> non-empty list[dict]",
      isinstance(rows, list) and rows and isinstance(rows[0], dict))

# resolve -> list[str] of fastq.gz URLs (no download)
urls = resolve("SRR1553469", database="ena", gzip=True)
check("12.2 resolve -> fastq.gz URLs", isinstance(urls, list) and any("fastq.gz" in u for u in urls))

# fetch a tiny batch -> FetchResult with every documented field, via a reporter
batch = os.environ.get("MIXED_LIST", "")
if not (batch and os.path.exists(batch)): batch = "ERR1726497"
rep = ListReporter()
buf_o, buf_e = io.StringIO(), io.StringIO()
with redirect_stdout(buf_o), redirect_stderr(buf_e):
    res = fetch(batch, outdir=str(work/"fetch"), gzip=True, quiet=True, reporter=rep,
                # exercise keyword-equivalents of CLI flags (passthrough must work)
                jobs=4, adaptive=True, meta_jobs=2, segment_size_mb=8, max_segments=4,
                max_conns_per_host=4, threads=4, speed=100, skip_md5=False)
check("12.3 fetch -> FetchResult", isinstance(res, FetchResult))
check("12.4 FetchResult fields present",
      hasattr(res,"accession") and isinstance(res.outdir, Path)
      and isinstance(res.failed, bool) and isinstance(res.success_ids, list)
      and isinstance(res.fail_ids, list))
check("12.5 fetch succeeded (>=1 success id, failed False)",
      len(res.success_ids) >= 1 and res.failed is False)
# default API path is silent: with an explicit reporter, messages go to the
# reporter, NOT to stdout/stderr (the API never prints on its own).
check("12.6 API does not write to stdout/stderr itself",
      buf_o.getvalue() == "" and buf_e.getvalue() == "")
check("12.7 reporter received progress messages", len(rep.infos) > 0)

# py.typed marker shipped
check("12.8 py.typed marker present",
      (Path(adaptiseq.__file__).parent / "py.typed").exists())

# every documented exception subclasses AdaptiSeqError
check("12.9 typed exceptions subclass AdaptiSeqError",
      all(issubclass(e, AdaptiSeqError) for e in
          (InvalidAccessionError, MetadataError, DownloadError, IntegrityError,
           MergeError, PreflightError, EngineUnavailableError)))

# raises (never sys.exit) on a bad accession
try:
    get_metadata("NOT_AN_ACCESSION_123"); check("12.10 bad accession raises (no sys.exit)", False)
except AdaptiSeqError:
    check("12.10 bad accession raises AdaptiSeqError (no sys.exit)", True)
except SystemExit:
    check("12.10 bad accession raises (no sys.exit)", False)

sys.exit(0 if ok else 1)
PY
assert "12.x Python API block" $?

# =============================================================================
# 13. Error handling — non-zero exits AND actionable messages
# =============================================================================
banner "13. Error handling (exit codes + actionable messages)"
expect_fail(){ local name="$1"; shift; if "$@" >/dev/null 2>&1; then assert "$name" 1; else assert "$name" 0; fi; }
expect_fail "13.1 no -i input rejected"       adaptiseq -Q
expect_fail "13.2 unknown option rejected"    adaptiseq -i SRR1553469 --bogus-flag
expect_fail "13.3 invalid -e value rejected"  adaptiseq -i SRX003906 -e zzz
expect_fail "13.4 merge on a Run ID rejected" adaptiseq -i SRR1553469 -g -e ex
expect_fail "13.5 aspera + -d sra rejected"   adaptiseq -i SRR1553469 -a -d sra
# message quality: errors carry "Error:" + a "How to solve?" suggestion
msg="$(adaptiseq -i SRR99999999 -g -Q 2>&1)"
{ grep -q "Error" <<<"$msg" && grep -q "How to solve?" <<<"$msg"; }
assert "13.6 error output is actionable (Error + How to solve?)" $?
# batch failure semantics: bad item fails, good item still succeeds, exit != 0
d="$WORK/batch_fail"; rm -rf "$d"; mkdir -p "$d"
printf 'ERR1726497\nSRR99999999\n' > "$WORK/badlist.txt"
adaptiseq -i "$WORK/badlist.txt" -g -Q -o "$d" >"$d/log.txt" 2>&1; rc=$?
{ [[ "$rc" -ne 0 ]] && grep -q "ERR1726497" "$d/success.log"; }
assert "13.7 batch continues past failure, exits non-zero" $?

# =============================================================================
# Summary
# =============================================================================
hr; printf '%sSUMMARY%s   PASS=%d  FAIL=%d  SKIP=%d\n' "$c_yel" "$c_off" "$PASS" "$FAIL" "$SKIP"; hr
for r in "${RESULTS[@]}"; do printf '  %s\n' "$r"; done
hr
echo "Artifacts under: $WORK"
if [[ "$FAIL" -eq 0 ]]; then echo "${c_green}ALL GREEN${c_off}"; exit 0; else echo "${c_red}$FAIL test(s) failed${c_off}"; exit 1; fi
