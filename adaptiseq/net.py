"""Thin ``wget`` wrappers used for all metadata / discovery network I/O.

Every metadata file, GEO lookup, GSA search, key file, and md5 list in iseq is
fetched by shelling to ``wget`` with specific flags, user-agents, and POST
bodies. To guarantee byte-for-byte parity (acceptance criterion 3) adaptiSeq
issues the *same* ``wget`` invocations rather than reimplementing the HTTP. This
keeps ``requests`` out of the hard dependency set as the spec allows.

Sequence-data bytes do **not** go through here — those go through the engine
seam (``engine/classic.py``), which is the single place Part 2 replaces.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

USER_AGENT_MOZILLA = "Mozilla/5.0"


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _throttle(url: str) -> None:
    """Consult the per-endpoint resolution rate limiters (no-op unless active)."""
    try:
        from . import ratelimits

        ratelimits.throttle(url)
    except Exception:
        pass


def wget_to_file(
    url: str,
    out_path,
    *,
    user_agent: Optional[str] = None,
    post_data: Optional[str] = None,
    cont: bool = False,
    quiet: bool = True,
) -> int:
    """Download ``url`` to ``out_path``.

    ``--quiet`` is the norm for metadata. Returns wget's exit code (the caller
    decides what an empty file means, inspecting the file afterwards rather than
    relying on wget's status).
    """
    _throttle(url)
    cmd = ["wget"]
    if cont:
        cmd.append("-c")
    if user_agent:
        cmd.append(f"--user-agent={user_agent}")
    if post_data is not None:
        cmd.append(f"--post-data={post_data}")
    if quiet:
        cmd.append("--quiet")
    cmd += [url, "-O", str(out_path)]
    return _run(cmd).returncode


def wget_capture(url: str, *, user_agent: Optional[str] = None) -> str:
    """Equivalent of ``wget -qO- URL`` — return the body as text."""
    _throttle(url)
    cmd = ["wget", "-qO-"]
    if user_agent:
        cmd.append(f"--user-agent={user_agent}")
    cmd.append(url)
    return _run(cmd).stdout


def wget_spider_size(url: str, *, ftp: bool, user_agent: Optional[str] = None) -> str:
    """Reproduce iseq's ``File size:`` probe.

    iseq runs, verbatim::

        wget [--user-agent=..] --spider URL 2>&1 | grep Length \\
            | awk '{printf "%.2fG", ($2/1024/1024/1024)}'   # https
        wget [--user-agent=..] --spider URL 2>&1 | grep SIZE  \\
            | awk '{printf "%.2fG", ($5/1024/1024/1024)}'    # ftp

    To match byte-for-byte we run the identical shell pipeline. This is purely
    the cosmetic size string; the actual download is independent.
    """
    ua = f'--user-agent="{user_agent}" ' if user_agent else ""
    if ftp:
        pipeline = (
            f"wget {ua}--spider \"{url}\" 2>&1 | grep SIZE "
            "| awk '{printf \"%.2fG\", ($5/1024/1024/1024)}'"
        )
    else:
        pipeline = (
            f"wget {ua}--spider \"{url}\" 2>&1 | grep Length "
            "| awk '{printf \"%.2fG\", ($2/1024/1024/1024)}'"
        )
    result = subprocess.run(["bash", "-c", pipeline], capture_output=True, text=True)
    return result.stdout.strip()


def file_nonempty(path) -> bool:
    p = Path(path)
    return p.exists() and p.stat().st_size > 0
