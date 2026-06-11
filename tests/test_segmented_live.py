"""Live segmented-engine acceptance tests (skip gracefully offline).

Acceptance #1/#4 exercised against the real ENA HTTPS mirror: a small real file
downloaded by the segmented engine is byte-identical to what ``wget`` (the classic
engine's transport) produces, fetched as multiple strict-206 ranged segments.
"""

import asyncio
import hashlib
import os
import subprocess

import aiohttp
import pytest

import adaptiseq
from adaptiseq.engine.ratelimit import HostGuard
from adaptiseq.engine.segmented import SegmentedDownloader

# A deliberately small, long-archived ENA run (~2.2 MB) so the test is fast.
ACCESSION = "SRR1553469"


def _link():
    recs = adaptiseq.get_metadata(ACCESSION, database="ena")
    ftp = recs[0]["fastq_ftp"].split(";")[0]
    return ftp  # e.g. ftp.sra.ebi.ac.uk/vol1/fastq/.../SRR1553469_1.fastq.gz


def test_segmented_matches_wget_live(online, tmp_path):
    if not online:
        pytest.skip("offline: live segmented byte-identity test skipped")
    try:
        link = _link()
    except Exception as e:  # pragma: no cover - network flake
        pytest.skip(f"could not resolve link live: {e}")
    url = "https://" + link

    # Reference via wget (the classic transport).
    ref = tmp_path / "wget.gz"
    rc = subprocess.run(["wget", "-q", url, "-O", str(ref)]).returncode
    if rc != 0 or ref.stat().st_size == 0:
        pytest.skip("wget reference download failed (network)")

    # Segmented engine, forced to multi-segment for a small file.
    out = str(tmp_path / "seg.gz")

    async def go():
        async with aiohttp.ClientSession() as s:
            d = SegmentedDownloader(
                s, url, out, segment_size=512 * 1024, max_segments=6,
                min_file_size_for_segmentation=256 * 1024, host_guard=HostGuard(8),
            )
            size, supports = await d.probe_range_support()
            assert supports, "ENA HTTPS mirror should support ranges (206)"
            assert len(d.calculate_segments(size)) > 1, "expected multiple segments"
            return await d.download()

    ok = asyncio.run(go())
    assert ok is True
    a = hashlib.md5(ref.read_bytes()).hexdigest()
    b = hashlib.md5((tmp_path / "seg.gz").read_bytes()).hexdigest()
    assert a == b, "segmented output differs from wget reference"
