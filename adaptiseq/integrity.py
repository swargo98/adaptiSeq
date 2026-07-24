"""Integrity checking — faithful ports of ``checkSRA`` / ``checkGSA``.

Policy (Section 3.4), reproduced exactly:

* ENA/SRA ``.fastq.gz`` (``-g`` direct mode): md5sum each file against the
  metadata table.
* ENA/SRA ``.sra``: ``vdb-validate ./SRR``.
* GSA: md5sum against the project ``CRA.md5sum.txt``.
* Up to three rounds of re-download, then record in ``fail.log``; successes go to
  ``success.log`` (``$(date)\t$ID``). ``-k`` skips the check entirely.

Retry counter: reset per Run/file (NOTES.md decision #2), not process-global.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .console import bright_green, bright_red, bright_yellow, green
from .logs import mark_fail, mark_success
from .net import USER_AGENT_MOZILLA, wget_to_file
from .options import RunContext


# ================================ helpers =======================================

def md5sum(path: Path) -> str:
    """Lower-case md5 hex digest of a file (``md5sum file | awk '{print $1}'``)."""
    import hashlib

    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def vdb_validate(ctx: RunContext, srr: str) -> bool:
    """``vdb-validate ./SRR > SRR.log 2>&1``; rc==0 is pass. Removes log on pass."""
    log = ctx.path(f"{srr}.log")
    with open(log, "w") as fh:
        rc = subprocess.run(
            ["vdb-validate", f"./{srr}"],
            cwd=str(ctx.workdir),
            stdout=fh,
            stderr=subprocess.STDOUT,
        ).returncode
    if rc == 0:
        try:
            log.unlink()
        except FileNotFoundError:
            pass
        return True
    return False


def _gzip_fastq_files(ctx: RunContext, srr: str) -> List[str]:
    """Enumerate ``${SRR}(_..)?\\.fastq\\.gz`` files for a Run."""
    tsv = ctx.metadata_tsv()
    if not tsv.exists():
        return []
    pat = re.compile(re.escape(srr) + r"(?:_[^;/\s]*)?\.fastq\.gz")
    found: List[str] = []
    for line in tsv.read_text(errors="replace").splitlines():
        if srr in line:
            found.extend(pat.findall(line))
    # mapfile keeps order but duplicates collapse naturally via the metadata layout;
    # de-dup while preserving order to avoid double-checking the same name.
    seen = set()
    result = []
    for f in found:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


def _gzip_md5_ok(ctx: RunContext, files: List[str]) -> Tuple[bool, Optional[str]]:
    """Return (all_pass, first_mismatch). Each file must exist and its md5 must
    appear somewhere in the metadata.tsv (``grep -q "$md5" metadata``)."""
    tsv_text = ctx.metadata_tsv().read_text(errors="replace")
    for fname in files:
        fpath = ctx.path(fname)
        if not fpath.is_file():
            return False, None
        digest = md5sum(fpath)
        if digest not in tsv_text:
            return False, fname
    return True, None


# ================================ checkSRA ======================================

def check_sra(ctx: RunContext, srr: str, download_fn: Callable[[], None]) -> bool:
    """``checkSRA``: md5-verify a Run. Returns True on success, False on final failure."""
    opts = ctx.options
    reporter = ctx.reporter
    gzip_mode = opts.gzip and not opts.fastq and ctx.database != "sra"
    count = 1

    while True:
        if gzip_mode:
            files = _gzip_fastq_files(ctx, srr)
            if files:
                all_pass, mismatch = _gzip_md5_ok(ctx, files)
                if mismatch is not None:
                    reporter.info(f"{bright_red('MD5 mismatch for:')} {mismatch}")
                if all_pass:
                    reporter.info(
                        bright_green(
                            f"{srr} download and md5 check successful, "
                            f"save {srr} in success.log"
                        )
                    )
                    mark_success(ctx.workdir, srr)
                    return True
                if count <= 1:
                    reporter.info(
                        f"{bright_yellow('Note')}: {srr} validate failed, "
                        f"retry {count} times"
                    )
                    download_fn()
                    count += 1
                    continue
                elif count <= 2:
                    reporter.info(
                        f"{bright_yellow('Note')}: {srr} validate failed, "
                        f"remove the files and retry {count} times"
                    )
                    _rm_files(ctx, files)
                    download_fn()
                    count += 1
                    continue
                else:
                    _rm_files(ctx, files)
                    reporter.info(
                        bright_red(
                            f"{srr} md5 check failed after trying {count} times, "
                            "save Run ID in fail.log"
                        )
                    )
                    mark_fail(ctx.workdir, srr)
                    ctx.failed = True
                    return False
            else:
                reporter.info(
                    f"{bright_yellow('Note')}: No FASTQ files found for {srr}"
                )
                if count <= 2:
                    count += 1
                    download_fn()
                    continue
                else:
                    _rm_files(ctx, files)
                    reporter.info(
                        bright_red(
                            f"{srr} failed: no FASTQ files after retry, "
                            "saving to fail.log"
                        )
                    )
                    mark_fail(ctx.workdir, srr)
                    ctx.failed = True
                    return False
        else:
            if vdb_validate(ctx, srr):
                reporter.info(
                    bright_green(
                        f"{srr} download and md5 check successful, "
                        f"save {srr} in success.log"
                    )
                )
                mark_success(ctx.workdir, srr)
                return True
            if count <= 1:
                reporter.info(
                    f"{bright_yellow('Note')}: {srr} validate failed, "
                    f"retry {count} times"
                )
                download_fn()
                count += 1
                continue
            elif count <= 2:
                reporter.info(
                    f"{bright_yellow('Note')}: {srr} validate failed, "
                    f"remove the file and retry {count} times"
                )
                _rm_one(ctx, srr)
                download_fn()
                count += 1
                continue
            else:
                _rm_one(ctx, srr)
                reporter.info(
                    bright_red(
                        f"{srr} md5 check failed after trying {count} times, "
                        "save Run ID in fail.log"
                    )
                )
                mark_fail(ctx.workdir, srr)
                ctx.failed = True
                return False


def _rm_files(ctx: RunContext, files: List[str]) -> None:
    for f in files:
        p = ctx.path(f)
        if p.is_file():
            p.unlink()


def _rm_one(ctx: RunContext, name: str) -> None:
    p = ctx.path(name)
    if p.is_file():
        p.unlink()


# ================================ checkGSA ======================================

GSA_DOWNLOAD_BASE = "https://download.cncb.ac.cn/"


def ensure_gsa_md5(ctx: RunContext, cra: str) -> Path:
    """Download ``CRA.md5sum.txt`` if missing (the checkGSA preamble)."""
    md5_path = ctx.path(f"{cra}.md5sum.txt")
    if not md5_path.is_file():
        csv_text = ctx.metadata_csv().read_text(errors="replace")
        matches = re.findall(rf"gsa[0-9]+/{re.escape(cra)}|gsa/{re.escape(cra)}", csv_text)
        # uniq (adjacent) then first
        seg = ""
        for m in matches:
            seg = m
            break
        md5_url = f"{GSA_DOWNLOAD_BASE}{seg}/md5sum.txt"
        wget_to_file(md5_url, md5_path, user_agent=USER_AGENT_MOZILLA, quiet=True)
    return md5_path


def verify_gsa(ctx: RunContext, filename: str, cra: str) -> Optional[bool]:
    """Return None if the md5 check is skipped (md5sum unavailable or empty list),
    else True/False for the comparison against ``CRA.md5sum.txt``."""
    md5_path = ensure_gsa_md5(ctx, cra)
    if shutil.which("md5sum") is None or not (
        md5_path.is_file() and md5_path.stat().st_size > 0
    ):
        return None
    wanted = ""
    for line in md5_path.read_text(errors="replace").splitlines():
        if filename in line:
            parts = line.split()
            if parts:
                wanted = parts[0].lower()
            break
    fpath = ctx.path(filename)
    if fpath.is_file() and md5sum(fpath) == wanted:
        return True
    return False
