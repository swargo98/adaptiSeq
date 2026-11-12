"""Which ascp runs: the one on PATH, unless the Transfer SDK in ~/.aspera/sdk is newer; and a
failed ENA transfer says what ascp it ran and how to get a current one. (ENA's Aspera server
refuses ascp 4.4.2, the one inside conda's aspera-cli 4.14.0; 4.4.8 transfers.)"""
import os
import stat

import pytest

from adaptiseq.engine import classic
from adaptiseq.engine.classic import ClassicEngine, ascp_path, ascp_version, find_ena_aspera_key
from adaptiseq.options import Options


def _fake_ascp(directory, version_line, exit_code=0, key=True):
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / "ascp"
    p.write_text(f"#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo '{version_line}'; exit 0; fi\nexit {exit_code}\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    if key:
        (directory / "aspera_bypass_rsa.pem").write_text("key")
    return str(p)


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    sdk = tmp_path / "sdk"
    monkeypatch.setattr(classic, "SDK_DIR", sdk)
    return tmp_path / "onpath", sdk


def _on_path(monkeypatch, path):
    monkeypatch.setattr(classic, "_which", lambda name: path)


def test_version_is_parsed(tmp_path):
    p = _fake_ascp(tmp_path, "ascp version 4.4.8.2592 6a5e6bf")
    assert ascp_version(p) == (4, 4, 8, 2592)
    assert ascp_version(str(tmp_path / "missing")) == ()


def test_no_ascp_anywhere(dirs, monkeypatch):
    _on_path(monkeypatch, None)
    assert ascp_path() is None
    assert find_ena_aspera_key() is None


def test_sdk_is_used_when_nothing_is_on_path(dirs, monkeypatch):
    _, sdk = dirs
    exe = _fake_ascp(sdk, "ascp version 4.4.8.2592 x")
    _on_path(monkeypatch, None)
    assert ascp_path() == exe
    assert find_ena_aspera_key().resolve() == (sdk / "aspera_bypass_rsa.pem").resolve()


def test_newer_sdk_beats_older_ascp_on_path(dirs, monkeypatch):
    onpath, sdk = dirs
    old = _fake_ascp(onpath, "ascp version 4.4.2.550 x")
    new = _fake_ascp(sdk, "ascp version 4.4.8.2592 x")
    _on_path(monkeypatch, old)
    assert ascp_path() == new
    assert find_ena_aspera_key().resolve() == (sdk / "aspera_bypass_rsa.pem").resolve()


def test_path_ascp_wins_when_it_is_as_new_or_newer(dirs, monkeypatch):
    onpath, sdk = dirs
    newer = _fake_ascp(onpath, "ascp version 4.5.0.1 x")
    _fake_ascp(sdk, "ascp version 4.4.8.2592 x")
    _on_path(monkeypatch, newer)
    assert ascp_path() == newer


def test_path_ascp_wins_when_a_version_cannot_be_read(dirs, monkeypatch):
    onpath, sdk = dirs
    stub = _fake_ascp(onpath, "no version here")            # a no-op stub prints no 'ascp version' line
    _fake_ascp(sdk, "ascp version 4.4.8.2592 x")
    _on_path(monkeypatch, stub)
    assert ascp_path() == stub


def test_failed_ena_transfer_explains_old_ascp_once(dirs, monkeypatch, tmp_path):
    onpath, sdk = dirs
    exe = _fake_ascp(onpath, "ascp version 4.4.2.550 x", exit_code=1)
    _on_path(monkeypatch, exe)

    class Rec:
        def __init__(self): self.lines = []
        def info(self, msg): self.lines.append(msg)
        def __getattr__(self, name): return lambda *a, **k: None

    rec = Rec()
    engine = ClassicEngine(Options(aspera=True, speed=100, quiet=True), tmp_path, rec)
    assert engine.fetch_aspera("ftp.sra.ebi.ac.uk/vol1/fastq/a.fastq.gz", "ENA") is False
    assert engine.fetch_aspera("ftp.sra.ebi.ac.uk/vol1/fastq/b.fastq.gz", "ENA") is False
    hints = [m for m in rec.lines if "adaptiseq --install-ascp" in m]
    assert len(hints) == 1 and "4.4.2.550" in hints[0] and exe in hints[0]


def test_successful_transfer_prints_no_hint_and_runs_the_chosen_binary(dirs, monkeypatch, tmp_path):
    onpath, sdk = dirs
    old = _fake_ascp(onpath, "ascp version 4.4.2.550 x", exit_code=1)
    new = _fake_ascp(sdk, "ascp version 4.4.8.2592 x", exit_code=0)
    _on_path(monkeypatch, old)

    class Rec:
        lines = []
        def info(self, msg): self.lines.append(msg)
        def __getattr__(self, name): return lambda *a, **k: None

    engine = ClassicEngine(Options(aspera=True, speed=100, quiet=True), tmp_path, Rec())
    assert engine.fetch_aspera("ftp.sra.ebi.ac.uk/vol1/fastq/a.fastq.gz", "ENA") is True   # the SDK binary exits 0
    assert not Rec.lines
