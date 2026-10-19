"""A range probe with no answer is retried, not read as "no ranges".

0.1.6 check (55063970), panel 3b: ENA refused a few ``Range: bytes=0-0`` probes,
each was reported as "server has no ranges", and five 1.5 to 2 GB files then
downloaded over a single connection for 15 to 30 min each. Now the probe takes a
host slot, waits at the connection ceiling, retries, and raises ``ProbeError`` if
it never gets an answer; transport selection still falls back to FTP when HTTPS
gives no answer at all.
"""

import asyncio
import hashlib
import os
import socket

import aiohttp
import pytest

from adaptiseq.engine import seam as seam_mod
from adaptiseq.engine import segmented
from adaptiseq.engine.seam import SegmentedEngine
from adaptiseq.engine.segmented import ProbeError, SegmentedDownloader
from adaptiseq.options import Options
from tests.servers import MultiFileRangeServer

MB = 1024 * 1024


def test_dropped_probe_is_retried_and_the_file_still_segmented(tmp_path):
    data = os.urandom(8 * MB)
    with MultiFileRangeServer({"f.bin": data}, delay=0.1) as srv:
        srv.drop["f.bin"] = 1          # the first request (the probe) gets no answer

        async def main():
            async with aiohttp.ClientSession() as s:
                d = SegmentedDownloader(s, srv.url("f.bin"), str(tmp_path / "f.bin"),
                                        segment_size=2 * MB, max_segments=4)
                return await d.download()
        assert asyncio.run(main())
        starts = sorted(a for n, a in srv.range_starts if n == "f.bin" and a > 0)
    assert hashlib.md5((tmp_path / "f.bin").read_bytes()).digest() == hashlib.md5(data).digest()
    # segmented (ranges from 2, 4, 6 MiB), not one single-stream GET
    assert starts[:3] == [2 * MB, 4 * MB, 6 * MB]


def test_probe_with_no_answer_raises(monkeypatch):
    monkeypatch.setattr(segmented, "PROBE_ATTEMPTS", 2)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    async def main():
        async with aiohttp.ClientSession() as sess:
            d = SegmentedDownloader(sess, f"http://127.0.0.1:{port}/x", "/dev/null")
            await d.probe_range_support()
    with pytest.raises(ProbeError):
        asyncio.run(main())


def test_transport_selection_falls_back_when_https_never_answers(monkeypatch, tmp_path):
    async def no_answer(self):
        raise ProbeError("x")

    async def no_ftp(host, port, path):
        return None, False, False

    monkeypatch.setattr(segmented.SegmentedDownloader, "probe_range_support", no_answer)
    monkeypatch.setattr(seam_mod, "probe_ftp", no_ftp)
    eng = SegmentedEngine(Options(quiet=True), str(tmp_path))

    async def main():
        async with aiohttp.ClientSession() as s:
            return await eng._probe_ftp_kind("ftp://h.example/x.fastq.gz", s)
    assert asyncio.run(main()) == "http-single"
