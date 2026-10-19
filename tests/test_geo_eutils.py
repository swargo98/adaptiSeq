"""GEO accessions resolve through NCBI E-utilities.

2026-10-19: GEO's accession page (geo/query/acc.cgi), which adaptiSeq and iSeq
scraped for the BioProject/BioSample, answers scripts with a reCAPTCHA "Checking
your browser" page, so every GSE/GSM was rejected as "not a valid GEO accession".
GSE now resolves via GEO DataSets (``bioproject``), GSM via BioSample (whose
identifiers list the GSM); the page stays as a fallback.
"""

import json

import pytest

from adaptiseq import accession as acc_mod
from adaptiseq.errors import InvalidAccessionError

CAPTCHA = "<html><title>Checking your browser - reCAPTCHA</title></html>"


def _fake(responses, calls):
    def wget_capture(url, **kw):
        calls.append(url)
        for key, body in responses.items():
            if key in url:
                return body if isinstance(body, str) else json.dumps(body)
        return CAPTCHA
    return wget_capture


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    class Instant:
        def acquire(self):
            pass
    monkeypatch.setattr(acc_mod, "_NCBI_LIMITER", Instant())


def test_gsm_resolves_through_biosample(monkeypatch):
    calls = []
    monkeypatch.setattr(acc_mod, "wget_capture", _fake({
        "esearch.fcgi?db=biosample": {"esearchresult": {"idlist": ["35350598", "1"]}},
        "esummary.fcgi?db=biosample": {"result": {"uids": ["35350598", "1"],
            "35350598": {"accession": "SAMN35350598",
                         "identifiers": "BioSample: SAMN35350598; SRA: SRS1; GEO: GSM7417667"},
            "1": {"accession": "SAMN1", "identifiers": "GEO: GSM74176670"}}},
    }, calls))
    assert acc_mod.validate_query("GSM7417667") == "SAMN35350598"
    assert not any("acc.cgi" in u for u in calls)


def test_gse_resolves_through_geo_datasets(monkeypatch):
    monkeypatch.setattr(acc_mod, "wget_capture", _fake({
        "esearch.fcgi?db=gds": {"esearchresult": {"idlist": ["200233000"]}},
        "esummary.fcgi?db=gds": {"result": {"uids": ["200233000"], "200233000": {
            "accession": "GSE233000", "bioproject": "PRJNA974701", "entrytype": "GSE"}}},
    }, []))
    assert acc_mod.validate_query("GSE233000") == "PRJNA974701"


def test_text_record_fallback_and_captcha_rejection(monkeypatch):
    # E-utilities empty: the text record, then the page; a CAPTCHA has no ids
    monkeypatch.setattr(acc_mod, "wget_capture", _fake({
        "esearch.fcgi": {"esearchresult": {"idlist": []}},
    }, []))
    with pytest.raises(InvalidAccessionError):
        acc_mod.validate_query("GSM1")
    calls = []
    monkeypatch.setattr(acc_mod, "wget_capture", _fake({
        "esearch.fcgi": {"esearchresult": {"idlist": []}},
        "form=text": "!Sample_relation = BioSample: https://www.ncbi.nlm.nih.gov/biosample/SAMN99\n",
    }, calls))
    assert acc_mod.validate_query("GSM2") == "SAMN99"
    assert "form=text" in calls[-1]             # the text record, not the HTML page
    monkeypatch.setattr(acc_mod, "wget_capture", _fake({
        "esearch.fcgi": {"esearchresult": {"idlist": []}},
        "form=text": "!Series_relation = BioProject: https://www.ncbi.nlm.nih.gov/bioproject/PRJNA7\n",
    }, []))
    assert acc_mod.validate_query("GSE7") == "PRJNA7"
