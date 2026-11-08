"""A segment that runs out of attempts but made progress continues in the same pass.

0.1.12 check, GSA panel (2026-10-22): download.cncb.ac.cn cut about 80 streams in
6 minutes; each segment that used up its 3 attempts stopped its file's splitting
for the rest of the pass, so the last 2-3 minutes ran on about 4 connections
before the files were queued again. Now such a segment continues from where it
stopped on a new connection; one that keeps failing without progress still ends
the pass, as before.
"""

import asyncio
import os

import aiohttp

from adaptiseq.engine import segmented
from adaptiseq.engine.ratelimit import HostGuard
from adaptiseq.engine.segmented import SegmentedDownloader
from tests.servers import MultiFileRangeServer

MB = 1024 * 1024


def _download(srv, tmp_path, name, **kw):
    async def main():
        async with aiohttp.ClientSession() as s:
            d = SegmentedDownloader(s, srv.url(name), str(tmp_path / name),
                                    segment_size=64 * MB, max_segments=1,
                                    host_guard=HostGuard(default_cap=16), **kw)
            ok = await d.download()
            return ok, d
    return asyncio.run(main())


def test_more_cuts_than_attempts_still_finish_in_one_pass(tmp_path):
    data = os.urandom(4 * MB)
    with MultiFileRangeServer({"f.bin": data}) as srv:
        srv.short["f.bin"] = 7          # each cut delivers half of what was asked
        ok, d = _download(srv, tmp_path, "f.bin")
    assert ok                            # 0.1.11: False after the 3rd cut
    assert d.relaunches >= 2
    assert (tmp_path / "f.bin").read_bytes() == data


def test_a_segment_that_never_progresses_still_ends_the_pass(tmp_path, monkeypatch):
    data = os.urandom(4 * MB)
    calls = []

    async def no_progress(self, segment_id, start, end, fd, progress_offsets):
        calls.append(start)
        progress_offsets[segment_id] = start
        raise RuntimeError("server keeps failing")

    monkeypatch.setattr(SegmentedDownloader, "download_segment_streaming", no_progress)
    with MultiFileRangeServer({"g.bin": data}) as srv:
        ok, d = _download(srv, tmp_path, "g.bin")
    assert not ok
    # the first task, then RELAUNCH_STALLS - 1 relaunches without progress
    assert len(calls) == segmented.RELAUNCH_STALLS
    assert d.relaunches == segmented.RELAUNCH_STALLS - 1
