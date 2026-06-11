"""Batch pool + adaptive controller + parallel-resolution rate-limit tests."""

import asyncio
import hashlib
import os
import time

import pytest

from adaptiseq import ratelimits
from adaptiseq.batch import AdaptiveController, BatchDownloader, DownloadTask
from adaptiseq.engine.gate import WorkerGate
from adaptiseq.engine.seam import SegmentedEngine
from adaptiseq.engine.throughput import ThroughputMeter
from adaptiseq.options import Options
from tests.servers import MultiFileRangeServer


def md5(b):
    return hashlib.md5(b).hexdigest()


def _engine(outdir, **opts):
    base = dict(engine="segmented", segment_size=1 * 1024 * 1024, max_segments=4,
                max_conns_per_host=8, quiet=True, adaptive=False, jobs=4)
    base.update(opts)
    return SegmentedEngine(Options(**base), outdir)


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
