"""ENA's portal API sometimes returns an error message instead of the TSV rows.

Seen on 2026-10-14 for ~3 of 241 per-Run queries per tool. iseq parses the line
as a Run named "ERROR"; adaptiSeq must re-query, and fall back to SRA if ENA
keeps failing, instead of treating the text as an accession.
"""

from pathlib import Path

from adaptiseq import metadata as meta
from adaptiseq.console import NullReporter
from adaptiseq.options import Options, RunContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOOD = (FIXTURES / "SRR7706354" / "SRR7706354.metadata.tsv").read_text()
HEADER = GOOD.splitlines()[0] + "\n"
ERROR = (
    HEADER
    + "ERROR occurred. Not all results may have been written.Query: "
    '{"bool":{"must":[{"term":{"run_accession":{"value":"SRR7706354"}}}]}}\n'
)


def _ctx(tmp_path):
    return RunContext(options=Options(), reporter=NullReporter(), workdir=tmp_path)


def _fake_wget(bodies, calls):
    """wget_to_file stand-in that serves ``bodies`` in order (wget -c appends)."""

    def fake(url, out_path, *, cont=False, **kw):
        calls.append(url)
        body = bodies[min(len(calls), len(bodies)) - 1]
        mode = "a" if cont and Path(out_path).exists() else "w"
        with open(out_path, mode) as fh:
            fh.write(body)
        return 0

    return fake


def test_ena_error_body_is_requeried(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(meta, "wget_to_file", _fake_wget([ERROR, GOOD], calls))
    monkeypatch.setattr(meta, "ENA_RETRY_DELAY_S", 0)
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR7706354")

    assert len(calls) == 2
    assert tsv.read_text() == GOOD
    assert ctx.database != "sra"


def test_persistent_ena_error_falls_back_to_sra(tmp_path, monkeypatch):
    calls = []
    sra_runinfo = "Run,size_MB\nSRR7706354,10\n"

    def fake(url, out_path, *, cont=False, **kw):
        calls.append(url)
        if "ebi.ac.uk" in url:
            body = ERROR
        elif "esearch" in url:
            body = "<WebEnv>W</WebEnv><QueryKey>1</QueryKey>"
        else:
            body = sra_runinfo
        mode = "a" if cont and Path(out_path).exists() else "w"
        with open(out_path, mode) as fh:
            fh.write(body)
        return 0

    monkeypatch.setattr(meta, "wget_to_file", fake)
    monkeypatch.setattr(meta, "ENA_RETRY_DELAY_S", 0)
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR7706354")

    assert sum("ebi.ac.uk" in u for u in calls) == meta.ENA_QUERY_ATTEMPTS
    assert ctx.database == "sra"
    assert not meta.has_ena_error(tsv)
    assert tsv.read_text().splitlines()[1].split("\t")[0] == "SRR7706354"


def test_cached_error_file_is_replaced(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(meta, "wget_to_file", _fake_wget([GOOD], calls))
    ctx = _ctx(tmp_path)
    ctx.metadata_tsv("SRR7706354").write_text(ERROR)

    tsv = meta.get_sra_metadata(ctx, "SRR7706354")

    assert len(calls) == 1
    assert tsv.read_text() == GOOD
