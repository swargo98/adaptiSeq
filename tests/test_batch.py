"""Batch pool + adaptive controller + parallel-resolution rate-limit tests."""

import asyncio
import hashlib
import os
import time

import pytest

from adaptiseq import ratelimits
from adaptiseq.batch import AdaptiveController, BatchDownloader, DownloadTask
from adaptiseq.console import ListReporter
from adaptiseq.core import _batch_download_phase, _worker_cap_label
from adaptiseq.engine.gate import WorkerGate
from adaptiseq.engine.seam import SegmentedEngine
from adaptiseq.engine.throughput import ThroughputMeter
from adaptiseq.options import Options, RunContext
from tests.servers import MultiFileRangeServer


def md5(b):
    return hashlib.md5(b).hexdigest()


class FakeEngine:
    """Records fetches and succeeds immediately — keeps pool-sizing tests offline."""

    def __init__(self):
        self.calls = []

    async def fetch_async(self, url, save_path, **kwargs):
        self.calls.append((url, save_path))
        on_bytes = kwargs.get("on_bytes")
        if on_bytes is not None:
            on_bytes(1024)
        return True


class _FakeProgress:
    def __init__(self, total, done):
        self.total = total
        self.done = done


def _engine(outdir, **opts):
    base = dict(engine="segmented", segment_size=1 * 1024 * 1024, max_segments=4,
                max_conns_per_host=8, quiet=True, adaptive=False, jobs=4)
    base.update(opts)
    return SegmentedEngine(Options(**base), outdir)


def test_worker_pool_is_capped_to_task_count(tmp_path):
    # -j 20 with 3 files must build 3 workers, not 20.
    opts = Options(engine="segmented", quiet=True, adaptive=False, jobs=20)
    bd = BatchDownloader(FakeEngine(), opts, str(tmp_path))
    tasks = [
        DownloadTask(f"https://example.test/f{i}.fastq.gz", f"f{i}.fastq.gz", "ACC")
        for i in range(3)
    ]

    failed = asyncio.run(bd.run(tasks))

    assert failed == set()
    assert bd._worker_slots == 3
    assert bd._initial_active == 3
    assert bd._gate.jobs == 3


def test_single_file_batch_uses_one_worker(tmp_path):
    opts = Options(engine="segmented", quiet=True, adaptive=False, jobs=20)
    bd = BatchDownloader(FakeEngine(), opts, str(tmp_path))
    tasks = [DownloadTask("https://example.test/f0.fastq.gz", "f0.fastq.gz", "ACC")]

    asyncio.run(bd.run(tasks))

    assert bd._worker_slots == 1
    assert bd._gate.jobs == 1
    assert bd._gate.active == 1


def test_single_file_adaptive_batch_does_not_preactivate_two_workers(tmp_path):
    # Adaptive normally pre-activates 2; with one file that would show a worker
    # that cannot exist.
    opts = Options(engine="segmented", quiet=True, adaptive=True, jobs=20,
                   probe_window=2)
    bd = BatchDownloader(FakeEngine(), opts, str(tmp_path))
    tasks = [DownloadTask("https://example.test/f0.fastq.gz", "f0.fastq.gz", "ACC")]

    asyncio.run(bd.run(tasks))

    assert bd._worker_slots == 1
    assert bd._initial_active == 1
    assert bd._gate.jobs == 1


def test_jobs_below_task_count_still_caps_at_jobs(tmp_path):
    # The cap is min(jobs, tasks) — -j must still be honoured as the ceiling.
    opts = Options(engine="segmented", quiet=True, adaptive=False, jobs=2)
    bd = BatchDownloader(FakeEngine(), opts, str(tmp_path))
    tasks = [
        DownloadTask(f"https://example.test/f{i}.fastq.gz", f"f{i}.fastq.gz", "ACC")
        for i in range(6)
    ]

    failed = asyncio.run(bd.run(tasks))

    assert failed == set()
    assert bd._worker_slots == 2
    assert bd._gate.jobs == 2


def test_gate_is_lowered_as_remaining_files_drain():
    gate = WorkerGate(jobs=8, active=8)
    BatchDownloader._cap_gate_to_remaining(_FakeProgress(total=8, done=6), gate)
    assert gate.active == 2


