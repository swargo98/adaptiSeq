"""Shared pytest fixtures and helpers."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _online(host: str = "www.ebi.ac.uk", port: int = 443, timeout: float = 3.0) -> bool:
    if os.environ.get("ADAPTISEQ_NO_NETWORK"):
        return False
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def online() -> bool:
    return _online()


@pytest.fixture
def seeded_workdir(tmp_path):
    """Return a factory that copies a fixture metadata file into a temp workdir."""

    def _seed(fixture_rel: str, dest_name: str) -> Path:
        src = FIXTURES / fixture_rel
        dest = tmp_path / dest_name
        dest.write_bytes(src.read_bytes())
        return tmp_path

    return _seed
