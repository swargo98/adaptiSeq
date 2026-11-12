"""Opt-in install of a current IBM Aspera ``ascp`` (``adaptiseq --install-ascp``).

ENA's Aspera server refuses the ``ascp`` 4.4.2 that the conda package ``aspera-cli`` 4.14.0 ships, and
the ``ascli`` in that package does not start with the Ruby conda resolves today, so it cannot fetch a
newer one. This module fetches the tested one directly: the IBM Aspera Transfer SDK 1.1.9 (``ascp``
4.4.8), from IBM's own download server, plus the public "bypass" key that IBM's open-source ``ascli``
ships (``ascli config ascp install`` makes the same download and writes the same key file).

Nothing is installed without confirmation, nothing is redistributed by adaptiSeq, and every download is
checked against a pinned sha256 before anything is written. The layout is the one ``ascli`` produces,
in ``~/.aspera/sdk``, which adaptiSeq already prefers whenever it is newer than the ``ascp`` on PATH.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import platform
import stat
import sys
import tarfile
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Tuple

from .engine import classic
from .errors import PreflightError

SDK_VERSION = "1.1.9"
ASCP_VERSION = (4, 4, 8)           # the tested ascp is 4.4.8.2592
PLATFORM = "linux-x86_64"          # the only platform this was tested on
SDK_URL = ("https://production-transfer-sdk.s3.us-west-2.amazonaws.com/1.1.9/"
           "ibm-aspera-transfer-sdk-linux-amd64-1.1.9.tar.gz")
SDK_SHA256 = "97ea42b564d4c4f09202fb2b6525b39d8d1f4f6e4a643671dec0d689bd2098d4"
SDK_SIZE_MB = 28
CATALOG_URL = "https://ibm.biz/sdk_location"
# The archive holds no keys. IBM's ascli generates them from its data files; the RSA one is the PKCS#1 DER
# in lib/aspera/data/2 of the ascli repository (checked: it gives the file ascli writes, byte for byte).
KEY_URL = "https://raw.githubusercontent.com/IBM/aspera-cli/v4.28.0/lib/aspera/data/2"
KEY_DATA_SHA256 = "0ffb27243d7e77fd2c565a25f910b9dad305750cda96c959be8605b292a8c3d0"
KEY_FILE = "aspera_bypass_rsa.pem"

_ARCHIVE_PREFIX = "ibm-aspera-transfer-sdk-linux-amd64-1.1.9/"
# member of the archive -> file name in the install directory (a flat layout, as ascli writes it)
_WANTED = {"bin/ascp": "ascp", "etc/aspera-license": "aspera-license", "etc/aspera.conf": "aspera.conf",
           "lib/libafwsfeed.so": "libafwsfeed.so", "lib/libstdc++.so.6": "libstdc++.so.6",
           "lib/libstdc++.so.6.0.28": "libstdc++.so.6.0.28"}
_REQUIRED = ("ascp", "aspera-license")


class AscpInstallError(PreflightError):
    """The install was refused or failed; nothing was left half installed."""


def platform_key() -> Optional[str]:
    """``linux-x86_64`` on 64-bit Intel/AMD Linux; ``None`` elsewhere (not tested, so not offered)."""
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return PLATFORM
    return None


def der_to_pem(der: bytes) -> str:
    """The traditional ``RSA PRIVATE KEY`` PEM for a PKCS#1 DER key."""
    body = "\n".join(textwrap.wrap(base64.b64encode(der).decode("ascii"), 64))
    return f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----\n"


def notice(sdk_dir: Path) -> str:
    return (
        f"adaptiseq will install the IBM Aspera Transfer SDK {SDK_VERSION} (ascp "
        f"{'.'.join(map(str, ASCP_VERSION))}) so that `-a` works with ENA's Aspera server:\n"
        f"  SDK     : {SDK_URL}\n"
        f"            about {SDK_SIZE_MB} MB, checked against sha256 {SDK_SHA256[:16]}... (IBM's catalog: {CATALOG_URL})\n"
        f"  key     : {KEY_URL}\n"
        f"            the public bypass key IBM's ascli ships, checked against sha256 {KEY_DATA_SHA256[:16]}...\n"
        f"  into    : {sdk_dir} (nothing else on this machine is changed)\n"
        "This is IBM software, fetched from IBM's servers; adaptiSeq does not redistribute it. Its use is governed "
        "by IBM's terms, not by adaptiSeq's MIT licence. IBM's own `ascli config ascp install` downloads the same archive."
    )


