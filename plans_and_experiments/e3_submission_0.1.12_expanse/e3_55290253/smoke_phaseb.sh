#!/usr/bin/env bash
# Short E3 smoke test — run on Expanse AFTER `conda activate adaptiseq_e3`.
#
# Proves the whole adaptiSeq download path works end-to-end against live ENA AND
# that the Phase B fix holds: the per-accession loop must NOT re-resolve/re-fetch
# files the parallel batch phase already downloaded. Before the fix, Phase B did
# one ~15 s network resolution per accession (the 49-min tail on 3a); after it,
# Phase B re-resolutions must be ZERO on a clean run.
#
#   conda activate adaptiseq_e3
#   bash bench/e3/smoke_phaseb.sh                 # default: SMOKE_D1 (3 tiny files)
#   LIST=datasets/D1_fair_PRJNA916347.txt N=25 bash bench/e3/smoke_phaseb.sh
#
# Runs with md5 checking ON (no -k) — the real E3 protocol. Needs sra-tools on
# PATH (the conda env provides it). Best run in an interactive compute-node job,
# but works anywhere with egress; it is a correctness check, not a benchmark.

set -uo pipefail
export PS1="${PS1:-}"

E3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E3_DIR/../.." && pwd)"
DATASETS="${DATASETS:-$REPO_DIR/datasets}"
PY="${E3_PYTHON:-python3}"

LIST="${LIST:-$DATASETS/SMOKE_D1.txt}"
N="${N:-0}"                                  # >0 = use only the first N accessions
WORK="${WORK:-$(mktemp -d)}"
LOG="$WORK/arm.log"

# Derive the manifest from the list name (…foo.txt -> …foo.manifest).
MANIFEST="${MANIFEST:-${LIST%.txt}.manifest}"

# Optionally slice the list to keep the run short.
RUNLIST="$WORK/list.txt"
if [[ "$N" -gt 0 ]]; then head -n "$N" "$LIST" > "$RUNLIST"; else cp "$LIST" "$RUNLIST"; fi
n_acc=$(grep -c . "$RUNLIST")

echo "=== adaptiSeq Phase B smoke test ==="
echo "  host      : $(hostname)"
echo "  list      : $LIST  (${n_acc} accessions)"
echo "  manifest  : $MANIFEST"
echo "  workdir   : $WORK"
command -v srapath >/dev/null || echo "  WARN: srapath not on PATH — md5-on run may fail preflight"

# --- run the real adaptiSeq arm (md5 ON, batch + Phase B), timed ---------------
t0=$SECONDS
( cd "$WORK" && "$PY" "$E3_DIR/aseq_run.py" \
    -i "$RUNLIST" -g --no-adaptive -j 8 --meta-jobs 8 -Q -o . ) > "$LOG" 2>&1
rc=$?
elapsed=$((SECONDS - t0))
echo "  arm exit  : $rc   wall: ${elapsed}s"

fail=0

# --- CHECK 0: the arm actually ran and produced files -------------------------
# Everything else is meaningless if the download crashed, so gate on this first
# and surface the arm's own error inline (no hunting for a temp log).
n_files=$(find "$WORK" -maxdepth 1 -name '*.fastq.gz' | wc -l)
echo "=== CHECK 0: arm ran and downloaded files ==="
echo "  exit=$rc  files_on_disk=$n_files"
if [[ "$rc" -ne 0 || "$n_files" -eq 0 ]]; then
    echo "  FAIL — arm did not complete; last 30 lines of its log:"
    echo "  ----------------------------------------------------------------"
    tail -n 30 "$LOG" | sed 's/^/  | /'
    echo "  ----------------------------------------------------------------"
    echo "=== SMOKE FAILED (arm crashed) — full log: $LOG ==="
    exit 1
fi

# --- CHECK 1: Phase B did NOT re-resolve present files -------------------------
# `_download_ena_fastq` (the sequential Phase B download path) is the only thing
# that emits a "File size:" line. On a clean run where the batch phase already
# fetched everything, the fixed Phase B verifies in place -> zero such lines.
# (grep -c always prints a count; tolerate its exit-1 on zero matches.)
reresolves=$(grep -c 'File size:' "$LOG" 2>/dev/null); reresolves=${reresolves:-0}
echo "=== CHECK 1: Phase B re-resolutions (want 0) ==="
echo "  'File size:' lines in Phase B : $reresolves"
if [[ "$reresolves" -eq 0 ]]; then
    echo "  PASS — Phase B verified in place, no per-accession re-resolution"
else
    echo "  FAIL — Phase B re-resolved $reresolves file(s); the fix is not active"
    fail=1
fi

# --- CHECK 2: every file present and md5-correct (the real judge) --------------
echo "=== CHECK 2: md5 verification vs manifest ==="
if [[ -f "$MANIFEST" ]]; then
    "$PY" "$E3_DIR/verify_output.py" --outdir "$WORK" --manifest "$MANIFEST" \
        | tee "$WORK/verify.txt"
    # verify_output prints runs_complete=X runs_expected=Y; require equality.
    read -r rc_done rc_exp < <(sed -n 's/.*runs_complete=\([0-9]*\).*runs_expected=\([0-9]*\).*/\1 \2/p' "$WORK/verify.txt")
    if [[ -n "${rc_done:-}" && "$rc_done" == "$rc_exp" && "$rc_done" -gt 0 ]]; then
        echo "  PASS — $rc_done/$rc_exp runs verified byte-identical"
    else
        echo "  FAIL — only ${rc_done:-0}/${rc_exp:-?} runs verified"
        fail=1
    fi
else
    echo "  SKIP — no manifest at $MANIFEST"
fi

# --- CHECK 3: arm exited cleanly ----------------------------------------------
echo "=== CHECK 3: arm exit code ==="
if [[ "$rc" -eq 0 ]]; then echo "  PASS"; else echo "  FAIL — exit $rc (see $LOG)"; fail=1; fi

echo "=== phase split (from log timestamps) ==="
a_last=$(grep 'adaptiseq.batch: downloaded' "$LOG" | grep -oE '^[0-9]{2}:[0-9]{2}:[0-9]{2}' | tail -1)
b_last=$(grep 'download finished' "$LOG" | grep -oE '^[0-9]{2}:[0-9]{2}:[0-9]{2}' | tail -1)
echo "  Phase A last download : ${a_last:-n/a}"
echo "  Phase B last finish   : ${b_last:-n/a}   (should be within seconds of Phase A)"

if [[ "$fail" -eq 0 ]]; then
    echo "=== SMOKE PASSED ==="; rm -rf "$WORK"; exit 0
else
    echo "=== SMOKE FAILED — inspect $LOG ==="; exit 1
fi
