"""ENA metadata retries are bounded by a shared time budget, not a count.

Round 2 rep 3 (2026-10-21): the ENA portal answered in 24-45 s, with an HTTP 500
now and then, for three hours. Two runs went to SRA (no ENA md5, so unverified)
after about 15 s of retries. A run now waits up to ``ENA_PATIENCE_S`` of portal
failure, shared across the accessions of a list, and a slow empty answer is
retried instead of read as "not in ENA".
"""

from adaptiseq import metadata as meta
from adaptiseq.console import ListReporter
from adaptiseq.options import Options, RunContext

GOOD = ("study_accession\trun_accession\tfastq_md5\n"
        "PRJNA1\tSRR22904251\tabc\n")
HEADER_ONLY = "run_accession\tfastq_md5\n"
SRA_RUNINFO = "Run,ReleaseDate\nSRR22904251,2023-01-01\n"


def _ctx(tmp_path):
    return RunContext(options=Options(quiet=True), reporter=ListReporter(),
                      workdir=tmp_path)


def _clock(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(meta, "_now", lambda: clock[0])

    def sleep(s):
        clock[0] += s
    monkeypatch.setattr(meta, "_sleep", sleep)
    return clock


def _fake(answers, calls, clock):
    """ENA gets the next (body, rc, seconds it takes); the last one repeats."""
    def fake(url, out_path, **kw):
        calls.append(url)
        if "ebi.ac.uk" in url:
            n = len([u for u in calls if "ebi.ac.uk" in u])
            body, rc, took = answers[min(n, len(answers)) - 1]
            clock[0] += took
        elif "esearch" in url:
            body, rc = "<WebEnv>W</WebEnv><QueryKey>1</QueryKey>", 0
        else:
            body, rc = SRA_RUNINFO, 0
        with open(out_path, "a" if kw.get("cont") else "w") as fh:
            fh.write(body)
        return rc
    return fake


def _ena(calls):
    return [u for u in calls if "ebi.ac.uk" in u]


def test_outage_waits_for_the_patience_budget_then_falls_back(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    calls = []
    monkeypatch.setattr(meta, "wget_to_file", _fake([("", 8, 1.0)], calls, clock))
    ctx = _ctx(tmp_path)
    start = clock[0]

    meta.get_sra_metadata(ctx, "SRR22904251")

    assert ctx.database == "sra"
    waited = clock[0] - start
    assert meta.ENA_PATIENCE_S <= waited < meta.ENA_PATIENCE_S + 60
    assert len(_ena(calls)) < meta.ENA_ATTEMPTS


def test_portal_back_within_the_budget_keeps_the_run_on_ena(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    calls = []
    answers = [("", 8, 1.0)] * 6 + [(GOOD, 0, 1.0)]   # about 90 s of HTTP 500
    monkeypatch.setattr(meta, "wget_to_file", _fake(answers, calls, clock))
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR22904251")

    assert ctx.database != "sra"
    assert tsv.read_text() == GOOD
    assert len(_ena(calls)) == 7


def test_the_budget_is_shared_by_the_accessions_of_a_list(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    calls = []
    monkeypatch.setattr(meta, "wget_to_file", _fake([("", 8, 1.0)], calls, clock))
    meta.get_sra_metadata(_ctx(tmp_path), "SRR22904251")   # spends the budget
    first = len(_ena(calls))

    ctx = _ctx(tmp_path)
    meta.get_sra_metadata(ctx, "SRR22904252")

    # the next accession tries ENA_MIN_ATTEMPTS times, not the whole budget again
    assert len(_ena(calls)) - first == meta.ENA_MIN_ATTEMPTS
    assert ctx.database == "sra"


def test_slow_empty_answer_is_retried_not_read_as_missing(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    calls = []
    answers = [(HEADER_ONLY, 0, 30.0), (HEADER_ONLY, 0, 30.0), (GOOD, 0, 1.0)]
    monkeypatch.setattr(meta, "wget_to_file", _fake(answers, calls, clock))
    ctx = _ctx(tmp_path)

    tsv = meta.get_sra_metadata(ctx, "SRR22904251")

    assert ctx.database != "sra"          # 0.1.11 sent it to SRA after two
    assert tsv.read_text() == GOOD
    assert len(_ena(calls)) == 3


def test_fast_empty_answer_still_means_sra_only(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    calls = []
    monkeypatch.setattr(meta, "wget_to_file", _fake([(HEADER_ONLY, 0, 0.5)], calls, clock))
    ctx = _ctx(tmp_path)

    meta.get_sra_metadata(ctx, "SRR22904251")

    assert ctx.database == "sra"
    assert len(_ena(calls)) == meta.ENA_EMPTY_ATTEMPTS


def test_a_success_ends_the_streak(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    calls = []
    monkeypatch.setattr(meta, "wget_to_file",
                        _fake([("", 8, 1.0), (GOOD, 0, 1.0)], calls, clock))
    meta.get_sra_metadata(_ctx(tmp_path), "SRR22904251")
    assert meta._ena_failing(clock[0]) is None
