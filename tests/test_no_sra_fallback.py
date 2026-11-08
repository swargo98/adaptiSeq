"""``--no-sra-fallback``: fail an accession rather than fetch it from NCBI SRA.

During the ENA portal outage of 2026-10-15 (full run 54927001) every tool sent
runs with no ENA answer to SRA, and the converted files could not be checked
against ENA's md5. With ``no_sra_fallback`` adaptiSeq must stop at each of the
three places that lead to SRA: metadata, URL resolution, and a cached SRA
runinfo file from an earlier run.
"""

import importlib

import pytest

from adaptiseq import batch, cli
from adaptiseq import metadata as meta
from adaptiseq.console import ListReporter
from adaptiseq.errors import DownloadError, MetadataError
from adaptiseq.options import Options, RunContext

# `adaptiseq.resolve` as a package attribute is the public API function.
resolve = importlib.import_module("adaptiseq.resolve")

ACC = "SRR22904251"
HEADER_ONLY = "run_accession\tfastq_md5\n"
SRA_RUNINFO = f"Run,ReleaseDate\n{ACC},2023-01-01\n"
ENA_COLUMNS = "study_accession\trun_accession\tlibrary_layout\tfastq_md5\tfastq_ftp\tsra_ftp\n"
ENA_FASTQ = (ENA_COLUMNS + f"PRJNA1\t{ACC}\tSINGLE\tabc\t"
             f"ftp.sra.ebi.ac.uk/vol1/fastq/SRR229/051/{ACC}/{ACC}.fastq.gz\t\n")
ENA_NO_FILES = ENA_COLUMNS + f"PRJNA1\t{ACC}\tSINGLE\t\t\t\n"


def _ctx(tmp_path, **kw):
    opts = Options(gzip=True, protocol="ftp", quiet=True, no_sra_fallback=True, **kw)
    ctx = RunContext(options=opts, reporter=ListReporter(), workdir=tmp_path)
    ctx.accession = ACC
    return ctx


def test_empty_ena_answer_raises_instead_of_querying_ncbi(tmp_path, monkeypatch):
    calls = []

    def fake(url, out_path, **kw):
        calls.append(url)
        body = HEADER_ONLY if "ebi.ac.uk" in url else SRA_RUNINFO
        with open(out_path, "a" if kw.get("cont") else "w") as fh:
            fh.write(body)
        return 0

    monkeypatch.setattr(meta, "wget_to_file", fake)
    monkeypatch.setattr(meta, "_sleep", lambda s: None)
    ctx = _ctx(tmp_path)

    with pytest.raises(MetadataError, match="--no-sra-fallback"):
        meta.get_sra_metadata(ctx, ACC)

    assert calls and all("ebi.ac.uk" in u for u in calls)
    assert ctx.database != "sra"


def test_ena_row_without_files_does_not_reach_srapath(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    ctx.metadata_tsv().write_text(ENA_NO_FILES)

    def no_srapath(srr):
        raise AssertionError("srapath must not run with no_sra_fallback")

    monkeypatch.setattr(resolve, "_srapath", no_srapath)
    with pytest.raises(DownloadError, match="--no-sra-fallback"):
        resolve.resolve_sra_urls(ctx, ACC)
    with pytest.raises(DownloadError, match="--no-sra-fallback"):
        resolve.download_sra(ctx, ACC)


def test_cached_sra_runinfo_is_queried_again(tmp_path, monkeypatch):
    opts = Options(gzip=True, protocol="ftp", quiet=True, no_sra_fallback=True)
    (tmp_path / f"{ACC}.metadata.tsv").write_text(SRA_RUNINFO.replace(",", "\t"))
    queried = []

    def fake_metadata(ctx, accession):
        queried.append(accession)
        tsv = ctx.metadata_tsv(accession)
        tsv.write_text(ENA_FASTQ)
        return tsv

    monkeypatch.setattr(meta, "get_sra_metadata", fake_metadata)
    tasks = batch._resolve_one(ACC, opts, tmp_path)

    assert queried == [ACC]
    assert [t.url for t in tasks] == [
        f"ftp://ftp.sra.ebi.ac.uk/vol1/fastq/SRR229/051/{ACC}/{ACC}.fastq.gz"
    ]


def test_cached_ena_tsv_is_reused(tmp_path, monkeypatch):
    opts = Options(gzip=True, protocol="ftp", quiet=True, no_sra_fallback=True)
    (tmp_path / f"{ACC}.metadata.tsv").write_text(ENA_FASTQ)
    monkeypatch.setattr(meta, "get_sra_metadata",
                        lambda ctx, acc: pytest.fail("cached ENA metadata was refetched"))

    assert len(batch._resolve_one(ACC, opts, tmp_path)) == 1


def test_is_ena_tsv(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text(ENA_FASTQ)
    assert meta.is_ena_tsv(p)
    p.write_text(SRA_RUNINFO.replace(",", "\t"))
    assert not meta.is_ena_tsv(p)
    assert not meta.is_ena_tsv(tmp_path / "missing.tsv")


def test_conflicts_with_database_sra(capsys):
    with pytest.raises(ValueError):
        Options(no_sra_fallback=True, database="sra")
    assert cli.main(["-i", ACC, "--no-sra-fallback", "-d", "sra"]) == 1
    assert "--no-sra-fallback cannot be used with -d sra" in capsys.readouterr().err