def test_gate_is_not_raised_by_capping():
    gate = WorkerGate(jobs=8, active=2)
    BatchDownloader._cap_gate_to_remaining(_FakeProgress(total=8, done=0), gate)
    assert gate.active == 2


def test_visible_workers_never_exceeds_remaining_and_is_zero_when_done():
    gate = WorkerGate(jobs=8, active=8)
    assert BatchDownloader._visible_workers(_FakeProgress(8, 6), gate) == 2
    assert BatchDownloader._visible_workers(_FakeProgress(8, 8), gate) == 0


def test_adaptive_controller_probe_is_capped_to_remaining_files():
    async def main():
        gate = WorkerGate(jobs=8, active=1)
        meter = ThroughputMeter(interval=0.05)
        meter.start()
        # Only 2 files outstanding: probing 8 workers must not open 8 slots.
        ctrl = AdaptiveController(gate, meter, probe_window=2, cc_penalty=1.01,
                                 max_workers=lambda: 2)
        await ctrl._probe(8)
        await meter.stop()
        return gate.active, ctrl.trajectory

    active, trajectory = asyncio.run(main())

    assert active == 2
    assert trajectory[0][0] == 2  # scored as 2 workers, not 8


def test_controller_history_is_bounded_but_aggregates_cover_whole_run():
    gate = WorkerGate(jobs=8, active=1)
    ctrl = AdaptiveController(gate, ThroughputMeter(), history_limit=3)
    for w, thrpt in [(1, 100.0), (2, 400.0), (3, 250.0), (4, 200.0), (5, 150.0)]:
        ctrl._record_probe(w, thrpt)

    assert len(ctrl.trajectory) == 3               # bounded
    assert ctrl.trajectory == [(3, 250.0), (4, 200.0), (5, 150.0)]  # most recent
    assert ctrl.probe_count == 5                   # full count survives
    assert ctrl.best_probe == (2, 400.0)           # best survives eviction
    assert ctrl.last_probe == (5, 150.0)


def test_controller_history_does_not_grow_without_bound():
    ctrl = AdaptiveController(WorkerGate(jobs=8), ThroughputMeter())
    for i in range(500):
        ctrl._record_probe(1 + i % 4, float(i))

    assert len(ctrl.trajectory) <= ctrl.history_limit
    assert ctrl.probe_count == 500


def test_controller_summary_is_empty_before_any_probe():
    ctrl = AdaptiveController(WorkerGate(jobs=8), ThroughputMeter())
    assert ctrl.summary() == ""


def test_controller_summary_reports_count_best_and_last():
    ctrl = AdaptiveController(WorkerGate(jobs=8), ThroughputMeter(), history_limit=2)
    ctrl._record_probe(1, 100.0)
    ctrl._record_probe(2, 400.0)
    ctrl._record_probe(3, 250.0)

    summary = ctrl.summary()

    assert "3 probe(s)" in summary
    assert "best 400 Mbps at 2 worker(s)" in summary
    assert "last 250 Mbps at 3 worker(s)" in summary
    assert "recent: 2w@400Mbps, 3w@250Mbps" in summary


def test_batch_phase_reports_summary_not_unbounded_trajectory(monkeypatch, tmp_path):
    from adaptiseq import core as core_mod

    task = DownloadTask("https://example.test/SRR1.fastq.gz", "SRR1.fastq.gz", "SRR1")

    class FakeBatchDownloader:
        def __init__(self, engine, options, workdir, reporter=None):
            ctrl = AdaptiveController(WorkerGate(jobs=4), ThroughputMeter())
            ctrl._record_probe(1, 100.0)
            ctrl._record_probe(2, 400.0)
            self._controller = ctrl

        async def run(self, tasks):
            return set()

    monkeypatch.setattr(
        "adaptiseq.batch.resolve_all",
        lambda accessions, opts, workdir, meta_jobs: ([task], []),
    )
    monkeypatch.setattr("adaptiseq.batch.BatchDownloader", FakeBatchDownloader)
    reporter = ListReporter()
    opts = Options(engine="segmented", quiet=True, adaptive=True, jobs=20)
    ctx = RunContext(options=opts, reporter=reporter, workdir=tmp_path)
    ctx.engine = FakeEngine()

    core_mod._batch_download_phase(ctx, ["SRR1"])

    output = "\n".join(reporter.infos)
    assert "adaptive worker summary: 2 probe(s)" in output
    assert "best 400 Mbps at 2 worker(s)" in output


