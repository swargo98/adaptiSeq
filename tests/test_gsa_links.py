"""GSA downloads take their links from the run-info table, and join the batch.

2026-10-19: GSA's browse page (ngdc.cncb.ac.cn/gsa/browse/CRA/CRR), where the
download links used to be read from, now answers scripts with a JavaScript
"browser check" page and no links, so a GSA run had nothing to fetch. The
run-info table from GSA's API carries the same paths (``Download_path``), and
download.cncb.ac.cn serves them over range-capable HTTPS. GSA accessions also
used to skip the batch pool and download one file at a time.
"""

import hashlib
import importlib

import pytest

from adaptiseq import batch, core, integrity
from adaptiseq.console import ListReporter
from adaptiseq.options import Options, RunContext

resolve = importlib.import_module("adaptiseq.resolve")

CSV = (
    "Run,Center,ReleaseDate,FileType,FileName,FileSize,Download_path,Experiment,Title\n"
    "CRR120307,NGDC,2020-03-14,fastq,CRR120307.fastq.gz,10,"
    "ftp://download.big.ac.cn/gsa3/CRA002399/CRR120307/CRR120307.fastq.gz,CRX095512,"
    '"ath1, RNA-seq"\n'
    "CRR9,NGDC,2020-03-14,fastq,CRR9_f1.fq.gz|CRR9_r2.fq.gz,10|10,"
    "ftp://download.big.ac.cn/gsa3/CRA002399/CRR9/CRR9_f1.fq.gz|"
    "ftp://download.big.ac.cn/gsa3/CRA002399/CRR9/CRR9_r2.fq.gz,CRX1,t\n"
)


def _ctx(tmp_path, **kw):
    ctx = RunContext(options=Options(quiet=True, **kw), reporter=ListReporter(),
                     workdir=tmp_path)
    ctx.accession = "CRX095512"
    (tmp_path / "CRX095512.metadata.csv").write_text(CSV)
    return ctx


def test_links_come_from_the_run_info_table():
    assert resolve.gsa_csv_links(CSV, "CRR120307") == [
        "ftp://download.big.ac.cn/gsa3/CRA002399/CRR120307/CRR120307.fastq.gz"]
    assert len(resolve.gsa_csv_links(CSV, "CRR9")) == 2
    assert resolve.gsa_csv_links(CSV, "CRR404") == []
    assert resolve.gsa_https(
        "ftp://download.big.ac.cn/gsa3/CRA002399/CRR9/CRR9_f1.fq.gz"
    ) == "https://download.cncb.ac.cn/gsa3/CRA002399/CRR9/CRR9_f1.fq.gz"


def test_resolution_uses_https_and_never_the_browse_page(tmp_path, monkeypatch):
    monkeypatch.setattr(resolve, "wget_capture",
                        lambda *a, **k: pytest.fail("browse page was fetched"))
    ctx = _ctx(tmp_path)
    assert resolve.resolve_gsa_urls(ctx, "CRR120307") == [
        "https://download.cncb.ac.cn/gsa3/CRA002399/CRR120307/CRR120307.fastq.gz"]
    ctx = _ctx(tmp_path, protocol="ftp")
    assert resolve.resolve_gsa_urls(ctx, "CRR120307")[0].startswith("ftp://download.big")


def test_md5_retry_downloads_again_instead_of_rechecking(tmp_path, monkeypatch):
    good, bad = b"good bytes", b"bad bytes!"
    ctx = _ctx(tmp_path)
    (tmp_path / "CRA002399.md5sum.txt").write_text(
        f"{hashlib.md5(good).hexdigest()}\t/CRA002399/CRR120307/CRR120307.fastq.gz\n")
    monkeypatch.setattr(resolve, "wget_spider_size", lambda *a, **k: "10")
    monkeypatch.setattr(integrity.shutil, "which", lambda name: "/usr/bin/" + name)
    calls = []

    class Engine:
        def fetch(self, link, name):
            # like the resuming engine: a full-size file present is left alone
            calls.append(link)
            p = tmp_path / name
            if not p.exists():
                p.write_bytes(bad if len(calls) == 1 else good)
            return True
    ctx.engine = Engine()
    resolve._gsa_one(ctx, "https://download.cncb.ac.cn/gsa3/CRA002399/CRR120307/"
                     "CRR120307.fastq.gz", "CRR120307", "CRA002399",
                     mode="https", ftp=False, aspera=False)
    assert len(calls) == 2                     # bad copy removed, fetched once more
    assert (tmp_path / "CRR120307.fastq.gz").read_bytes() == good


