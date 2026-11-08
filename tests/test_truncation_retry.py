"""Cut-short responses are counted, and a failing file that makes progress keeps
its place in the pool.

Tournament rep 1, GSA panel (0.1.8, greedy controller, about 40 connections):
download.cncb.ac.cn cut 95 responses short in 28 minutes, 13 segments ran out of
their 3 attempts, and the last files ran on one or two connections. Now each
cut-short response is recorded (HostGuard kind "truncated", for the budget
controller), a pass that moved the file's resume point does not use up one of
its three retries, and a file fetched on its own may split onto spare
connections.
"""

import asyncio
import json
import os

import aiohttp

from adaptiseq import batch as batch_mod
from adaptiseq.batch import AdaptiveController, BatchDownloader, DownloadTask
from adaptiseq.engine import segmented
from adaptiseq.engine.gate import WorkerGate
from adaptiseq.engine.ratelimit import HostGuard
from adaptiseq.engine.seam import SegmentedEngine
from adaptiseq.engine.segmented import SegmentedDownloader
from adaptiseq.options import Options
from tests.servers import MultiFileRangeServer
from tests.test_controllers import FakeLink, _controller

MB = 1024 * 1024


def test_cut_short_response_is_recorded_and_retried(tmp_path):
    data = os.urandom(4 * MB)
    guard = HostGuard(default_cap=16)
    with MultiFileRangeServer({"f.bin": data}) as srv:
        srv.short["f.bin"] = 2

        async def main():
            async with aiohttp.ClientSession() as s:
                d = SegmentedDownloader(s, srv.url("f.bin"), str(tmp_path / "f.bin"),
                                        segment_size=MB, max_segments=4, host_guard=guard)
                return await d.download()
        assert asyncio.run(main())
    assert (tmp_path / "f.bin").read_bytes() == data
    assert sum(1 for _h, k, _d in guard.trips if k == "truncated") == 2
    assert all(st.cap == 16 for st in guard._hosts.values())   # recorded, cap untouched


def test_budget_backs_off_on_a_storm_of_cut_streams(monkeypatch):
    monkeypatch.setenv("ASEQ_BUDGET_WINDOW", "0.02")
    monkeypatch.setenv("ASEQ_BUDGET_SETTLE", "0")
    link = FakeLink(knee=100)
    gate, ctrl = _controller(link, "budget")
    seen = []
    orig = link.guard.set_budget
    link.guard.set_budget = lambda n: (seen.append(n), orig(n))[1]

    async def main():
        task = asyncio.ensure_future(ctrl.run())
        await asyncio.sleep(0.3)
        mark = len(seen)
        link.guard.trips.extend([("h", "truncated", 0.0)] * 3)
        await asyncio.sleep(0.1)
        ctrl.stop()
        await asyncio.wait_for(task, 5)
        return mark
    mark = asyncio.run(main())
    after = seen[mark - 1:]
    assert any(b <= int(a * 0.7) for a, b in zip(after, after[1:])), seen


class _ProgressingEngine:
    """Fails ``fails`` times, each time recording more bytes done in .part.meta."""

    def __init__(self, workdir, fails):
        self.workdir, self.fails, self.calls = workdir, fails, 0

    async def fetch_async(self, url, save_path, **kw):
        self.calls += 1
        meta = self.workdir / (save_path + ".part.meta")
        if self.calls <= self.fails:
            json.dump({"file_size": 100, "segments": [[0, 99]], "completed_indices": [],
                       "partial_offsets": {"0": self.calls * 4}}, open(meta, "w"))
            return False
        (self.workdir / save_path).write_bytes(b"x" * 100)
        return True


def test_progress_does_not_use_up_retries(tmp_path):
    eng = _ProgressingEngine(tmp_path, fails=6)
    opts = Options(quiet=True, adaptive=False, jobs=1)
    failed = asyncio.run(BatchDownloader(eng, opts, tmp_path).run(
        [DownloadTask("https://h.example/f", "f", "ACC")]))
    assert not failed and eng.calls == 7


def test_no_progress_still_fails_after_three(tmp_path):
    class Stuck:
        calls = 0

        async def fetch_async(self, url, save_path, **kw):
            Stuck.calls += 1
            return False
    opts = Options(quiet=True, adaptive=False, jobs=1)
    failed = asyncio.run(BatchDownloader(Stuck(), opts, tmp_path).run(
        [DownloadTask("https://h.example/f", "f", "ACC")]))
    assert failed == {"f"} and Stuck.calls == 3


def test_a_lone_file_splits_onto_spare_connections(tmp_path, monkeypatch):
    monkeypatch.setattr(segmented, "MIN_STEAL", 128 * 1024)
    monkeypatch.setattr(segmented, "SPLIT_POLL_S", 0.05)
    data = os.urandom(4 * MB)
    with MultiFileRangeServer({"f.bin": data}) as srv:
        srv.throttle["f.bin"] = (2 * MB, None)
        opts = Options(engine="segmented", segment_size=64 * MB, max_segments=4, quiet=True)
        assert SegmentedEngine(opts, str(tmp_path)).fetch(srv.url("f.bin"), "f.bin")
        assert srv.max_concurrent >= 2
    assert (tmp_path / "f.bin").read_bytes() == data
