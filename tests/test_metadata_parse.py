"""Metadata parsing parity against frozen fixtures."""

from pathlib import Path

from adaptiseq.metadata import parse_csv, parse_tsv

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_sra_tsv_columns_and_rows():
    rows = parse_tsv(FIXTURES / "SRR7706354" / "SRR7706354.metadata.tsv")
    assert len(rows) == 1
    r = rows[0]
    assert r["run_accession"] == "SRR7706354"
    assert r["library_layout"] == "PAIRED"
    assert len(r) == 51
    assert ";" in r["fastq_md5"]


def test_parse_gsa_csv_columns_and_rows():
    rows = parse_csv(FIXTURES / "CRR311377" / "CRR311377.metadata.csv")
    assert len(rows) == 1
    r = rows[0]
    assert r["Run"] == "CRR311377"
    assert r["FileName"] == "CRR311377.fq.gz"
    assert len(r) == 25
