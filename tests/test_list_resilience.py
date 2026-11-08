"""Transient ENA metadata errors, and one bad accession in a list.

Gate run 54902879 (Expanse, 2026-10-13): ENA's portal answered one filereport
query with HTTP 200 and the body "ERROR occurred. Not all results may have been
written.Query: {...}". adaptiSeq saved that as SRR22904257.metadata.tsv, took
the error line for a Run, reused the cached file in Phase B, and the resulting
DownloadError stopped Phase B for every accession after it. These tests pin the
three fixes: retry the error body, never trust a cached error body, and keep
going through a list when one accession fails.
"""

from adaptiseq import batch, core
from adaptiseq import metadata as meta
from adaptiseq.console import ListReporter
from adaptiseq.errors import DownloadError
from adaptiseq.logs import FAIL_LOG
from adaptiseq.options import Options, RunContext

ERROR_BODY = (
    'ERROR occurred. Not all results may have been written.Query: {"bool":{"must":'
    '[{"term":{"run_accession":{"value":"SRR22904251"}}},{"match":{"status":{"query":4}}}]}}\n'
)
GOOD_BODY = (
    "run_accession\tlibrary_layout\tfastq_ftp\tfastq_md5\n"
    "SRR22904251\tSINGLE\tftp.sra.ebi.ac.uk/vol1/fastq/SRR000/001/SRR22904251/SRR22904251.fastq.gz\tabc\n"
)


def _ctx(tmp_path):
    opts = Options(gzip=True, database="ena", protocol="ftp", quiet=True)
    return RunContext(options=opts, reporter=ListReporter(), workdir=tmp_path)


def _fake_wget(bodies, calls):
    """wget_to_file stand-in: write the next body (the last one repeats)."""
    def fake(url, out_path, **kw):
        calls.append(url)
        body = bodies[min(len(calls), len(bodies)) - 1]
        with open(out_path, "a" if kw.get("cont") else "w") as fh:
            fh.write(body)
        return 0
    return fake


