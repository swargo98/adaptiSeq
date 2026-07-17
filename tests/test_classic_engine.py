"""ENA Aspera key discovery for the classic engine.

Real installs put the ENA key in several places depending on how ascp was
installed (IBM Connect vs conda aspera-cli vs a hand-copied key); these pin the
search order and the error message when nothing is found.
"""

import pytest

from adaptiseq.engine.classic import (
    ena_aspera_key_candidates,
    find_ena_aspera_key,
)


def _fake_ascp(monkeypatch, path):
    monkeypatch.setattr("adaptiseq.engine.classic._which", lambda name: str(path))


def test_finds_key_in_ibm_connect_layout(tmp_path, monkeypatch):
    # ascp in bin/, key under ../etc/aspera/ — the layout supported before.
    bin_dir = tmp_path / "env" / "bin"
    etc_dir = tmp_path / "env" / "etc" / "aspera"
    bin_dir.mkdir(parents=True)
    etc_dir.mkdir(parents=True)
    (bin_dir / "ascp").write_text("")
    key = etc_dir / "aspera_bypass_rsa.pem"
    key.write_text("key")

    _fake_ascp(monkeypatch, bin_dir / "ascp")

    assert find_ena_aspera_key() is not None
    assert find_ena_aspera_key().resolve() == key.resolve()


def test_finds_tokenauth_key_under_etc(tmp_path, monkeypatch):
    bin_dir = tmp_path / "env" / "bin"
    etc_dir = tmp_path / "env" / "etc"
    bin_dir.mkdir(parents=True)
    etc_dir.mkdir(parents=True)
    (bin_dir / "ascp").write_text("")
    key = etc_dir / "aspera_tokenauth_id_rsa"
    key.write_text("key")

    _fake_ascp(monkeypatch, bin_dir / "ascp")

    assert find_ena_aspera_key().resolve() == key.resolve()


def test_finds_key_beside_ascp_in_conda_layout(tmp_path, monkeypatch):
    # conda aspera-cli can ship ascp and its key in the same directory — this
    # layout was previously missed entirely.
    aspera_dir = tmp_path / "env" / "etc" / "aspera"
    aspera_dir.mkdir(parents=True)
    (aspera_dir / "ascp").write_text("")
    key = aspera_dir / "aspera_bypass_rsa.pem"
    key.write_text("key")

    _fake_ascp(monkeypatch, aspera_dir / "ascp")

    assert find_ena_aspera_key().resolve() == key.resolve()


def test_finds_hand_copied_key_in_home_aspera(tmp_path, monkeypatch):
    home = tmp_path / "home"
    aspera = home / ".aspera"
    aspera.mkdir(parents=True)
    key = aspera / "aspera_bypass_rsa.pem"
    key.write_text("key")
    bin_dir = tmp_path / "elsewhere" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ascp").write_text("")

    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: home))
    _fake_ascp(monkeypatch, bin_dir / "ascp")

    assert find_ena_aspera_key().resolve() == key.resolve()


def test_bypass_key_wins_over_tokenauth_in_same_dir(tmp_path, monkeypatch):
    etc_dir = tmp_path / "env" / "etc" / "aspera"
    bin_dir = tmp_path / "env" / "bin"
    etc_dir.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    (bin_dir / "ascp").write_text("")
    bypass = etc_dir / "aspera_bypass_rsa.pem"
    bypass.write_text("bypass")
    (tmp_path / "env" / "etc" / "aspera_tokenauth_id_rsa").write_text("token")

    _fake_ascp(monkeypatch, bin_dir / "ascp")

    assert find_ena_aspera_key().resolve() == bypass.resolve()


def test_returns_none_when_no_key_exists(tmp_path, monkeypatch):
    bin_dir = tmp_path / "env" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ascp").write_text("")

    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path / "home"))
    _fake_ascp(monkeypatch, bin_dir / "ascp")

    assert find_ena_aspera_key() is None


def test_returns_none_when_ascp_is_absent(monkeypatch):
    monkeypatch.setattr("adaptiseq.engine.classic._which", lambda name: None)

    assert find_ena_aspera_key() is None
    assert ena_aspera_key_candidates() == ()


def test_candidates_are_unique_and_cover_every_searched_layout(tmp_path, monkeypatch):
    bin_dir = tmp_path / "env" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ascp").write_text("")
    _fake_ascp(monkeypatch, bin_dir / "ascp")

    candidates = ena_aspera_key_candidates()
    rendered = [str(c) for c in candidates]

    assert len(rendered) == len(set(rendered))       # no duplicate paths tried
    assert all(c is not None for c in candidates)    # no None placeholders
    assert any("etc/aspera/aspera_bypass_rsa.pem" in c for c in rendered)
    assert any(".aspera" in c for c in rendered)


def test_missing_key_error_lists_every_candidate_path(tmp_path, monkeypatch):
    from adaptiseq.engine.classic import ClassicEngine
    from adaptiseq.errors import PreflightError
    from adaptiseq.options import Options

    bin_dir = tmp_path / "env" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ascp").write_text("")
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path / "home"))
    _fake_ascp(monkeypatch, bin_dir / "ascp")

    engine = ClassicEngine(Options(engine="classic", quiet=True), tmp_path)

    with pytest.raises(PreflightError) as excinfo:
        engine.fetch_aspera("ftp.sra.ebi.ac.uk/vol1/fastq/a.fastq.gz", "ENA")

    message = str(excinfo.value)
    assert "aspera_bypass_rsa.pem" in message
    assert " OR " in message
    assert "None" not in message  # the old (None, None) placeholder is gone
