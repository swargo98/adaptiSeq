"""``success.log`` / ``fail.log`` helpers — faithful port of iseq's log handling.

iseq records one ``$(date)\t$ID`` line per Run/file. "Already downloaded" is a
*substring* test (``grep -c $ID success.log``), and a success removes the ID from
``fail.log`` (``sed -i "/$ID/d"``). The differential harness compares these logs
as **sets of IDs** (the 2nd tab field), so the exact date string is cosmetic;
we still reproduce the ``date``-style timestamp for realism.
"""

from __future__ import annotations

import time
from pathlib import Path

SUCCESS_LOG = "success.log"
FAIL_LOG = "fail.log"


def _timestamp() -> str:
    """Reproduce the default ``date`` output, e.g. ``Wed Jun 11 05:03:00 UTC 2026``."""
    return time.strftime("%a %b %e %H:%M:%S %Z %Y")


def ensure_success_log(workdir: Path) -> None:
    p = Path(workdir) / SUCCESS_LOG
    if not p.exists():
        p.touch()


def in_success(workdir: Path, token: str) -> bool:
    """``grep -c $token success.log >= 1`` — substring match over all lines."""
    p = Path(workdir) / SUCCESS_LOG
    if not p.exists():
        return False
    text = p.read_text(errors="replace")
    return any(token in line for line in text.splitlines())


def mark_success(workdir: Path, token: str) -> None:
    """Append ``$(date)\\t$token`` to success.log and drop it from fail.log."""
    p = Path(workdir) / SUCCESS_LOG
    with p.open("a") as fh:
        fh.write(f"{_timestamp()}\t{token}\n")
    remove_from_fail(workdir, token)


def mark_fail(workdir: Path, token: str) -> None:
    """Append ``$(date)\\t$token`` to fail.log."""
    p = Path(workdir) / FAIL_LOG
    with p.open("a") as fh:
        fh.write(f"{_timestamp()}\t{token}\n")


def remove_from_fail(workdir: Path, token: str) -> None:
    """``sed -i "/$token/d" fail.log`` — drop any line containing ``token``."""
    p = Path(workdir) / FAIL_LOG
    if not p.exists():
        return
    lines = p.read_text(errors="replace").splitlines(keepends=True)
    kept = [ln for ln in lines if token not in ln]
    p.write_text("".join(kept))