def test_batch_resolution_includes_gsa_with_md5(tmp_path, monkeypatch):
    (tmp_path / "CRX095512.metadata.csv").write_text(CSV)
    (tmp_path / "CRA002399.md5sum.txt").write_text(
        "aaa\t/CRA002399/CRR120307/CRR120307.fastq.gz\n"
        "bbb\t/CRA002399/CRR9/CRR9_f1.fq.gz\n")
    monkeypatch.setattr(resolve, "wget_capture",
                        lambda *a, **k: pytest.fail("browse page was fetched"))
    tasks = batch._resolve_one("CRX095512", Options(quiet=True), tmp_path)
    got = {t.save_path: (t.url.split("/")[2], t.md5) for t in tasks}
    assert got["CRR120307.fastq.gz"] == ("download.cncb.ac.cn", "aaa")
    assert got["CRR9_f1.fq.gz"] == ("download.cncb.ac.cn", "bbb")
    assert got["CRR9_r2.fq.gz"][1] is None


def test_gsa_is_not_reported_as_an_sra_fallback():
    T = batch.DownloadTask
    tasks = [T("https://download.cncb.ac.cn/x/CRR1.fastq.gz", "CRR1.fastq.gz", "CRX1"),
             T("https://sra-pub-run-odp.s3.amazonaws.com/sra/SRR1/SRR1", "SRR1", "SRR1")]
    assert core._non_ena_accessions(tasks) == ["SRR1"]


def test_gsa_md5s_parses_the_listing():
    assert integrity.gsa_md5s("ABC  /CRA1/CRR1/CRR1.fastq.gz\nxyz /CRA1/CRR1/CRR1.sra\n") == {
        "CRR1.fastq.gz": "abc", "CRR1.sra": "xyz"}


def test_md5_list_fetch_is_retried_and_an_empty_file_refetched(tmp_path, monkeypatch):
    """A refused md5sum.txt fetch used to leave an empty file that was never
    fetched again, so the project's files were 'verified' without an md5."""
    ctx = _ctx(tmp_path)
    (tmp_path / "CRA002399.md5sum.txt").write_text("")       # left by a failed fetch
    calls = []

    def fake_wget(url, out, **kw):
        calls.append(url)
        open(out, "w").write("" if len(calls) < 3 else "abc  /CRA002399/CRR120307/x.gz\n")
        return 0 if len(calls) >= 3 else 4
    monkeypatch.setattr(integrity, "wget_to_file", fake_wget)
    monkeypatch.setattr("time.sleep", lambda s: None)
    p = integrity.ensure_gsa_md5(ctx, "CRA002399")
    assert len(calls) == 3 and calls[0].endswith("gsa3/CRA002399/md5sum.txt")
    assert "abc" in p.read_text()


def test_without_an_md5_list_the_size_must_match(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(integrity, "ensure_gsa_md5", lambda c, cra: tmp_path / "none.txt")
    f = tmp_path / "CRR120307.fastq.gz"
    f.write_bytes(b"x" * 10)                                   # table lists 10 bytes
    assert integrity.verify_gsa(ctx, "CRR120307.fastq.gz", "CRA002399") is None
    f.write_bytes(b"x" * 9)
    assert integrity.verify_gsa(ctx, "CRR120307.fastq.gz", "CRA002399") is False
