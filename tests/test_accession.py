"""Accession validation regex parity (Section 3.3)."""

import pytest

from adaptiseq.accession import is_gsa, validate_query
from adaptiseq.errors import InvalidAccessionError


@pytest.mark.parametrize("acc", [
    "PRJEB42779", "PRJNA480016", "PRJDB14838",   # projects
    "ERP126685", "DRP009283", "SRP158268",        # studies
    "SAMD00258402", "SAMEA7997453", "SAMN06479985",  # biosamples
    "ERS5684710", "DRS259711", "SRS2024210",      # samples
    "ERX5050800", "DRX406443", "SRX4563689",      # experiments
    "ERR5260405", "DRR421224", "SRR7706354",      # runs
])
def test_direct_accessions_pass_through(acc):
    assert validate_query(acc) == acc


@pytest.mark.parametrize("acc", [
    "PRJCA000613", "CRA000553", "SAMC017083",
    "CRX020217", "CRR311377",
])
def test_gsa_accessions_route_to_gsa(acc):
    assert is_gsa(acc) is True
    # GSA accessions are not handled by validate_query (the SRA/ENA path)
    with pytest.raises(InvalidAccessionError):
        validate_query(acc)


@pytest.mark.parametrize("acc", [
    "NOTANACCESSION", "SRR123", "SRX12", "12345", "PRJX1", "",
])
def test_invalid_accessions_raise(acc):
    with pytest.raises(InvalidAccessionError):
        validate_query(acc)


def test_run_requires_six_digits():
    # The Bash regex is ^[EDS]RR[0-9]{6,}$ — fewer than 6 digits is invalid.
    with pytest.raises(InvalidAccessionError):
        validate_query("SRR12345")
    assert validate_query("SRR123456") == "SRR123456"


def test_sra_accessions_are_not_gsa():
    for acc in ["SRR7706354", "PRJNA480016", "ERX5050800"]:
        assert is_gsa(acc) is False
