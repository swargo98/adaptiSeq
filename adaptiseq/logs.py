"""``success.log`` / ``fail.log`` helpers.

One ``$(date)\t$ID`` line is recorded per Run/file. "Already downloaded" asks whether the
ID's field in ``success.log`` is the token, or a name that starts with the token followed by
a character that cannot continue an ID (``_`` or ``.``, as in ``SRR123_1.fastq.gz``); so
``SRR123`` is not found by ``SRR1234``. iSeq's ``grep -c $ID`` is a substring test, which
skipped a Run whose ID is a prefix of an ID already downloaded and erased the longer ID's
line from ``fail.log`` (issue #2). A success removes the ID, and the file names that
belong to it, from ``fail.log``. The differential harness compares these logs as **sets of
IDs** (the 2nd tab field), so the exact date string is cosmetic; we still write a
``date``-style timestamp for realism.

``success.log`` is read once and kept in memory; the copy is refreshed when the file's
size or modification time differs from what this process last saw (another process, or a
hand edit), and kept current by ``mark_success`` so a batch does not re-read the file for
every Run.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Dict, Set, Tuple

SUCCESS_LOG = "success.log"
FAIL_LOG = "fail.log"


def _timestamp() -> str:
    """Reproduce the default ``date`` output, e.g. ``Wed Jun 11 05:03:00 UTC 2026``."""
    return time.strftime("%a %b %e %H:%M:%S %Z %Y")


def ensure_success_log(workdir: Path) -> None:
    p = Path(workdir) / SUCCESS_LOG
    if not p.exists():
        p.touch()


_lock = threading.RLock()
# path -> (st_mtime_ns, st_size, keys). ``keys`` holds every logged ID and each of its
# prefixes that ends before a non-alphanumeric character.
_cache: Dict[str, Tuple[int, int, Set[str]]] = {}


def _field(line: str) -> str:
    """The ID of a log line: its 2nd tab field (the whole line when there is no tab)."""
    parts = line.rstrip("\r\n").split("\t")
    return (parts[1] if len(parts) > 1 else parts[0]).strip()


def _keys(entry: str) -> Set[str]:
    """``entry`` and every prefix of it that stops before a non-alphanumeric character."""
    out = {entry}
    out.update(entry[:i] for i, ch in enumerate(entry) if not ch.isalnum() and i)
    return out


def _matches(entry: str, token: str) -> bool:
    """True when ``entry`` is ``token`` or a name that begins with it (``token_1.fastq.gz``)."""
    return entry == token or (entry.startswith(token) and not entry[len(token)].isalnum())


def _read_keys(p: Path) -> Tuple[int, int, Set[str]]:
    st = p.stat()
    keys: Set[str] = set()
    for line in p.read_text(errors="replace").splitlines():
        entry = _field(line)
        if entry:
            keys |= _keys(entry)
    return st.st_mtime_ns, st.st_size, keys


def in_success(workdir: Path, token: str) -> bool:
    """True when ``token`` is logged in success.log (see the module docstring)."""
    p = Path(workdir) / SUCCESS_LOG
    token = token.strip()
    if not token:
        return False
    with _lock:
        try:
            st = p.stat()
        except OSError:
            _cache.pop(str(p), None)
            return False
        hit = _cache.get(str(p))
        if hit is None or (hit[0], hit[1]) != (st.st_mtime_ns, st.st_size):
            hit = _read_keys(p)
            _cache[str(p)] = hit
        return token in hit[2]


def mark_success(workdir: Path, token: str) -> None:
    """Append ``$(date)\\t$token`` to success.log and drop it from fail.log."""
    p = Path(workdir) / SUCCESS_LOG
    with _lock:
        known = _cache.get(str(p))
        try:
            before = p.stat()
        except OSError:
            before = None
        with p.open("a") as fh:
            fh.write(f"{_timestamp()}\t{token}\n")
        if known is not None and before is not None and (known[0], known[1]) == (before.st_mtime_ns, before.st_size):
            st = p.stat()
            _cache[str(p)] = (st.st_mtime_ns, st.st_size, known[2] | _keys(token))
        else:
            _cache.pop(str(p), None)
    remove_from_fail(workdir, token)


def mark_fail(workdir: Path, token: str) -> None:
    """Append ``$(date)\\t$token`` to fail.log."""
    p = Path(workdir) / FAIL_LOG
    with p.open("a") as fh:
        fh.write(f"{_timestamp()}\t{token}\n")


def remove_from_fail(workdir: Path, token: str) -> None:
    """Drop the lines of fail.log whose ID is ``token`` or a name that begins with it
    (``token_1.fastq.gz``); other IDs that merely start with the same characters stay."""
    p = Path(workdir) / FAIL_LOG
    if not p.exists():
        return
    token = token.strip()
    lines = p.read_text(errors="replace").splitlines(keepends=True)
    kept = [ln for ln in lines if not (token and _matches(_field(ln), token))]
    if len(kept) != len(lines):
        p.write_text("".join(kept))
