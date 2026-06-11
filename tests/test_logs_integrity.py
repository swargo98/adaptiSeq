"""Logs + integrity (md5) policy parity, offline with synthetic files."""

import hashlib
from pathlib import Path

from adaptiseq import integrity, logs
from adaptiseq.console import NullReporter
from adaptiseq.options import Options, RunContext


def _ctx(tmp_path, **opts):
    return RunContext(
        options=Options(**opts), reporter=NullReporter(), workdir=tmp_path
    )


# --------------------------------- logs ----------------------------------------

def test_success_log_roundtrip_and_skip(tmp_path):
    logs.ensure_success_log(tmp_path)
    assert logs.in_success(tmp_path, "SRR1") is False
    logs.mark_success(tmp_path, "SRR1")
    assert logs.in_success(tmp_path, "SRR1") is True
    line = (tmp_path / "success.log").read_text().strip()
    assert line.split("\t")[1] == "SRR1"


def test_mark_success_removes_from_fail(tmp_path):
    logs.mark_fail(tmp_path, "SRR9")
    assert "SRR9" in (tmp_path / "fail.log").read_text()
    logs.mark_success(tmp_path, "SRR9")
    assert "SRR9" not in (tmp_path / "fail.log").read_text()


# ------------------------------ checkSRA (gzip) --------------------------------

def _md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def test_gzip_md5_success(tmp_path):
    content = b"fake fastq gz payload"
    (tmp_path / "SRR0000001.fastq.gz").write_bytes(content)
    digest = _md5(content)
    # The metadata row must carry the fastq filename (as the real fastq_ftp path
    # does) so checkSRA can enumerate the files to md5-check.
    (tmp_path / "SRR0000001.metadata.tsv").write_text(
        "run_accession\tfastq_md5\tlibrary_layout\tfastq_ftp\n"
        f"SRR0000001\t{digest}\tSINGLE\t"
        "ftp.sra.ebi.ac.uk/vol1/fastq/SRR000/SRR0000001/SRR0000001.fastq.gz\n"
    )
    ctx = _ctx(tmp_path, gzip=True, database="ena")
    ctx.accession = "SRR0000001"
    ctx.database = "ena"

    calls = []
    ok = integrity.check_sra(ctx, "SRR0000001", lambda: calls.append(1))
    assert ok is True
    assert calls == []  # no re-download on first-try success
    assert logs.in_success(tmp_path, "SRR0000001")


def test_gzip_md5_failure_after_retries(tmp_path):
    (tmp_path / "SRR0000002.fastq.gz").write_bytes(b"wrong payload")
    (tmp_path / "SRR0000002.metadata.tsv").write_text(
        "run_accession\tfastq_md5\tlibrary_layout\tfastq_ftp\n"
        "SRR0000002\tdeadbeefdeadbeefdeadbeefdeadbeef\tSINGLE\t"
        "ftp.sra.ebi.ac.uk/vol1/fastq/SRR000/SRR0000002/SRR0000002.fastq.gz\n"
    )
    ctx = _ctx(tmp_path, gzip=True, database="ena")
    ctx.accession = "SRR0000002"
    ctx.database = "ena"

    ok = integrity.check_sra(ctx, "SRR0000002", lambda: None)  # noop redownload
    assert ok is False
    assert ctx.failed is True
    assert "SRR0000002" in (tmp_path / "fail.log").read_text()
