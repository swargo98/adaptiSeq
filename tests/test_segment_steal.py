"""A file's connections stay busy until its last byte.

Controller trace 55061744 (0.1.5, panel 3b, adaptive default): the bulk of 26 GB
arrived in 4 min on about 50 connections, then the last 5 files took 15 more
minutes on about 5, because each file's split was fixed at its start and only one
slow segment per file was left. Now a finished segment's connection takes over
half of the largest remainder, and spare connection budget offered by the batch
(queue empty) splits a file further, up to ``max_segments``.
"""

import asyncio
import hashlib
import json
import os
import time

import aiohttp

from adaptiseq.engine import segmented
from adaptiseq.engine.segmented import SegmentedDownloader
from tests.servers import MultiFileRangeServer

MB = 1024 * 1024


def md5(b):
    return hashlib.md5(b).hexdigest()


def _fast_split(monkeypatch):
    monkeypatch.setattr(segmented, "MIN_STEAL", 128 * 1024)
    monkeypatch.setattr(segmented, "SPLIT_POLL_S", 0.05)


def _download(srv, name, dest, **kw):
    async def main():
        async with aiohttp.ClientSession() as s:
            d = SegmentedDownloader(s, srv.url(name), str(dest), **kw)
            ok = await d.download()
            return ok, d
    return asyncio.run(main())


def test_finished_segment_takes_over_half_of_a_straggler(tmp_path, monkeypatch):
    _fast_split(monkeypatch)
    data = os.urandom(8 * MB)
    with MultiFileRangeServer({"f.bin": data}) as srv:
        # segment 0 (bytes 0..4 MiB-1) crawls; segment 1 is fast
        srv.throttle["f.bin"] = (1 * MB, 0)
        t0 = time.monotonic()
        ok, d = _download(srv, "f.bin", tmp_path / "f.bin", segment_size=4 * MB,
                          max_segments=2)
        took = time.monotonic() - t0
        starts = sorted(a for n, a in srv.range_starts if n == "f.bin")
    assert ok
    assert md5((tmp_path / "f.bin").read_bytes()) == md5(data)
    assert d.splits >= 1
    # someone fetched from inside segment 0's original range
    assert any(0 < a < 4 * MB for a in starts)
    # without the split segment 0 alone needs 4 s at 1 MiB/s
    assert took < 3.5


def test_spare_budget_splits_a_single_segment_file(tmp_path, monkeypatch):
    _fast_split(monkeypatch)
    data = os.urandom(4 * MB)
    with MultiFileRangeServer({"f.bin": data}) as srv:
        srv.throttle["f.bin"] = (2 * MB, None)   # every connection 2 MiB/s
        ok, d = _download(srv, "f.bin", tmp_path / "f.bin", segment_size=64 * MB,
                          max_segments=4, spare_slots=lambda: 10)
        peak = srv.max_concurrent
    assert ok
    assert md5((tmp_path / "f.bin").read_bytes()) == md5(data)
    assert d.splits >= 2
    assert 2 <= peak <= 4          # grew, but never past max_segments


def test_no_spare_budget_no_growth(tmp_path, monkeypatch):
    _fast_split(monkeypatch)
    data = os.urandom(2 * MB)
    with MultiFileRangeServer({"f.bin": data}) as srv:
        srv.throttle["f.bin"] = (4 * MB, None)
        ok, d = _download(srv, "f.bin", tmp_path / "f.bin", segment_size=64 * MB,
                          max_segments=4, spare_slots=lambda: 0)
    assert ok and d.splits == 0


def test_interrupted_split_download_resumes_from_its_grown_plan(tmp_path, monkeypatch):
    """A .part.meta written after splits holds the grown plan; a resume reads it
    back (plan_from_meta) and fetches only what is missing."""
    _fast_split(monkeypatch)
    data = os.urandom(8 * MB)
    dest = tmp_path / "f.bin"
    with MultiFileRangeServer({"f.bin": data}) as srv:
        srv.throttle["f.bin"] = (1 * MB, None)   # every connection 1 MiB/s

        async def interrupted():
            async with aiohttp.ClientSession() as s:
                d = SegmentedDownloader(s, srv.url("f.bin"), str(dest),
                                        segment_size=4 * MB, max_segments=4,
                                        spare_slots=lambda: 10)
                task = asyncio.ensure_future(d.download_with_resume())
                await asyncio.sleep(0.8)       # grown to 4 segments, ~3 of 8 MiB in
                task.cancel()
                try:
                    return await task
                except asyncio.CancelledError:
                    return None
        asyncio.run(interrupted())
        meta = json.load(open(str(dest) + ".part.meta"))
        assert len(meta["segments"]) > 2          # the split is in the stored plan
        assert meta["segments"][0][0] == 0 and meta["segments"][-1][1] <= len(data) - 1

        srv.throttle.clear()
        ok, _d = _download(srv, "f.bin", dest, segment_size=4 * MB, max_segments=4)
    assert ok
    assert md5(dest.read_bytes()) == md5(data)
