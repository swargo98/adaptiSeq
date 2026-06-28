"""The classic ``wget``/``axel`` download engine and the ``ascp`` aspera path.

Faithful port of ``executeDownload`` and ``executeAspera``. This module is the
single seam through which sequence-data bytes are fetched (Section 5.1). The
public surface is intentionally tiny:

* :meth:`ClassicEngine.fetch(url, save_path) -> bool` — the seam Part 2 replaces.
* :meth:`ClassicEngine.fetch_aspera(link, db, save_path=None) -> bool` — the ascp
  path (unchanged by Part 2's HTTP/FTP segmented engine).

Returns ``True`` when the transfer command exits 0. As in the Bash, *success* of
a Run is ultimately decided by the integrity check, not by this return value.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from ..console import green, green_bold, red_bold, Reporter, NullReporter
from ..errors import PreflightError
from ..net import USER_AGENT_MOZILLA, wget_to_file

GSA_ASPERA_KEY = ".asperaGSA.openssh"
GSA_ASPERA_KEY_URL = (
    "https://ngdc.cncb.ac.cn/gsa/file/downFile?fileName=download/aspera01.openssh"
)


def _wget_supports_show_progress() -> bool:
    """Port of the ``wget_version < 1.16`` test in ``executeDownload``."""
    try:
        out = subprocess.run(
            ["wget", "--version"], capture_output=True, text=True
        ).stdout
    except FileNotFoundError:
        return True
    first = out.splitlines()[0] if out else ""
    parts = first.split()
    version = parts[2] if len(parts) >= 3 else "0"
    m = re.match(r"(\d+)\.(\d+)", version)
    if not m:
        return True
    major, minor = int(m.group(1)), int(m.group(2))
    return (major, minor) >= (1, 16)


def _ena_aspera_key_candidates(ascp: str) -> tuple:
    base = Path(ascp).resolve().parent
    candidates = [
        # Conda aspera-cli can place ascp and keys together in env/etc/aspera.
        base / "aspera_bypass_rsa.pem",
        base / "aspera_tokenauth_id_rsa",
        # IBM Aspera Connect usually puts ascp in bin and keys under ../etc.
        base / ".." / "etc" / "aspera" / "aspera_bypass_rsa.pem",
        base / ".." / "etc" / "aspera_tokenauth_id_rsa",
        Path.home() / ".aspera" / "aspera_bypass_rsa.pem",
        Path.home() / ".aspera" / "aspera_tokenauth_id_rsa",
    ]
    unique = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return tuple(unique)


def find_ena_aspera_key() -> Optional[Path]:
    """Locate the ENA ascp key relative to the ``ascp`` binary (executeAspera)."""
    ascp = _which("ascp")
    if ascp is None:
        return None
    for candidate in _ena_aspera_key_candidates(ascp):
        if candidate.is_file():
            return candidate.resolve()
    return None


def ena_aspera_key_candidates() -> tuple:
    ascp = _which("ascp")
    if ascp is None:
        return ()
    return _ena_aspera_key_candidates(ascp)


def _which(name: str) -> Optional[str]:
    import shutil

    return shutil.which(name)


class ClassicEngine:
    """``wget``/``axel`` + ``ascp`` transport, configured from :class:`Options`."""

    name = "classic"

    def __init__(self, options, workdir: Path, reporter: Optional[Reporter] = None):
        self.options = options
        self.workdir = Path(workdir)
        self.reporter = reporter or NullReporter()

    # --- the seam ---------------------------------------------------------------
    def fetch(self, url: str, save_path: str) -> bool:
        """Download ``url`` to ``save_path`` (relative to workdir) via wget/axel.

        Mirrors ``executeDownload``: ``axel -n P`` when ``-p`` is set, else
        ``wget -c --limit-rate``. Progress flags follow the same quiet/version
        rules.
        """
        opts = self.options
        quiet = opts.quiet

        if opts.parallel > 0:
            max_speed = opts.speed * 1024 * 1024
            cmd = [
                "axel",
                "-n", str(opts.parallel),
                "-o", save_path,
                "-a",
                "-c",
                url,
                "-s", str(max_speed),
            ]
            if quiet:
                return self._run(cmd, discard=True) == 0
            self.reporter.info(
                f"{green('Note')}: Classic engine using axel parallel download "
                f"with {opts.parallel} connection(s) (-n {opts.parallel}), "
                f"resume enabled (-c), speed cap {opts.speed} MB/s, output {save_path}"
            )
            self.reporter.info(
                f"{green('Note')}: Axel may reuse connection numbers while retrying "
                "byte ranges; final md5 validation determines file integrity"
            )
            rc = self._run(cmd)
            if rc == 0:
                self.reporter.info(
                    f"{green('Note')}: Axel process completed for {save_path}; "
                    "starting integrity validation"
                )
                return True
            self.reporter.error(
                f"{red_bold('Error')}: Axel exited with code {rc} for {save_path}"
            )
            return False

        # wget path
        if quiet:
            wget_params = ["--quiet"]
        elif _wget_supports_show_progress():
            wget_params = ["--quiet", "--show-progress"]
        else:
            wget_params = ["--progress=bar"]
        cmd = ["wget", "-c", url, "-O", save_path] + wget_params + [
            f"--limit-rate={opts.speed}M"
        ]
        return self._run(cmd) == 0

    # --- aspera (ascp) ----------------------------------------------------------
    def fetch_aspera(self, link: str, db: str, save_path: Optional[str] = None) -> bool:
        """Port of ``executeAspera`` for ``db`` in {ENA, GSA}."""
        opts = self.options
        if db == "ENA":
            key = find_ena_aspera_key()
            if key is None:
                candidates = " OR ".join(str(c) for c in ena_aspera_key_candidates())
                raise PreflightError(
                    f"Aspera key file not found in the path: {candidates}",
                    "Please copy the Aspera key file in the above path and rename it",
                )
            aspera_link = link.replace(
                "ftp.sra.ebi.ac.uk/", "era-fasp@fasp.sra.ebi.ac.uk:"
            )
            key_file = str(key)
        elif db == "GSA":
            key_file = self._ensure_gsa_key()
            aspera_link = link.replace(
                "ftp://download.big.ac.cn/", "aspera01@download.cncb.ac.cn:"
            )
        else:  # pragma: no cover
            raise ValueError(f"Unknown aspera db: {db}")

        cmd = ["ascp"]
        if opts.quiet:
            cmd.append("-q")
        cmd += [
            "-P", "33001",
            "-i", key_file,
            "-QT",
            "-l", f"{opts.speed}M",
            "-k1",
            "-d", aspera_link,
            ".",
        ]
        return self._run(cmd) == 0

    def _ensure_gsa_key(self) -> str:
        key = self.workdir / GSA_ASPERA_KEY
        if not key.is_file():
            wget_to_file(
                GSA_ASPERA_KEY_URL,
                key,
                user_agent=USER_AGENT_MOZILLA,
                quiet=True,
            )
        if not key.is_file():
            raise PreflightError(
                f"{GSA_ASPERA_KEY} is not exist",
                "Please download GSA Aspera key file from "
                f"{GSA_ASPERA_KEY_URL} and rename it to {GSA_ASPERA_KEY}",
            )
        return GSA_ASPERA_KEY

    def _run(self, cmd, discard: bool = False) -> int:
        stdout = subprocess.DEVNULL if discard else None
        stderr = subprocess.DEVNULL if discard else None
        return subprocess.run(
            cmd, cwd=str(self.workdir), stdout=stdout, stderr=stderr
        ).returncode


def get_engine(options, workdir, reporter=None):
    """Engine factory.

    Part 2: ``--engine segmented`` (the default) returns the segmented engine,
    which itself falls back to the classic ``wget``/``axel`` path per-download
    when a host cannot serve ranges. ``--engine classic`` returns the Part 1
    engine unchanged.
    """
    if getattr(options, "engine", "segmented") == "segmented":
        from .seam import SegmentedEngine  # local import to avoid a cycle

        return SegmentedEngine(options, workdir, reporter)
    return ClassicEngine(options, workdir, reporter)
