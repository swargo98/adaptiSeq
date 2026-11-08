"""A ``.part.meta`` that outlives its ``.part`` must never be resumed from.

Gate job 54902879 (Expanse, 2026-10-14), panel 3b: SRR15852411 failed its md5
check on three separate downloads. Looking for a way adaptiSeq itself could
write wrong bytes turned up this one: resume state is kept in two files, and
the single-connection path finalised ``.part`` without removing ``.part.meta``.
If the md5 check then deleted the final file (as ``check_sra`` does before a
retry), the next download read the stale metadata, opened a new empty ``.part``,
fetched only the segments it listed as unfinished, and renamed a file with a
hole of zeros. Whether this is what happened in the gate is not known; it is a
bug either way.
"""

import asyncio
import hashlib
import os

import aiohttp

from adaptiseq.engine import segmented as S
from tests.servers import RangeServer

SEG = 1024 * 1024


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


async def _download(url, dest, pause=None):
    async with aiohttp.ClientSession() as sess:
        d = S.SegmentedDownloader(
            sess, url, dest, segment_size=SEG, max_segments=4,
            min_file_size_for_segmentation=SEG, pause=pause,
        )
        return await d.download()


def test_partial_meta_without_part_restarts(tmp_path):
    data = os.urandom(4 * SEG + 77)
    dest = str(tmp_path / "file.bin")
    d = S.SegmentedDownloader(None, "http://x/file.bin", dest, segment_size=SEG,
                              max_segments=4, min_file_size_for_segmentation=SEG)
    segments = d.calculate_segments(len(data))
    # metadata says segments 0 and 1 are done, but there is no .part
    d.write_metadata(len(data), segments, {0, 1}, {2: segments[2][0] + 100})

    with RangeServer(data) as srv:
        ok = asyncio.run(_download(srv.url(), dest))

    assert ok is True
    assert md5((tmp_path / "file.bin").read_bytes()) == md5(data)
    assert not (tmp_path / "file.bin.part.meta").exists()


def test_single_connection_clears_meta_and_redownload_is_whole(tmp_path):
    data = os.urandom(4 * SEG + 77)
    dest = str(tmp_path / "file.bin")

    class StopAfter:
        def __init__(self, n):
            self.n, self.calls = n, 0

        def should_continue(self):
            self.calls += 1
            return self.calls <= self.n

    with RangeServer(data) as srv:
        # 1. a segmented attempt that stops part way: .part + .part.meta remain
        assert asyncio.run(_download(srv.url(), dest, pause=StopAfter(3))) is False
        assert (tmp_path / "file.bin.part.meta").exists()

    with RangeServer(data, force_200=True) as srv:
        # 2. the retry finds no range support and completes on one connection
        assert asyncio.run(_download(srv.url(), dest)) is True
    assert md5((tmp_path / "file.bin").read_bytes()) == md5(data)
    assert not (tmp_path / "file.bin.part.meta").exists()

    # 3. the md5 check deletes the file and asks for a fresh download
    os.remove(dest)
    with RangeServer(data) as srv:
        assert asyncio.run(_download(srv.url(), dest)) is True
    assert md5((tmp_path / "file.bin").read_bytes()) == md5(data)

