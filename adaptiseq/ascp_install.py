"""Opt-in install of a current IBM Aspera ``ascp`` (``adaptiseq --install-ascp``).

ENA's Aspera server refuses the ``ascp`` 4.4.2 that the conda package ``aspera-cli`` 4.14.0 ships, and
the ``ascli`` in that package does not start with the Ruby conda resolves today, so it cannot fetch a
newer one. This module fetches the tested one directly: the IBM Aspera Transfer SDK 1.1.9 (``ascp``
4.4.8), from IBM's own download server, plus the public "bypass" key that IBM's open-source ``ascli``
ships (``ascli config ascp install`` makes the same download and writes the same key file).

Nothing is installed without confirmation, nothing is redistributed by adaptiSeq, and every download is
checked against a pinned sha256 before anything is written. The layout is the one ``ascli`` produces,
in ``~/.aspera/sdk``, which adaptiSeq already prefers whenever it is newer than the ``ascp`` on PATH.

Platforms: only those where the pinned SDK build was run against ENA (Linux x86_64; macOS Apple silicon).
The macOS x86_64 build could not be run on the machine available, so Intel Macs are not offered.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import platform
import ssl
import stat
import sys
import tarfile
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Dict, Optional

from .engine import classic
from .errors import PreflightError

SDK_VERSION = "1.1.9"
ASCP_VERSION = (4, 4, 8)           # the tested ascp is 4.4.8.2592 (IBM's catalog says 4.4.7; the binaries say 4.4.8)
CATALOG_URL = "https://ibm.biz/sdk_location"
_BASE = "https://production-transfer-sdk.s3.us-west-2.amazonaws.com/1.1.9/"

# One entry per platform on which the pinned build was run against ENA's Aspera server.
# ``wanted``: member of the archive -> file name in the install directory (a flat layout, as ascli writes it).
PLATFORMS: Dict[str, dict] = {
    "linux-x86_64": dict(
        label="Linux x86_64",
        url=_BASE + "ibm-aspera-transfer-sdk-linux-amd64-1.1.9.tar.gz",
        sha256="97ea42b564d4c4f09202fb2b6525b39d8d1f4f6e4a643671dec0d689bd2098d4",
        size_mb=28,
        kind="tar.gz",
        prefix="ibm-aspera-transfer-sdk-linux-amd64-1.1.9/",
        wanted={"bin/ascp": "ascp", "etc/aspera-license": "aspera-license", "etc/aspera.conf": "aspera.conf",
                "lib/libafwsfeed.so": "libafwsfeed.so", "lib/libstdc++.so.6": "libstdc++.so.6",
                "lib/libstdc++.so.6.0.28": "libstdc++.so.6.0.28"},
    ),
    "osx-arm64": dict(
        label="macOS Apple silicon (arm64)",
        url=_BASE + "ibm-aspera-transfer-sdk-macos-arm64-1.1.9.zip",
        sha256="5101c4cff354b5021b57ca28bd48894254f237b6894e4c9967a0e15a40eda6fa",
        size_mb=26,
        kind="zip",
        prefix="ibm-aspera-transfer-sdk-macos-arm64-1.1.9/",
        wanted={"bin/ascp": "ascp", "etc/aspera-license": "aspera-license", "etc/aspera.conf": "aspera.conf",
                "lib/libafwsfeed.dylib": "libafwsfeed.dylib"},
    ),
}
# The archives hold no keys. IBM's ascli generates them from its data files; the RSA one is the PKCS#1 DER
# in lib/aspera/data/2 of the ascli repository (checked: it gives the file ascli writes, byte for byte).
KEY_URL = "https://raw.githubusercontent.com/IBM/aspera-cli/v4.28.0/lib/aspera/data/2"
KEY_DATA_SHA256 = "0ffb27243d7e77fd2c565a25f910b9dad305750cda96c959be8605b292a8c3d0"
KEY_FILE = "aspera_bypass_rsa.pem"
_REQUIRED = ("ascp", "aspera-license")


class AscpInstallError(PreflightError):
    """The install was refused or failed; nothing was left half installed."""


class _CertificateError(OSError):
    """This Python cannot verify the server's HTTPS certificate and certifi is not installed."""


def platform_key() -> Optional[str]:
    """The key of this machine in ``PLATFORMS`` (``linux-x86_64``, ``osx-arm64``); ``None`` elsewhere."""
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return "linux-x86_64"
    if sys.platform == "darwin" and machine == "arm64":
        return "osx-arm64"
    return None


def _unsupported_message() -> str:
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return ("Intel Macs are not supported by this installer: the macOS x86_64 build of the SDK could not be "
                f"tested (this machine: darwin/{machine})")
    return (f"This installer supports {', '.join(p['label'] for p in PLATFORMS.values())} only "
            f"(this machine: {sys.platform}/{machine})")


def der_to_pem(der: bytes) -> str:
    """The traditional ``RSA PRIVATE KEY`` PEM for a PKCS#1 DER key."""
    body = "\n".join(textwrap.wrap(base64.b64encode(der).decode("ascii"), 64))
    return f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----\n"


