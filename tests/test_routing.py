"""Routing and -e merge guard parity (Section 4 / lines 174-202)."""

import pytest

from adaptiseq.errors import AdaptiSeqError
from adaptiseq.routing import check_merge_guard, route


def test_route_gsa_vs_sra():
    assert route("CRR311377") == "gsa"
    assert route("PRJCA000613") == "gsa"
    assert route("SRR7706354") == "sra"
    assert route("PRJNA480016") == "sra"


def test_merge_ex_rejects_run():
    with pytest.raises(AdaptiSeqError) as e:
        check_merge_guard("ex", ["SRR123456"])
    assert "is a Run ID" in e.value.message


def test_merge_ex_allows_experiment():
    check_merge_guard("ex", ["SRX123456"])  # no raise


def test_merge_sa_rejects_run_and_experiment():
    with pytest.raises(AdaptiSeqError):
        check_merge_guard("sa", ["SRR123456"])
    with pytest.raises(AdaptiSeqError):
        check_merge_guard("sa", ["SRX123456"])
    check_merge_guard("sa", ["SRS123456"])  # sample allowed


def test_merge_st_rejects_run_exp_sample():
    for bad in ["SRR123456", "SRX123456", "SRS123456", "SAMN06479985"]:
        with pytest.raises(AdaptiSeqError):
            check_merge_guard("st", [bad])
    check_merge_guard("st", ["SRP158268"])  # study allowed
    check_merge_guard("st", ["PRJNA480016"])  # project allowed


def test_merge_guard_includes_gsa_runs():
    # The Bash guard regex includes C (CRR/CRX) for GSA accessions.
    with pytest.raises(AdaptiSeqError):
        check_merge_guard("ex", ["CRR311377"])
