"""iSeq issue #60: the merge step's sample-ID pattern did not match SAMN50758553-style IDs there."""
from adaptiseq import merge


def test_sample_ids_of_every_archive_and_length_are_found():
    text = "x SAMN50758553 y SAMEA123456 z SAMD00012345 SAMN02427192 SAMEA1234"
    assert set(merge._RE_SAM.findall(text)) == {
        "SAMN50758553", "SAMEA123456", "SAMD00012345", "SAMN02427192", "SAMEA1234"}