def notice(sdk_dir: Path, spec: Optional[dict] = None) -> str:
    spec = spec or PLATFORMS[platform_key() or "linux-x86_64"]
    return (
        f"adaptiseq will install the IBM Aspera Transfer SDK {SDK_VERSION} for {spec['label']} (ascp "
        f"{'.'.join(map(str, ASCP_VERSION))}) so that `-a` works with ENA's Aspera server:\n"
        f"  SDK     : {spec['url']}\n"
        f"            about {spec['size_mb']} MB, checked against sha256 {spec['sha256'][:16]}... "
        f"(IBM's catalog: {CATALOG_URL})\n"
        f"  key     : {KEY_URL}\n"
        f"            the public bypass key IBM's ascli ships, checked against sha256 {KEY_DATA_SHA256[:16]}...\n"
        f"  into    : {sdk_dir} (nothing else on this machine is changed)\n"
        "This is IBM software, fetched from IBM's servers; adaptiSeq does not redistribute it. Its use is governed "
        "by IBM's terms, not by adaptiSeq's MIT licence. IBM's own `ascli config ascp install` downloads the same archive."
    )


def _open(url: str, limit: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "adaptiseq-install-ascp"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read(limit + 1)
    except urllib.error.URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise
    # This Python cannot verify the server's certificate (common with a python.org Python on macOS): use the
    # certifi bundle when it is installed, otherwise say how to fix it. Never fall back to unverified HTTPS.
    try:
        import certifi
    except ImportError:
        raise _CertificateError("this Python cannot verify the server's HTTPS certificate") from None
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        return resp.read(limit + 1)


def _download(url: str, expected_sha256: str, limit: int, what: str) -> bytes:
    """Fetch ``url`` (at most ``limit`` bytes) and refuse it unless its sha256 is the pinned one."""
    try:
        data = _open(url, limit)
    except _CertificateError as exc:
        raise AscpInstallError(
            f"Could not download the {what} from {url}: {exc}",
            "Install certificates for this Python: on macOS with a python.org Python, run 'Install Certificates.command' "
            "from its folder in Applications; otherwise run `pip install certifi` (the installer uses it automatically). "
            "Certificate checking is never turned off") from exc
    except urllib.error.URLError as exc:
        raise AscpInstallError(f"Could not download the {what} from {url}: {exc.reason}",
                               "Check the network connection and try again") from exc
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


def _extract_tar(archive: bytes, spec: dict, into: Path) -> set:
    found = set()
    prefix, wanted = spec["prefix"], spec["wanted"]
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.startswith(prefix):
                continue
            target = wanted.get(member.name[len(prefix):])
            if target is None:
                continue
            if member.issym():
                # a library alias (libstdc++.so.6 -> libstdc++.so.6.0.28): only a plain name beside it is followed
                link = member.linkname
                if "/" in link or link not in wanted.values():
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
    return found


def _extract_zip(archive: bytes, spec: dict, into: Path) -> set:
    found = set()
    prefix, wanted = spec["prefix"], spec["wanted"]
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for info in zf.infolist():
            if not info.filename.startswith(prefix) or info.is_dir():
                continue
            target = wanted.get(info.filename[len(prefix):])
            if target is None:
                continue
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:      # a symlink: not followed
                continue
            (into / target).write_bytes(zf.read(info))
            found.add(target)
    return found


def _extract(archive: bytes, spec: dict, into: Path) -> None:
    """Write only the named members of the SDK archive, as regular files, into ``into``."""
    found = _extract_zip(archive, spec, into) if spec["kind"] == "zip" else _extract_tar(archive, spec, into)
    missing = [n for n in _REQUIRED if n not in found]
    if missing:
        raise AscpInstallError(f"The SDK archive has no {', '.join(missing)}; not installed",
                               "Nothing was changed")


def installed_version(sdk_dir: Path):
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
    key = platform_key()
    if key is None or key not in PLATFORMS:
        raise AscpInstallError(
            _unsupported_message(),
            "Install IBM Aspera Connect or the Aspera CLI for your platform and put its ascp on PATH")
    spec = PLATFORMS[key]

    have = installed_version(sdk_dir)
    if have and have[:3] >= ASCP_VERSION and not force:
        say(f"ascp {'.'.join(map(str, have))} is already installed in {sdk_dir}; nothing to do (--force reinstalls).")
        return sdk_dir / "ascp"

    say(notice(sdk_dir, spec))
    if not assume_yes:
        if confirm is None:
            if not (sys.stdin and sys.stdin.isatty()):
                raise AscpInstallError("Not a terminal, so there is nobody to confirm the install",
                                       "Run `adaptiseq --install-ascp --yes` to confirm it")
            confirm = lambda q: input(q).strip().lower() in ("y", "yes")      # noqa: E731
        if not confirm("Install it? [y/N] "):
            raise AscpInstallError("Not installed: the install was not confirmed", "Nothing was changed")

    archive = sdk_bytes if sdk_bytes is not None else _download(spec["url"], spec["sha256"], 200 * 2**20, "SDK archive")
    key_data = key_bytes if key_bytes is not None else _download(KEY_URL, KEY_DATA_SHA256, 64 * 1024, "key data")
    _verified(archive, spec["sha256"], 200 * 2**20, "SDK archive", spec["url"])
    _verified(key_data, KEY_DATA_SHA256, 64 * 1024, "key data", KEY_URL)

    sdk_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".sdk-install-", dir=str(sdk_dir.parent)))
    backup = None
    try:
        staging.chmod(0o755)
        _extract(archive, spec, staging)
        (staging / KEY_FILE).write_text(der_to_pem(key_data))
        (staging / KEY_FILE).chmod(stat.S_IRUSR | stat.S_IWUSR)
        (staging / "ascp").chmod(0o755)
        version = installed_version(staging)
        if not version or version[:3] < ASCP_VERSION:
            got = ".".join(map(str, version)) or "no version"
            raise AscpInstallError(f"The installed ascp reports {got}, not {'.'.join(map(str, ASCP_VERSION))}; "
                                   "not installed", "Nothing was changed")
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