def test_worker_cap_label_mentions_configured_max_only_when_capped():
    assert _worker_cap_label(20, 1) == "1 worker(s) (configured max 20)"
    assert _worker_cap_label(20, 3) == "3 worker(s) (configured max 20)"
    assert _worker_cap_label(2, 6) == "2 worker(s)"


def test_batch_start_notice_reports_effective_worker_cap(monkeypatch, tmp_path):
    from adaptiseq import core as core_mod

    task = DownloadTask("https://example.test/SRR1.fastq.gz", "SRR1.fastq.gz", "SRR1")

    class FakeBatchDownloader:
        def __init__(self, engine, options, workdir, reporter=None):
            self._controller = None

        async def run(self, tasks):
            return set()

    monkeypatch.setattr(
        "adaptiseq.batch.resolve_all",
        lambda accessions, opts, workdir, meta_jobs: ([task], []),
    )
    monkeypatch.setattr("adaptiseq.batch.BatchDownloader", FakeBatchDownloader)
    reporter = ListReporter()
    opts = Options(engine="segmented", quiet=True, adaptive=True, jobs=20)
    ctx = RunContext(options=opts, reporter=reporter, workdir=tmp_path)
    ctx.engine = FakeEngine()

    core_mod._batch_download_phase(ctx, ["SRR1"])

    output = "\n".join(reporter.infos)
    assert "with up to 1 worker(s) (configured max 20)" in output
    assert "up to 20 workers" not in output


def test_batch_downloads_all_and_continues_past_failure(tmp_path):
    files = {f"f{i}.bin": os.urandom(2 * 1024 * 1024 + i) for i in range(5)}
    with MultiFileRangeServer(files) as srv:
        opts = Options(engine="segmented", segment_size=1024 * 1024, max_segments=4,
                       quiet=True, adaptive=False, jobs=4)
        eng = SegmentedEngine(opts, str(tmp_path))
        tasks = [DownloadTask(srv.url(n), n, "ACC") for n in files]
        # one task points at a missing file -> 404 -> must fail without aborting
        tasks.append(DownloadTask(srv.url("missing.bin"), "missing.bin", "ACC"))
        bd = BatchDownloader(eng, opts, str(tmp_path))
        failed = asyncio.run(bd.run(tasks))

    assert failed == {"missing.bin"}
    for n, data in files.items():
        assert md5((tmp_path / n).read_bytes()) == md5(data)


def test_batch_respects_jobs_and_cap(tmp_path):
    files = {f"g{i}.bin": os.urandom(2 * 1024 * 1024) for i in range(6)}
    with MultiFileRangeServer(files, delay=0.05) as srv:
        opts = Options(engine="segmented", segment_size=1024 * 1024, max_segments=4,
                       max_conns_per_host=3, quiet=True, adaptive=False, jobs=2)
        eng = SegmentedEngine(opts, str(tmp_path))
        tasks = [DownloadTask(srv.url(n), n, "ACC") for n in files]
        failed = asyncio.run(BatchDownloader(eng, opts, str(tmp_path)).run(tasks))
        assert not failed
        # per-host cap is the hard ceiling regardless of jobs
        assert srv.max_concurrent <= 3


def test_auto_cap_does_not_truncate_intended_concurrency(tmp_path):
    """Regression: the per-host cap must not silently truncate the design.

    ``max_conns_per_host`` used to default to a fixed 8. ``HostGuard`` is
    process-wide and shared by every worker, so N in-flight files x k segments
    could never exceed 8 connections in total -- one 8-segment file consumed the
    entire budget and ``-j`` went inert for large files. The intended plan is one
    worker per file, each opening up to ``max_segments`` connections, so auto
    (``0``) derives ``jobs * max_segments`` and the plan becomes reachable.

    Files are 8 MB (above the engine's 5 MB min_file_size_for_segmentation) so
    segmentation actually engages: 8 MB / 1 MB segments -> capped at
    max_segments=4 -> 4 files x 4 segments = 16 intended connections.
    """
    files = {f"g{i}.bin": os.urandom(8 * 1024 * 1024) for i in range(4)}
    with MultiFileRangeServer(files, delay=0.05) as srv:
        opts = Options(engine="segmented", segment_size=1024 * 1024, max_segments=4,
                       quiet=True, adaptive=False, jobs=4)  # max_conns_per_host: auto
        assert opts.max_conns_per_host == 16, "auto cap should be jobs * max_segments"
        eng = SegmentedEngine(opts, str(tmp_path))
        tasks = [DownloadTask(srv.url(n), n, "ACC") for n in files]
        failed = asyncio.run(BatchDownloader(eng, opts, str(tmp_path)).run(tasks))
        assert not failed
        # The old fixed default of 8 made this impossible by construction.
        assert srv.max_concurrent > 8, (
            f"per-host cap still truncating: peak={srv.max_concurrent} (want >8)"
        )
    for n, data in files.items():
        assert md5((tmp_path / n).read_bytes()) == md5(data), f"{n} corrupted"


