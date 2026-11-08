"""Topdown measures a worker count only once the pool has reached it.

Round 2 panel 4r (2026-10-20/21): the gate acts only at file pickup, so right
after a step down the files started at the higher count were still running and
the lower count read their throughput; topdown stepped down on that (20w@27,
10w@73, 5w@122 Mbps) and committed at 2-5 workers while 20-50 connections won.
Also: a file running while the controller holds others back in the queue may
use the spare connection budget (panel 4m: the GSA tail on one connection).
"""

import asyncio
import time

import pytest

from adaptiseq.batch import AdaptiveController, BatchDownloader, DownloadTask
from adaptiseq.engine.gate import WorkerGate
from adaptiseq.engine.ratelimit import HostGuard
from adaptiseq.options import Options


class LagPool:
    """Files in flight follow the gate up at once and down after ``lag`` s
    (None: never within the test, like 1.6 GB files); Mbps = f(in flight),
    scaled down for ``ramp`` s after the pool grows (new files still connecting)."""

    def __init__(self, gate, f, lag, ramp=0.0):
        self.gate, self.f, self.lag, self.ramp = gate, f, lag, ramp
        self.n = gate.active
        self.target, self.since = gate.active, time.monotonic()
        self.grew = time.monotonic()

    def in_flight(self):
        a = self.gate.active
        if a != self.target:
            self.target, self.since = a, time.monotonic()
        if a > self.n:
            self.n, self.grew = a, time.monotonic()
        elif a < self.n and self.lag is not None and time.monotonic() - self.since >= self.lag:
            self.n = a
        return self.n

    def recent_average(self, k):
        n = self.in_flight()
        warm = 1.0
        if self.ramp:
            warm = min(1.0, max(0.1, (time.monotonic() - self.grew) / self.ramp))
        return self.f(n) * warm


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setenv("ASEQ_PROBE_WINDOW", "0.02")
    monkeypatch.setenv("ASEQ_TOPDOWN_SETTLE", "0")
    monkeypatch.setenv("ASEQ_TOPDOWN_DRAIN_S", "0.3")
    monkeypatch.setenv("ASEQ_TOPDOWN_SETTLE_UP", "0.25")
    monkeypatch.setenv("ASEQ_EXPLOIT_REPROBE_S", "30")


def _run(jobs, f, lag, seconds=1.5, ramp=0.0, pool_count=True):
    gate = WorkerGate(jobs, active=2)
    pool = LagPool(gate, f, lag, ramp)
    ctrl = AdaptiveController(gate, pool, mode="topdown", max_workers=lambda: jobs,
                              pending=lambda: 100,
                              in_flight=pool.in_flight if pool_count else None)

    async def main():
        task = asyncio.ensure_future(ctrl.run())
        await asyncio.sleep(seconds)
        ctrl.stop()
        await asyncio.wait_for(task, 5)
    asyncio.run(main())
    return gate.active, ctrl


def test_more_files_faster_holds_the_cap(fast):
    # ENA: about 2 MB/s per connection, so more files in flight is faster. The
    # first reading at the cap falls in the ramp-up and the files drain 0.1 s
    # after a step down: the round-2 panel-4r shape.
    active, _ = _run(20, lambda n: 16.0 * n, lag=0.1, ramp=0.2)
    assert active == 20


def test_the_old_ladder_stepped_down_on_the_same_link(fast, monkeypatch):
    # The same link, measured the 0.1.11 way (no pool count, no ramp settle).
    monkeypatch.setenv("ASEQ_TOPDOWN_SETTLE_UP", "0")
    active, _ = _run(20, lambda n: 16.0 * n, lag=0.1, ramp=0.2, pool_count=False)
    assert active < 20


def test_files_that_do_not_drain_keep_the_higher_count(fast):
    # 1.6 GB files: no clean reading at the lower count, so no step down even
    # though the (stale) meter would say lower is better.
    active, _ = _run(8, lambda n: 500.0 - 40 * n, lag=None)
    assert active == 8


def test_real_throttling_still_walks_down(fast):
    # A server that slows down with more files: fewer is better at every step.
    active, _ = _run(16, lambda n: 100.0 - 4 * n, lag=0.0)
    assert active <= 4


def test_without_a_pool_count_topdown_behaves_as_before(fast):
    # Callers that pass no in_flight (aspera, older embedders) are unaffected.
    gate = WorkerGate(16, active=2)
    pool = LagPool(gate, lambda n: 100.0 - 4 * n, lag=0.0)
    ctrl = AdaptiveController(gate, pool, mode="topdown", max_workers=lambda: 16,
                              pending=lambda: 100)

    async def main():
        task = asyncio.ensure_future(ctrl.run())
        await asyncio.sleep(1.0)
        ctrl.stop()
        await asyncio.wait_for(task, 5)
    asyncio.run(main())
    assert gate.active <= 4


def _downloader(tmp_path, jobs=20):
    return BatchDownloader(engine=None, options=Options(quiet=True, jobs=jobs),
                           workdir=tmp_path)


def test_spare_budget_offered_while_the_controller_holds_files_back(tmp_path):
    bd = _downloader(tmp_path)
    queue = asyncio.Queue()
    queue.put_nowait(DownloadTask("https://download.cncb.ac.cn/a", "a", "CRR1"))
    task = DownloadTask("https://download.cncb.ac.cn/b", "b", "CRR2")
    guard = HostGuard(default_cap=40)
    gate = WorkerGate(20, active=1)          # topdown at 1 worker
    bd._in_flight = 1                        # ... and that worker is busy
    assert bd._spare_slots(queue, guard, task, gate)() == 40


def test_no_spare_while_a_free_worker_can_start_the_next_file(tmp_path):
    bd = _downloader(tmp_path)
    queue = asyncio.Queue()
    queue.put_nowait(DownloadTask("https://download.cncb.ac.cn/a", "a", "CRR1"))
    task = DownloadTask("https://download.cncb.ac.cn/b", "b", "CRR2")
    guard = HostGuard(default_cap=40)
    held = WorkerGate(20, active=4)
    bd._in_flight = 2                        # 2 of 4 active workers are free
    assert bd._spare_slots(queue, guard, task, held)() == 0
    full = WorkerGate(20, active=20)         # fixed -j: unchanged behaviour
    bd._in_flight = 20
    assert bd._spare_slots(queue, guard, task, full)() == 0
