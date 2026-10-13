#!/usr/bin/env python3
"""Judge one tool's output tree against the ENA manifest -- name-independent.

Why this exists (EXPERIMENT_PLAN §12.2, "bytes + format + md5, not just wall
time"): the E3 arms do not agree on names or layout. fastq-dl renames to
<run>_1.fastq.gz, fetchngs restructures into fastq/, kingfisher can emit .sra,
iseq writes flat. Trusting each tool's own exit code or a naive `du -sb` would
compare different things and let a tool that fetched less, or fetched a
different format, look fast.

So we ignore names entirely and hash the output tree, then match digests against
the manifest's md5 set. A run counts as COMPLETE only when every one of its
expected files is present with a byte-identical md5. That is a single objective
criterion applied identically to every arm, including our own -- adaptiSeq gets
no benefit of the doubt.

Files whose md5 matches nothing in the manifest are reported as `extra` (usually
.sra, metadata, or a decompressed fastq): they are NOT counted as success, and
their presence is what flips `format` away from a clean "gz", which segregates
the row per §12.2 rather than silently comparing it on wall time.

Usage:
    python bench/e3/verify_output.py --manifest D1_fair.manifest --outdir DIR [--jobs 32]

Emits one line of `key=value` pairs on stdout for the harness to splice into its TSV row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple

# Not payload: tool bookkeeping we must not bill anyone for (or credit anyone with).
SKIP_SUFFIXES = (
    ".log", ".part", ".meta", ".tmp", ".aria2", ".st", ".json", ".yml", ".yaml",
    ".html", ".txt", ".tsv", ".csv", ".xlsx", ".md5", ".flag",
)
SKIP_NAMES = {"success.log", "fail.log", "urls.txt", ".has_failed.flag"}
SKIP_DIRS = {"work", ".nextflow", "pipeline_info", ".command", "tmp"}


def md5_of(path: str, _bufsize: int = 8 << 20) -> Tuple[str, str, int]:
    h = hashlib.md5()
    n = 0
    with open(path, "rb") as fh:
        while True:
            b = fh.read(_bufsize)
            if not b:
                break
            h.update(b)
            n += len(b)
    return path, h.hexdigest(), n


def data_files(outdir: Path) -> List[str]:
    out: List[str] = []
    for root, dirs, files in os.walk(outdir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if f in SKIP_NAMES or f.startswith("."):
                continue
            if f.endswith(SKIP_SUFFIXES) and not f.endswith(".fastq.gz"):
                continue
            p = os.path.join(root, f)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            if os.path.getsize(p) == 0:
                continue
            out.append(p)
    return out


def load_manifest(path: Path) -> Dict[str, List[Tuple[str, int, str]]]:
    runs: Dict[str, List[Tuple[str, int, str]]] = {}
    for line in path.read_text().splitlines()[1:]:
        if not line.strip():
            continue
        run, name, nbytes, md5 = line.split("\t")
        runs.setdefault(run, []).append((name, int(nbytes), md5))
    return runs


def fmt_of(paths: List[str]) -> str:
    exts = set()
    for p in paths:
        n = os.path.basename(p)
        if n.endswith(".fastq.gz") or n.endswith(".fq.gz"):
            exts.add("gz")
        elif n.endswith(".fastq") or n.endswith(".fq"):
            exts.add("fastq")
        elif n.endswith(".sra") or ".sra" in n:
            exts.add("sra")
        elif n.endswith(".bam"):
            exts.add("bam")
        else:
            exts.add(os.path.splitext(n)[1].lstrip(".") or "none")
    return ",".join(sorted(exts)) or "-"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=min(32, os.cpu_count() or 8))
    ap.add_argument("--json", type=Path, help="also dump a detailed per-run report")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    want_md5 = {m: (run, name, nb)
                for run, rows in manifest.items() for (name, nb, m) in rows}

    paths = data_files(args.outdir) if args.outdir.exists() else []
    got: Dict[str, Tuple[str, int]] = {}
    total_bytes = 0
    if paths:
        with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            for p, digest, n in ex.map(md5_of, paths, chunksize=1):
                got[digest] = (p, n)
                total_bytes += n

    matched = {d for d in got if d in want_md5}
    extra = [got[d][0] for d in got if d not in want_md5]

    runs_complete = 0
    runs_partial = 0
    for run, rows in manifest.items():
        have = sum(1 for (_n, _b, m) in rows if m in matched)
        if have == len(rows):
            runs_complete += 1
        elif have > 0:
            runs_partial += 1

    files_expected = sum(len(r) for r in manifest.values())
    bytes_expected = sum(b for rows in manifest.values() for (_n, b, _m) in rows)
    bytes_verified = sum(want_md5[d][2] for d in matched)

    if args.json:
        args.json.write_text(json.dumps({
            "runs_complete": runs_complete,
            "runs_partial": runs_partial,
            "runs_expected": len(manifest),
            "files_verified": len(matched),
            "files_expected": files_expected,
            "bytes_verified": bytes_verified,
            "bytes_expected": bytes_expected,
            "bytes_on_disk": total_bytes,
            "extra_files": extra[:50],
        }, indent=2))

    print(
        f"runs_complete={runs_complete} "
        f"runs_partial={runs_partial} "
        f"runs_expected={len(manifest)} "
        f"files_verified={len(matched)} "
        f"files_expected={files_expected} "
        f"bytes_verified={bytes_verified} "
        f"bytes_expected={bytes_expected} "
        f"bytes_on_disk={total_bytes} "
        f"files_on_disk={len(paths)} "
        f"extra_files={len(extra)} "
        f"format={fmt_of(paths)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
