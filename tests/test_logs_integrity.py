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


def test_gzip_md5_mismatch_first_retry_is_a_fresh_download(tmp_path):
    # Regression: the first retry used to call the download with the bad file
    # still in place; the engine skips a full-size file, so only the second
    # retry actually re-downloaded.
    good = b"good payload"
    f = tmp_path / "SRR0000006.fastq.gz"
    f.write_bytes(b"same size, wrong bytes")
    (tmp_path / "SRR0000006.metadata.tsv").write_text(
        "run_accession\tfastq_md5\tlibrary_layout\tfastq_ftp\n"
        f"SRR0000006\t{_md5(good)}\tSINGLE\t"
        "ftp.sra.ebi.ac.uk/vol1/fastq/SRR000/SRR0000006/SRR0000006.fastq.gz\n"
    )
    ctx = _ctx(tmp_path, gzip=True, database="ena")
    ctx.accession = "SRR0000006"
    ctx.database = "ena"

    calls = []

    def redownload():
        # Behaves like the engine: an existing file is left alone.
        calls.append(f.exists())
        if not f.exists():
            f.write_bytes(good)

    ok = integrity.check_sra(ctx, "SRR0000006", redownload)
    assert ok is True
    assert calls == [False]  # bad file was gone before the first retry
    assert logs.in_success(tmp_path, "SRR0000006")


# ------------------------- checkSRA (-g, SRA-only Run) -------------------------

def _sra_only_ctx(tmp_path, srr):
    """-g on a Run whose metadata lists no ENA fastq.gz: the .sra was fetched."""
    (tmp_path / f"{srr}.metadata.tsv").write_text(
        "run_accession\tfastq_md5\tlibrary_layout\tfastq_ftp\n"
        f"{srr}\t\tPAIRED\t\n"
    )
    (tmp_path / srr).write_bytes(b"fake sra payload")
    ctx = _ctx(tmp_path, gzip=True, database="ena")
    ctx.accession = srr
    ctx.database = "ena"
    return ctx


def test_gzip_sra_only_run_validates_sra_file(tmp_path, monkeypatch):
    # Regression: this used to look for fastq.gz md5s, find none, write the Run
    # to fail.log and exit 1 -- although the .sra was then converted correctly.
    ctx = _sra_only_ctx(tmp_path, "SRR0000003")
    validated = []
    monkeypatch.setattr(
        integrity, "vdb_validate", lambda c, s: validated.append(s) or True
    )

    calls = []
    ok = integrity.check_sra(ctx, "SRR0000003", lambda: calls.append(1))
    assert ok is True
    assert validated == ["SRR0000003"]
    assert calls == []  # no needless re-download
    assert ctx.failed is False
    assert logs.in_success(tmp_path, "SRR0000003")
    assert not (tmp_path / "fail.log").exists()


def test_gzip_sra_only_run_still_fails_on_bad_sra(tmp_path, monkeypatch):
    ctx = _sra_only_ctx(tmp_path, "SRR0000004")
    monkeypatch.setattr(integrity, "vdb_validate", lambda c, s: False)

    calls = []
    ok = integrity.check_sra(ctx, "SRR0000004", lambda: calls.append(1))
    assert ok is False
    assert len(calls) == 2  # same retry budget as any other .sra
    assert ctx.failed is True
    assert "SRR0000004" in (tmp_path / "fail.log").read_text()


def test_gzip_sra_only_run_counts_as_present(tmp_path):
    from adaptiseq import core

    ctx = _sra_only_ctx(tmp_path, "SRR0000005")
    assert core._run_files_present(ctx, "SRR0000005") is True
    (tmp_path / "SRR0000005").unlink()
    assert core._run_files_present(ctx, "SRR0000005") is False