def _download(url: str, expected_sha256: str, limit: int, what: str) -> bytes:
    """Fetch ``url`` (at most ``limit`` bytes) and refuse it unless its sha256 is the pinned one."""
    req = urllib.request.Request(url, headers={"User-Agent": "adaptiseq-install-ascp"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read(limit + 1)
    except OSError as exc:
        raise AscpInstallError(f"Could not download the {what} from {url}: {exc}",
                               "Check the network connection and try again") from exc
    return _verified(data, expected_sha256, limit, what, url)


def _verified(data: bytes, expected_sha256: str, limit: int, what: str, url: str) -> bytes:
    if len(data) > limit:
        raise AscpInstallError(f"The {what} from {url} is larger than expected ({limit} bytes); not installed",
                               "Nothing was changed")
    got = hashlib.sha256(data).hexdigest()
    if got != expected_sha256:
        raise AscpInstallError(
            f"The {what} from {url} does not match the pinned checksum (got {got[:16]}..., expected "
            f"{expected_sha256[:16]}...); not installed",
            "Nothing was changed. IBM may have replaced the file: report it at "
            "https://github.com/swargo98/adaptiSeq/issues")
    return data


def _extract(archive: bytes, into: Path) -> None:
    """Write only the named members of the SDK archive, as regular files, into ``into``."""
    found = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.startswith(_ARCHIVE_PREFIX):
                continue
            target = _WANTED.get(member.name[len(_ARCHIVE_PREFIX):])
            if target is None:
                continue
            if member.issym():
                # a library alias (libstdc++.so.6 -> libstdc++.so.6.0.28): only a plain name beside it is followed
                link = member.linkname
                if "/" in link or link not in _WANTED.values():
                    continue
                (into / target).symlink_to(link)
                found.add(target)
                continue
            if not member.isfile():
                continue
            src = tar.extractfile(member)
            if src is None:
                continue
            (into / target).write_bytes(src.read())
            found.add(target)
    missing = [n for n in _REQUIRED if n not in found]
    if missing:
        raise AscpInstallError(f"The SDK archive has no {', '.join(missing)}; not installed",
                               "Nothing was changed")


def installed_version(sdk_dir: Path) -> Tuple[int, ...]:
    exe = Path(sdk_dir) / "ascp"
    return classic.ascp_version(str(exe)) if exe.is_file() and os.access(exe, os.X_OK) else ()


def install_ascp(
    *,
    assume_yes: bool = False,
    sdk_dir: Optional[Path] = None,
    force: bool = False,
    say: Callable[[str], None] = print,
    confirm: Optional[Callable[[str], bool]] = None,
    sdk_bytes: Optional[bytes] = None,
    key_bytes: Optional[bytes] = None,
) -> Path:
    """Install the pinned IBM Aspera Transfer SDK into ``sdk_dir`` (default ``~/.aspera/sdk``) and return
    the path of its ``ascp``. Asks first (``assume_yes=True`` answers yes); with no terminal and no
    ``assume_yes`` it refuses. ``sdk_bytes`` and ``key_bytes`` replace the downloads (for tests); they are
    still checked against the pinned checksums."""
    sdk_dir = Path(sdk_dir) if sdk_dir is not None else classic.SDK_DIR
    if platform_key() != PLATFORM:
        raise AscpInstallError(
            f"This installer supports {PLATFORM} only (this machine: {sys.platform}/{platform.machine()})",
            "Install IBM Aspera Connect or the Aspera CLI for your platform and put its ascp on PATH")

    have = installed_version(sdk_dir)
    if have and have[:3] >= ASCP_VERSION and not force:
        say(f"ascp {'.'.join(map(str, have))} is already installed in {sdk_dir}; nothing to do (--force reinstalls).")
        return sdk_dir / "ascp"

    say(notice(sdk_dir))
    if not assume_yes:
        if confirm is None:
            if not (sys.stdin and sys.stdin.isatty()):
                raise AscpInstallError("Not a terminal, so there is nobody to confirm the install",
                                       "Run `adaptiseq --install-ascp --yes` to confirm it")
            confirm = lambda q: input(q).strip().lower() in ("y", "yes")      # noqa: E731
        if not confirm("Install it? [y/N] "):
            raise AscpInstallError("Not installed: the install was not confirmed", "Nothing was changed")

    archive = sdk_bytes if sdk_bytes is not None else _download(SDK_URL, SDK_SHA256, 200 * 2**20, "SDK archive")
    key_data = key_bytes if key_bytes is not None else _download(KEY_URL, KEY_DATA_SHA256, 64 * 1024, "key data")
    _verified(archive, SDK_SHA256, 200 * 2**20, "SDK archive", SDK_URL)
    _verified(key_data, KEY_DATA_SHA256, 64 * 1024, "key data", KEY_URL)

    sdk_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".sdk-install-", dir=str(sdk_dir.parent)))
    try:
        staging.chmod(0o755)
        _extract(archive, staging)
        (staging / KEY_FILE).write_text(der_to_pem(key_data))
        (staging / KEY_FILE).chmod(stat.S_IRUSR | stat.S_IWUSR)
        (staging / "ascp").chmod(0o755)
        version = installed_version(staging)
        if not version or version[:3] < ASCP_VERSION:
            got = ".".join(map(str, version)) or "no version"
            raise AscpInstallError(f"The installed ascp reports {got}, not {'.'.join(map(str, ASCP_VERSION))}; "
                                   "not installed", "Nothing was changed")
        backup = None
        if sdk_dir.exists():
            backup = sdk_dir.with_name(f"{sdk_dir.name}.old.{time.strftime('%Y%m%d%H%M%S')}")
            os.replace(sdk_dir, backup)
        os.replace(staging, sdk_dir)
        staging = None
    finally:
        if staging is not None:
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
    classic._ascp_versions.clear()
    if backup is not None:
        say(f"The previous {sdk_dir.name} directory was kept as {backup}.")
    say(f"Installed ascp {'.'.join(map(str, installed_version(sdk_dir)))} in {sdk_dir}. adaptiSeq uses it for `-a` "
        "whenever it is newer than the ascp on PATH.")
    return sdk_dir / "ascp"
