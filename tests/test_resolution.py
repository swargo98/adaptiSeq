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


def test_link_extraction_uniq_collapses_ftp_and_galaxy(tmp_path):
    # fastq_ftp and fastq_galaxy are identical; uniq must collapse them to one
    # token so paired data resolves to exactly two links, not four.
    ctx = _ctx(tmp_path, gzip=True, database="ena")
    tsv_text = ctx.metadata_tsv().read_text()
    toks = R._tokens(R._lines_with(tsv_text, "SRR7706354"))
    fastq_links = R._extract(toks, R._RE_FASTQLINK)
    assert len(fastq_links) == 1
    assert fastq_links[0].count(";") == 1  # two semicolon-joined urls
