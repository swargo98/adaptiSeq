"""API-drift canary (Section 8.2).

ENA / NCBI / GSA metadata endpoints change repeatedly (GSA Nov 2025, ENA Sep
2025). These live tests fetch one known-stable accession per database and assert
the expected column structure is still present. A failure here means an *upstream
API moved*, not that adaptiSeq is broken — the assertion messages say so. Kept
separate from the offline suite; skips when offline.
"""

import pytest

import adaptiseq

UPSTREAM_MOVED = (
    "Upstream {db} metadata API appears to have changed (expected column {col!r} "
    "missing). This is an external API drift, not an adaptiSeq bug — update the "
    "field list / parser to match the new {db} schema."
)


def test_ena_columns_present(online):
    if not online:
        pytest.skip("offline: API-drift canary skipped")
    records = adaptiseq.get_metadata("SRR7706354", database="ena")
    assert records, "ENA returned no rows for a known-stable accession"
    row = records[0]
    for col in ("run_accession", "fastq_ftp", "fastq_md5", "library_layout"):
        assert col in row, UPSTREAM_MOVED.format(db="ENA", col=col)


def test_gsa_columns_present(online):
    if not online:
        pytest.skip("offline: API-drift canary skipped")
    records = adaptiseq.get_metadata("CRR311377")
    assert records, "GSA returned no rows for a known-stable accession"
    row = records[0]
    for col in ("Run", "FileName", "FileSize", "Download_path"):
        assert col in row, UPSTREAM_MOVED.format(db="GSA", col=col)
