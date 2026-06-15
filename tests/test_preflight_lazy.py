"""Needs-based preflight: a tool that is only required on a *fallback* path must
surface a clean PreflightError at the point it is actually needed — not a bare
FileNotFoundError, and not a misleading 'not available in all databases' message.

These lock in the fix for the release-blocker review: srapath (SRA URL
resolution) and fasterq-dump (.sra -> FASTQ conversion) are not required for a
pure-ENA .fastq.gz run, so they are checked lazily rather than up front.
"""

from __future__ import annotations

import importlib

import pytest

from adaptiseq import convert
from adaptiseq.console import NullReporter
from adaptiseq.errors import AdaptiSeqError, PreflightError
from adaptiseq.options import Options, RunContext

R = importlib.import_module("adaptiseq.resolve")


def _hide(monkeypatch, *missing):
    """Make shutil.which report the named tools as absent (others unchanged)."""
    import shutil

    real = shutil.which

    def fake(name, *a, **k):
        return None if name in missing else real(name, *a, **k)

    # check_software uses shutil.which via the preflight module namespace.
    monkeypatch.setattr("adaptiseq.preflight.shutil.which", fake)


def test_srapath_missing_raises_preflight(monkeypatch):
    _hide(monkeypatch, "srapath")
    with pytest.raises(PreflightError) as exc:
        R._srapath("SRR000001")
    assert "srapath" in exc.value.message
    assert isinstance(exc.value, AdaptiSeqError)  # caught by the CLI's handler


def test_srapath_present_resolves_normally(monkeypatch):
    # When srapath exists, _srapath must not raise from the preflight guard; it
    # returns whatever the tool prints (empty string here, since the accession is
    # bogus) without inventing a PreflightError.
    monkeypatch.setattr(R.subprocess, "run",
                        lambda *a, **k: type("P", (), {"stdout": "https://x/y\n"})())
    assert R._srapath("SRR000001") == "https://x/y"


def test_convert_missing_fasterq_dump_raises_preflight(monkeypatch, tmp_path):
    # A .sra file present + a conversion trigger (-g) but no fasterq-dump must
    # raise a clean PreflightError instead of a subprocess FileNotFoundError.
    (tmp_path / "SRR000001.metadata.tsv").write_text("run\tx\nSRR000001\ty\n")
    (tmp_path / "SRR000001").write_bytes(b"not-a-real-sra")
    ctx = RunContext(
        options=Options(gzip=True),
        reporter=NullReporter(),
        workdir=tmp_path,
    )
    ctx.accession = "SRR000001"
    _hide(monkeypatch, "fasterq-dump")
    with pytest.raises(PreflightError) as exc:
        convert.maybe_convert(ctx, "SRR000001")
    assert "fasterq-dump" in exc.value.message