def test_has_ena_error(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text("run_accession\tfastq_ftp\n" + ERROR_BODY)
    assert meta.has_ena_error(p)
    p.write_text(GOOD_BODY)
    assert not meta.has_ena_error(p)
    assert not meta.has_ena_error(tmp_path / "missing.tsv")


def test_ena_error_body_is_retried(tmp_path, monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(meta, "wget_to_file", _fake_wget([ERROR_BODY, GOOD_BODY], calls))
    monkeypatch.setattr(meta, "_sleep", sleeps.append)
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR22904251")

    assert len(calls) == 2 and sleeps == [meta.ENA_RETRY_BASE_S]
    # the error body was removed, not resumed onto
    assert tsv.read_text() == GOOD_BODY
    assert ctx.database == "ena"


def test_persistent_ena_error_falls_back_to_sra(tmp_path, monkeypatch):
    calls, sleeps = [], []
    sra_runinfo = "Run,ReleaseDate\nSRR22904251,2023-01-01\n"

    def fake(url, out_path, **kw):
        calls.append(url)
        if "ebi.ac.uk" in url:
            body = ERROR_BODY
        elif "esearch" in url:
            body = "<WebEnv>W</WebEnv><QueryKey>1</QueryKey>"
        else:
            body = sra_runinfo
        with open(out_path, "a" if kw.get("cont") else "w") as fh:
            fh.write(body)
        return 0

    monkeypatch.setattr(meta, "wget_to_file", fake)
    monkeypatch.setattr(meta, "_sleep", sleeps.append)
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR22904251")

    ena_calls = [u for u in calls if "ebi.ac.uk" in u]
    assert len(ena_calls) == meta.ENA_ATTEMPTS
    assert len(sleeps) == meta.ENA_ATTEMPTS - 1
    assert ctx.database == "sra"
    assert not meta.has_ena_error(tsv)
    assert tsv.read_text().splitlines()[1].split("\t")[0] == "SRR22904251"


# ENA portal outage, 2026-10-15 (full run 54927001): the portal also answered
# with HTTP 500 (wget exit 8, empty file), timed out (exit 4), or sent HTTP 200
# with the header line only. Each sent the Run to SRA and cost its md5.
HEADER_ONLY = "run_accession\tfastq_md5\n"
SRA_RUNINFO = "Run,ReleaseDate\nSRR22904251,2023-01-01\n"


def _fake_ena(answers, calls):
    """wget_to_file stand-in: ENA gets the next (body, rc) (the last repeats);
    NCBI gets an esearch/runinfo answer for SRR22904251."""
    def fake(url, out_path, **kw):
        calls.append(url)
        if "ebi.ac.uk" in url:
            n = len([u for u in calls if "ebi.ac.uk" in u])
            body, rc = answers[min(n, len(answers)) - 1]
        elif "esearch" in url:
            body, rc = "<WebEnv>W</WebEnv><QueryKey>1</QueryKey>", 0
        else:
            body, rc = SRA_RUNINFO, 0
        with open(out_path, "a" if kw.get("cont") else "w") as fh:
            fh.write(body)
        return rc
    return fake


def test_failed_ena_request_is_retried(tmp_path, monkeypatch):
    calls, sleeps = [], []
    answers = [("", 8), ("", 4), (GOOD_BODY, 0)]
    monkeypatch.setattr(meta, "wget_to_file", _fake_ena(answers, calls))
    monkeypatch.setattr(meta, "_sleep", sleeps.append)
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR22904251")

    assert len(calls) == 3 and sleeps == [2.0, 4.0]
    assert tsv.read_text() == GOOD_BODY
    assert ctx.database == "ena"


def test_empty_ena_answer_is_retried_once(tmp_path, monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(meta, "wget_to_file", _fake_ena([(HEADER_ONLY, 0), (GOOD_BODY, 0)], calls))
    monkeypatch.setattr(meta, "_sleep", sleeps.append)
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR22904251")

    assert len(calls) == 2 and sleeps == [meta.ENA_RETRY_BASE_S]
    assert tsv.read_text() == GOOD_BODY  # not appended onto the header-only file
    assert ctx.database == "ena"


def test_sra_only_run_costs_one_extra_ena_query(tmp_path, monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(meta, "wget_to_file", _fake_ena([(HEADER_ONLY, 0)], calls))
    monkeypatch.setattr(meta, "_sleep", sleeps.append)
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR22904251")

    ena_calls = [u for u in calls if "ebi.ac.uk" in u]
    assert len(ena_calls) == meta.ENA_EMPTY_ATTEMPTS
    assert len(sleeps) == meta.ENA_EMPTY_ATTEMPTS - 1
    assert ctx.database == "sra"
    assert tsv.read_text().splitlines()[1].split("\t")[0] == "SRR22904251"


def test_persistent_ena_failure_falls_back_to_sra(tmp_path, monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(meta, "wget_to_file", _fake_ena([("<!doctype html>", 8)], calls))
    monkeypatch.setattr(meta, "_sleep", sleeps.append)
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR22904251")

    ena_calls = [u for u in calls if "ebi.ac.uk" in u]
    assert len(ena_calls) == meta.ENA_ATTEMPTS
    assert len(sleeps) == meta.ENA_ATTEMPTS - 1
    assert ctx.database == "sra"
    assert "doctype" not in tsv.read_text()


def test_batch_phase_names_accessions_sent_to_sra(tmp_path, monkeypatch):
    tasks = [
        batch.DownloadTask("https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR229/051/SRR22904251/SRR22904251.fastq.gz",
                           "SRR22904251.fastq.gz", "SRR22904251"),
        batch.DownloadTask("ftp.sra.ebi.ac.uk/vol1/fastq/SRR229/052/SRR22904252/SRR22904252.fastq.gz",
                           "SRR22904252.fastq.gz", "SRR22904252"),
        batch.DownloadTask("https://sra-pub-run-odp.s3.amazonaws.com/sra/SRR22904253/SRR22904253",
                           "SRR22904253", "SRR22904253"),
    ]
    monkeypatch.setattr(batch, "resolve_all", lambda *a, **k: (tasks, []))

    class NoDownload:
        def __init__(self, *a, **k):
            pass

        async def run(self, tasks):
            return set()

    monkeypatch.setattr(batch, "BatchDownloader", NoDownload)
    ctx = _ctx(tmp_path)

    core._batch_download_phase(ctx, ["SRR22904251", "SRR22904252", "SRR22904253"])

    notes = [m for m in ctx.reporter.infos if "downloaded from SRA" in m]
    assert len(notes) == 1 and notes[0].endswith("SRA: SRR22904253")
    assert "1 accession(s)" in notes[0]


def test_cached_error_body_is_refetched_by_batch_resolver(tmp_path, monkeypatch):
    (tmp_path / "SRR22904251.metadata.tsv").write_text("run_accession\n" + ERROR_BODY)
    fetched = []

    def fake_get(ctx, accession):
        fetched.append(accession)
        tsv = ctx.metadata_tsv(accession)
        tsv.write_text(GOOD_BODY)
        return tsv

    monkeypatch.setattr(meta, "get_sra_metadata", fake_get)
    monkeypatch.setattr(batch, "resolve_sra_urls", lambda ctx, run: [f"https://x/{run}.fastq.gz"])
    opts = Options(gzip=True, database="ena", protocol="ftp", quiet=True)

    tasks = batch._resolve_one("SRR22904251", opts, tmp_path)

    assert fetched == ["SRR22904251"]
    assert [t.save_path for t in tasks] == ["SRR22904251.fastq.gz"]


def test_cached_error_body_is_refetched_by_phase_b(tmp_path, monkeypatch):
    (tmp_path / "SRR22904251.metadata.tsv").write_text("run_accession\n" + ERROR_BODY)
    fetched = []

    def fake_get(ctx, accession):
        fetched.append(accession)
        ctx.metadata_tsv(accession).write_text(GOOD_BODY)
        return ctx.metadata_tsv(accession)

    monkeypatch.setattr(core.meta, "get_sra_metadata", fake_get)
    monkeypatch.setattr(core.resolve, "download_sra", lambda c, s: None)
    monkeypatch.setattr(core.integrity, "check_sra", lambda c, s, f: True)
    ctx = _ctx(tmp_path)

    core.process_accession(ctx, "SRR22904251")

    assert fetched == ["SRR22904251"]


def test_one_failing_accession_does_not_stop_the_list(tmp_path, monkeypatch):
    seen = []

    def fake_process(ctx, accession):
        seen.append(accession)
        if accession == "SRR22904252":
            raise DownloadError("The sequencing file of SRR22904252 is not available in all databases")

    monkeypatch.setattr(core, "process_accession", fake_process)
    monkeypatch.setattr(core, "_batch_download_phase", lambda ctx, accs: None)
    rep = ListReporter()
    opts = Options(gzip=True, database="ena", protocol="ftp", quiet=True)

    ctx = core.run(["SRR22904251", "SRR22904252", "SRR22904253"], opts, reporter=rep, workdir=tmp_path)

    assert seen == ["SRR22904251", "SRR22904252", "SRR22904253"]
    assert ctx.failed
    assert "SRR22904252" in (tmp_path / FAIL_LOG).read_text()
    assert any("not available in all databases" in e for e in rep.errors)


def test_single_accession_still_raises(tmp_path, monkeypatch):
    def fake_process(ctx, accession):
        raise DownloadError("boom")

    monkeypatch.setattr(core, "process_accession", fake_process)
    monkeypatch.setattr(core, "_batch_download_phase", lambda ctx, accs: None)
    opts = Options(gzip=True, database="ena", protocol="ftp", quiet=True)

    try:
        core.run(["SRR22904251"], opts, reporter=ListReporter(), workdir=tmp_path)
    except DownloadError:
        pass
    else:
        raise AssertionError("expected DownloadError for a single accession")