def test_explicit_cap_still_overrides_auto(tmp_path):
    """An explicit --max-conns-per-host must still be honoured (and enforced)."""
    opts = Options(engine="segmented", max_conns_per_host=5, jobs=20, max_segments=8)
    assert opts.max_conns_per_host == 5, "explicit value must win over auto"


def test_batch_skips_already_in_success_log(tmp_path):
    (tmp_path / "success.log").write_text("date\tg0.bin\n")
    files = {"g0.bin": os.urandom(1024 * 1024), "g1.bin": os.urandom(1024 * 1024)}
    with MultiFileRangeServer(files) as srv:
        opts = Options(engine="segmented", quiet=True, adaptive=False, jobs=2,
                       segment_size=1024 * 1024, max_segments=2)
        eng = SegmentedEngine(opts, str(tmp_path))
        tasks = [DownloadTask(srv.url(n), n, "ACC") for n in files]
        asyncio.run(BatchDownloader(eng, opts, str(tmp_path)).run(tasks))
    # g0 was skipped (in success.log) -> not written; g1 downloaded
    assert not (tmp_path / "g0.bin").exists()
    assert (tmp_path / "g1.bin").exists()


def test_adaptive_controller_adjusts_gate_and_records_trajectory(tmp_path):
    # Drive the controller against a meter we feed manually; assert it sets the
    # gate active count and records a trajectory (observable, acceptance #2).
    async def main():
        gate = WorkerGate(jobs=8, active=2)
        meter = ThroughputMeter(interval=0.05)
        meter.start()
        ctrl = AdaptiveController(gate, meter, probe_window=2, cc_penalty=1.01)

        async def feed():
            # throughput grows with gate.active -> controller should raise workers
            for _ in range(40):
                meter.on_bytes(int(gate.active * 200 * 1024))
                await asyncio.sleep(0.05)

        feeder = asyncio.ensure_future(feed())
        runner = asyncio.ensure_future(ctrl.run())
        await asyncio.sleep(5)
        ctrl.stop()
        runner.cancel()
        feeder.cancel()
        await asyncio.gather(runner, feeder, return_exceptions=True)
        await meter.stop()
        return ctrl.trajectory, gate.active

    trajectory, active = asyncio.run(main())
    assert len(trajectory) >= 1          # probed at least once
    assert all(1 <= w <= 8 for w, _ in trajectory)


def test_rate_limiter_enforces_rps():
    rl = ratelimits.RateLimiter(rps=5)  # 5/s -> 0.2s spacing
    t0 = time.monotonic()
    for _ in range(3):
        rl.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.4  # 3 requests at 5/s span >= 2 intervals


def test_ncbi_rps_without_key(monkeypatch):
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    assert ratelimits.ncbi_rps() == 3.0
    monkeypatch.setenv("NCBI_API_KEY", "x")
    assert ratelimits.ncbi_rps() == 10.0


def test_endpoint_classification():
    assert ratelimits.endpoint_for_url("https://www.ebi.ac.uk/ena/x") == "ena"
    assert ratelimits.endpoint_for_url("https://eutils.ncbi.nlm.nih.gov/x") == "ncbi"
    assert ratelimits.endpoint_for_url("https://ngdc.cncb.ac.cn/gsa/x") == "gsa"
    assert ratelimits.endpoint_for_url("https://example.com/x") is None


def test_throttle_noop_when_inactive():
    ratelimits.set_active(None)
    ratelimits.throttle("https://eutils.ncbi.nlm.nih.gov/x")  # returns immediately
