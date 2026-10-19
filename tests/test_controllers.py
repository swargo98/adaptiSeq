"""The candidate adaptive controllers, ``budget`` and ``greedy`` (--controller).

Neither is the default. ``budget`` steers a per-host connection budget instead
of a worker count; ``greedy`` runs every worker and only backs off on 429/503.
These tests drive each controller against a fake link whose throughput grows
with open connections up to a knee, so the decisions can be checked exactly.
"""

import asyncio
import os

import pytest

from adaptiseq import cli
from adaptiseq.batch import AdaptiveController, BatchDownloader, DownloadTask
from adaptiseq.engine.gate import WorkerGate
from adaptiseq.engine.ratelimit import HostGuard
from adaptiseq.engine.seam import SegmentedEngine
from adaptiseq.options import CONTROLLERS, Options
from tests.servers import MultiFileRangeServer

MB = 1024 * 1024


class FakeLink:
    """Open connections = min(budget, available); Mbps = per_conn x min(conns, knee)."""

    def __init__(self, knee, available=200, per_conn=16.0):
        self.knee, self.available, self.per_conn = knee, available, per_conn
        self.guard = HostGuard(default_cap=160)

    def conns(self):
        return min(self.guard.default_cap, self.available)

    def recent_average(self, n):
        return self.per_conn * min(self.conns(), self.knee)


def _controller(link, mode, jobs=20, pending=lambda: 5):
    gate = WorkerGate(jobs, active=2)
    link.guard.total_in_flight = link.conns
    ctrl = AdaptiveController(gate, link, mode=mode, guard=link.guard, pending=pending,
                              max_workers=lambda: jobs)
    return gate, ctrl


def _run_for(ctrl, seconds):
    async def main():
        task = asyncio.ensure_future(ctrl.run())
        await asyncio.sleep(seconds)
        ctrl.stop()
        await asyncio.wait_for(task, 5)
    asyncio.run(main())


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setenv("ASEQ_BUDGET_WINDOW", "0.02")
    monkeypatch.setenv("ASEQ_BUDGET_SETTLE", "0")
    monkeypatch.setenv("ASEQ_GREEDY_WINDOW", "0.02")


@pytest.mark.parametrize("knee", [12, 30, 70])
def test_budget_settles_near_the_knee(fast, knee):
    link = FakeLink(knee)
    gate, ctrl = _controller(link, "budget")
    seen = []
    orig = link.guard.set_budget
    link.guard.set_budget = lambda n: (seen.append(n), orig(n))[1]
    _run_for(ctrl, 1.5)
    tail = seen[-12:]
    # it keeps probing around the knee, never far from it
    assert min(tail) >= 0.6 * knee and max(tail) <= 1.6 * knee + 2, (knee, seen)
    assert gate.active == 20                    # every worker stays active
    assert "connection(s)" in ctrl.summary()


def test_budget_cuts_on_pushback(fast):
    link = FakeLink(knee=100)
    gate, ctrl = _controller(link, "budget")
    seen = []
    orig = link.guard.set_budget
    link.guard.set_budget = lambda n: (seen.append(n), orig(n))[1]

    async def main():
        task = asyncio.ensure_future(ctrl.run())
        await asyncio.sleep(0.3)
        mark = len(seen)
        link.guard.trips.append(("h", "429", 1.0))
        await asyncio.sleep(0.1)
        ctrl.stop()
        await asyncio.wait_for(task, 5)
        return mark
    mark = asyncio.run(main())
    after = seen[mark - 1:]
    assert any(b <= int(a * 0.7) for a, b in zip(after, after[1:])), seen


def test_budget_does_not_judge_the_tail(fast):
    link = FakeLink(knee=100)
    gate, ctrl = _controller(link, "budget", pending=lambda: 0)
    start = link.guard.default_cap
    _run_for(ctrl, 0.4)
    assert link.guard.default_cap == 40 or link.guard.default_cap == start


def test_greedy_runs_every_worker_and_backs_off_on_429(fast):
    link = FakeLink(knee=100)
    gate, ctrl = _controller(link, "greedy")
    seen = []
    orig = gate.set_active
    gate.set_active = lambda w: (seen.append(w), orig(w))[1]

    async def main():
        task = asyncio.ensure_future(ctrl.run())
        await asyncio.sleep(0.1)
        mark = len(seen)
        link.guard.trips.append(("h", "503", 1.0))
        await asyncio.sleep(0.5)
        ctrl.stop()
        await asyncio.wait_for(task, 5)
        return mark
    mark = asyncio.run(main())
    assert seen[0] == 20 and set(seen[:mark]) == {20}
    assert min(seen[mark:]) <= 15 and seen[-1] == 20


def test_controller_option_validates_and_reaches_the_cli():
    assert set(CONTROLLERS) == {"topdown", "bottomup", "budget", "greedy"}
    with pytest.raises(ValueError):
        Options(controller="nope")
    assert Options().controller is None          # default unchanged: topdown
    p = cli.build_parser()
    assert p.parse_args(["-i", "SRR1", "--controller", "budget"]).controller == "budget"
    assert p.parse_args(["-i", "SRR1"]).controller is None
    with pytest.raises(SystemExit):
        p.parse_args(["-i", "SRR1", "--controller", "nope"])


@pytest.mark.parametrize("mode", ["budget", "greedy"])
def test_batch_downloads_correctly_under_each_candidate(tmp_path, monkeypatch, fast, mode):
    files = {f"f{i}.bin": os.urandom(3 * MB) for i in range(6)}
    with MultiFileRangeServer(files, delay=0.05) as srv:
        opts = Options(engine="segmented", segment_size=MB, max_segments=3, quiet=True,
                       adaptive=True, jobs=4, controller=mode)
        bd = BatchDownloader(SegmentedEngine(opts, str(tmp_path)), opts, tmp_path)
        failed = asyncio.run(bd.run([DownloadTask(srv.url(n), n, "ACC") for n in files]))
    assert not failed
    for n, b in files.items():
        assert (tmp_path / n).read_bytes() == b
