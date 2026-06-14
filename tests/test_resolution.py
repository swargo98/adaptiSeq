"""Offline URL-resolution parity using the frozen SRA fixture.

Only the gzip-direct path is exercised offline (it resolves purely from the
metadata file). The ``.sra`` path depends on ``srapath`` (a tool + network) and
is covered by the live differential test.
"""

from pathlib import Path

import pytest

import importlib

# The package attribute `adaptiseq.resolve` is the public API *function*, which
# shadows the submodule; reach the submodule explicitly via importlib.
R = importlib.import_module("adaptiseq.resolve")
from adaptiseq.console import NullReporter
from adaptiseq.options import Options, RunContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _ctx(tmp_path, **opts):
    src = FIXTURES / "SRR7706354" / "SRR7706354.metadata.tsv"
    (tmp_path / "SRR7706354.metadata.tsv").write_bytes(src.read_bytes())
    ctx = RunContext(options=Options(**opts), reporter=NullReporter(), workdir=tmp_path)
    ctx.accession = "SRR7706354"
    ctx.database = ctx.options.database
    return ctx


def test_gzip_ftp_resolution(tmp_path):
    ctx = _ctx(tmp_path, gzip=True, database="ena", protocol="ftp")
    urls = R.resolve_sra_urls(ctx, "SRR7706354")
    assert urls == [
        "ftp://ftp.sra.ebi.ac.uk/vol1/fastq/SRR770/004/SRR7706354/SRR7706354_1.fastq.gz",
        "ftp://ftp.sra.ebi.ac.uk/vol1/fastq/SRR770/004/SRR7706354/SRR7706354_2.fastq.gz",
    ]


def test_gzip_https_resolution(tmp_path):
    ctx = _ctx(tmp_path, gzip=True, database="ena", protocol="https")
    urls = R.resolve_sra_urls(ctx, "SRR7706354")
    assert all(u.startswith("https://") for u in urls)
    assert len(urls) == 2


def test_three_file_run_resolves_all_fastq_parts(tmp_path):
    # A PAIRED run with 3 fastq files (orphan/barcode + _1 + _2). iseq mishandles
    # this; adaptiSeq must resolve ALL .fastq.gz parts so the md5 check passes.
    base = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR229/069/SRR2290426"
    fastq_ftp = f"{base}/SRR2290426.fastq.gz;{base}/SRR2290426_1.fastq.gz;{base}/SRR2290426_2.fastq.gz"
    tsv = tmp_path / "SRR2290426.metadata.tsv"
    tsv.write_text(
        "run_accession\tlibrary_layout\tfastq_ftp\n"
        f"SRR2290426\tPAIRED\t{fastq_ftp}\n"
    )
    ctx = RunContext(
        options=Options(gzip=True, database="ena", protocol="ftp"),
        reporter=NullReporter(), workdir=tmp_path,
    )
    ctx.accession = "SRR2290426"
    ctx.database = "ena"
    urls = R.resolve_sra_urls(ctx, "SRR2290426")
    assert len(urls) == 3
    assert urls[0].endswith("SRR2290426.fastq.gz")
    assert urls[1].endswith("_1.fastq.gz")
    assert urls[2].endswith("_2.fastq.gz")


def test_link_extraction_uniq_collapses_ftp_and_galaxy(tmp_path):
    # fastq_ftp and fastq_galaxy are identical; uniq must collapse them to one
    # token so paired data resolves to exactly two links, not four.
    ctx = _ctx(tmp_path, gzip=True, database="ena")
    tsv_text = ctx.metadata_tsv().read_text()
    toks = R._tokens(R._lines_with(tsv_text, "SRR7706354"))
    fastq_links = R._extract(toks, R._RE_FASTQLINK)
    assert len(fastq_links) == 1
    assert fastq_links[0].count(";") == 1  # two semicolon-joined urls
