"""Opt-in LIVE real-Aspera test (Part 6).

Runs a genuine IBM ``ascp`` against the real ENA Aspera endpoint and md5-verifies the
result. Skips unless ALL of:

* ``ADAPTISEQ_LIVE_ASPERA=1`` is set (explicit opt-in — it does a real network
  transfer), and
* the network is up (and ``ADAPTISEQ_NO_NETWORK`` is unset), and
* a *real* ``ascp`` is on PATH (``ascp --version`` reports an IBM build, not the
  benchmark no-op stub), and
* the ENA Aspera key is discoverable (``find_ena_aspera_key()``).

Provision a real IBM ``ascp`` and the ENA Aspera key on PATH first. This test never
runs in normal/offline CI.
"""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess

import pytest

from adaptiseq.engine.classic import ClassicEngine, find_ena_aspera_key
from adaptiseq.options import Options


# A tiny, stable ENA single-end run (≈ 51 KB) with a known md5.
ACC_PATH = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR229/057/SRR22904257/SRR22904257.fastq.gz"
EXPECTED_MD5 = "bfa437e8a76bd5aab426eb3e5bef4cb6"


def _real_ascp() -> bool:
    if shutil.which("ascp") is None:
        return False
    try:
        out = subprocess.run(["ascp", "--version"], capture_output=True, text=True,
                             timeout=15).stdout.lower()
    except Exception:
        return False
    return "ascp version" in out  # the no-op stub prints no such line


pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("ADAPTISEQ_LIVE_ASPERA") == "1"
        and not os.environ.get("ADAPTISEQ_NO_NETWORK")
        and _real_ascp()
        and find_ena_aspera_key() is not None
    ),
    reason="live aspera opt-in: set ADAPTISEQ_LIVE_ASPERA=1 with a real ascp + ENA key",
)


def _md5(path) -> str:
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def test_real_ena_aspera_single_file_md5(tmp_path):
    opts = Options(aspera=True, speed=100, quiet=True)
    engine = ClassicEngine(opts, tmp_path)
    ok = engine.fetch_aspera(ACC_PATH, "ENA")
    assert ok, "real ascp transfer returned non-zero"
    out = tmp_path / "SRR22904257.fastq.gz"
    assert out.is_file() and out.stat().st_size > 0
    assert _md5(out) == EXPECTED_MD5
