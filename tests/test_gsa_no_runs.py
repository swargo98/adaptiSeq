"""A GSA accession that resolves to no Run must fail, not exit 0.

2026-10-20, round 2 rep 1 (panel 4g, topdown arm): GSA's getRunInfoByCra table
for CRA002399 came back without CRR120307. Filtered to that Run, its metadata
CSV held only the header; the batch resolver made no task, the per-accession
loop found no CRR, printed "CRR120307 download finished" and the tool exited 0
with the Run missing. The run-info query is now retried and then fails.
"""

import pytest

from adaptiseq import batch, core
from adaptiseq import metadata as meta
from adaptiseq.console import ListReporter
from adaptiseq.errors import MetadataError
from adaptiseq.options import Options, RunContext

HEADER = "Run,Center,ReleaseDate,FileType,FileName,FileSize,Download_path,Experiment,Title\n"
ROW = ("CRR120307,NGDC,2020-03-14,fastq,CRR120307.fastq.gz,10,"
       "ftp://download.big.ac.cn/gsa3/CRA002399/CRR120307/CRR120307.fastq.gz,"
       "CRX095512,t\n")


def _ctx(tmp_path):
    ctx = RunContext(options=Options(quiet=True), reporter=ListReporter(),
                     workdir=tmp_path)
    ctx.accession = "CRR120307"
    return ctx


def _fake_gsa(monkeypatch, answers):
    """Search page names CRA002399; each run-info request returns the next answer."""
    calls = []
    monkeypatch.setattr(meta, "wget_capture", lambda *a, **k: "CRA002399")
    monkeypatch.setattr(meta, "_sleep", lambda s: None)
    monkeypatch.setattr(meta, "get_gsa_xlsx", lambda ctx, cra: None)

    def wget_to_file(url, out, **kw):
        calls.append(url)
        out.write_text(answers[min(len(calls), len(answers)) - 1])
        return 0
    monkeypatch.setattr(meta, "wget_to_file", wget_to_file)
    return calls


def test_partial_run_info_is_retried(tmp_path, monkeypatch):
    calls = _fake_gsa(monkeypatch, [HEADER, HEADER + ROW])
    csv = meta.get_gsa_metadata(_ctx(tmp_path), "CRR120307")
    assert len(calls) == 2
    assert csv.read_text() == HEADER + ROW


def test_run_missing_after_retries_fails_and_leaves_no_csv(tmp_path, monkeypatch):
    calls = _fake_gsa(monkeypatch, [HEADER])
    with pytest.raises(MetadataError, match="no row for CRR120307"):
        meta.get_gsa_metadata(_ctx(tmp_path), "CRR120307")
    assert len(calls) == meta.GSA_ATTEMPTS
    assert not (tmp_path / "CRR120307.metadata.csv").exists()


def test_header_only_csv_on_disk_is_fetched_again(tmp_path, monkeypatch):
    # The case seen: the CSV was already on disk with no Run row.
    (tmp_path / "CRR120307.metadata.csv").write_text(HEADER)
    calls = _fake_gsa(monkeypatch, [HEADER])
    ctx = _ctx(tmp_path)
    with pytest.raises(MetadataError):
        core.process_accession(ctx, "CRR120307")
    assert calls, "the stale header-only CSV was trusted"
    assert not any("download finished" in m for m in ctx.reporter.infos)


def test_batch_resolver_refetches_header_only_csv(tmp_path, monkeypatch):
    (tmp_path / "CRR120307.metadata.csv").write_text(HEADER)
    calls = _fake_gsa(monkeypatch, [HEADER])
    with pytest.raises(MetadataError):
        batch._resolve_one("CRR120307", Options(quiet=True), tmp_path)
    assert calls


def test_list_run_exits_nonzero_when_a_gsa_run_resolves_to_nothing(tmp_path, monkeypatch):
    (tmp_path / "CRR120307.metadata.csv").write_text(HEADER)
    _fake_gsa(monkeypatch, [HEADER])
    monkeypatch.setattr(core, "_batch_download_phase", lambda ctx, accs: None)
    monkeypatch.setattr(core, "_process_sra", lambda ctx, acc: None)
    ctx = core.run(["CRR120307", "SRR1"], Options(quiet=True), workdir=tmp_path)
    assert ctx.failed
    assert "CRR120307" in (tmp_path / "fail.log").read_text()
