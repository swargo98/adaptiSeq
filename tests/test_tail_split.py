"""Files that start near the end of a batch are split finer.

Full run, panel 3b: a 1.6 GB file is three 512 MB segments, so the last files of
the batch, and every file fetched again after an md5 mismatch, ran on one to
three connections while ENA would have served 25. The batch now shares the
per-host connection budget among the files still to do, within ``max_segments``.
"""

import asyncio
import hashlib
import json
import os

from adaptiseq.batch import BatchDownloader, DownloadTask
from adaptiseq.engine import segmented
from adaptiseq.engine.seam import SegmentedEngine
from adaptiseq.engine.segmented import (
    SegmentedDownloader,
    calculate_segments,
    plan_from_meta,
)
from adaptiseq.options import Options
from tests.servers import MultiFileRangeServer

MB = 1024 * 1024
GB = 1024 * MB


def test_target_raises_the_split_within_max_segments_and_min_split():
    kw = dict(min_file_size=5 * MB, max_segments=8, segment_size=512 * MB)
    assert len(calculate_segments(int(1.6 * GB), **kw)) == 3
    assert len(calculate_segments(int(1.6 * GB), target_segments=8, **kw)) == 8
    assert len(calculate_segments(int(1.6 * GB), target_segments=40, **kw)) == 8
    # never below 64 MiB a segment
    assert len(calculate_segments(200 * MB, target_segments=8, **kw)) == 3
    # a target below the size-derived count changes nothing
    assert len(calculate_segments(int(1.6 * GB), target_segments=1, **kw)) == 3
    plan = calculate_segments(int(1.6 * GB), target_segments=8, **kw)
    assert plan[0][0] == 0 and plan[-1][1] == int(1.6 * GB) - 1
    assert all(b + 1 == c for (_, b), (c, _) in zip(plan, plan[1:]))


def test_plan_from_meta_accepts_only_a_tiling_of_this_file():
    meta = {"file_size": 100, "segments": [[0, 49], [50, 99]]}
    assert plan_from_meta(meta, 100) == [(0, 49), (50, 99)]
    assert plan_from_meta(meta, 101) is None
    assert plan_from_meta({"file_size": 100, "segments": [[0, 49], [51, 99]]}, 100) is None
    assert plan_from_meta({"file_size": 100, "segments": [[0, 120]]}, 100) is None
    assert plan_from_meta(None, 100) is None
    # a grown plan (splits appended out of byte order) keeps its stored order
    grown = {"file_size": 100, "segments": [[0, 24], [50, 99], [25, 49]]}
    assert plan_from_meta(grown, 100) == [(0, 24), (50, 99), (25, 49)]


def test_resume_keeps_the_plan_it_started_with(tmp_path):
    """A .part.meta from a 2-segment start resumes as 2 segments even when the
    downloader would now split the file 4 ways, so finished bytes are kept."""
    data = os.urandom(8 * MB)
    dest = tmp_path / "f.bin"
    half = len(data) // 2
    with open(str(dest) + ".part", "wb") as f:
        f.write(data[:half])
        f.write(b"\0" * (len(data) - half))
    with open(str(dest) + ".part.meta", "w") as f:
        json.dump({"file_size": len(data), "segments": [[0, half - 1], [half, len(data) - 1]],
                   "completed_indices": [0], "partial_offsets": {}}, f)

    with MultiFileRangeServer({"f.bin": data}) as srv:
        async def main():
            import aiohttp
            async with aiohttp.ClientSession() as s:
                d = SegmentedDownloader(s, srv.url("f.bin"), str(dest), segment_size=MB,
                                        max_segments=4)
                return await d.download()
        assert asyncio.run(main())
        # only the unfinished half was requested again
        assert srv.max_concurrent == 1
    assert hashlib.md5(dest.read_bytes()).hexdigest() == hashlib.md5(data).hexdigest()


class _RecordingEngine:
    def __init__(self):
        self.targets = {}

    async def fetch_async(self, url, save_path, **kwargs):
        self.targets[save_path] = kwargs.get("target_segments")
        await asyncio.sleep(0.01)
        return True


def test_batch_gives_the_last_files_the_spare_connection_budget(tmp_path):
    opts = Options(engine="segmented", quiet=True, adaptive=False, jobs=2, max_segments=8)
    eng = _RecordingEngine()
    tasks = [DownloadTask(f"https://h.example/f{i}", f"f{i}", "ACC") for i in range(6)]
    asyncio.run(BatchDownloader(eng, opts, tmp_path).run(tasks))
    # budget 2 x 8 = 16: early files share it with the whole queue, the last
    # file to start has it to itself (capped by max_segments in the engine)
    assert eng.targets["f0"] == 16 // 6
    assert eng.targets["f5"] >= 16 // 2


def test_batch_splits_a_lone_large_file_finer(tmp_path, monkeypatch):
    monkeypatch.setattr(segmented, "MIN_SPLIT", 4 * MB)
    data = os.urandom(24 * MB)
    with MultiFileRangeServer({"big.bin": data}, delay=0.2) as srv:
        opts = Options(engine="segmented", segment_size=16 * MB, max_segments=6,
                       quiet=True, adaptive=False, jobs=4)
        eng = SegmentedEngine(opts, str(tmp_path))
        failed = asyncio.run(BatchDownloader(eng, opts, tmp_path).run(
            [DownloadTask(srv.url("big.bin"), "big.bin", "ACC")]))
        assert not failed
        # 24 MB / 16 MB alone is one segment; the lone file gets the budget
        # (1 worker x 6 segments) in 4 MB pieces
        assert srv.max_concurrent == 6
    assert (tmp_path / "big.bin").read_bytes() == data
