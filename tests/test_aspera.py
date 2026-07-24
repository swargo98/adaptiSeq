"""Adaptive Aspera: hysteresis controller, dir-growth meter, fake-ascp e2e.

These offline tests exercise the controller on synthetic throughput curves and the
whole pool end-to-end with a fake ``ascp`` (a function that writes a file's bytes
over a short time) — they never need the network and always run.

Real ENA Aspera *was* subsequently validated with a genuine IBM ``ascp``: see
``test_aspera_live.py`` (opt-in, ``ADAPTISEQ_LIVE_ASPERA=1``).
"""

import asyncio
import os
import time

from adaptiseq.aspera import (
    AsperaBatchDownloader,
    HysteresisController,
    hysteresis_search,
)
from adaptiseq.batch import DownloadTask
from adaptiseq.engine.gate import WorkerGate
from adaptiseq.engine.throughput import DirGrowthMeter
from adaptiseq.options import Options


# ============================ hysteresis_search ===============================

def test_linear_scaling_keeps_adding_to_jobs():
    # Perfect linear scaling -> efficiency stays 1.0 -> climbs to the -j ceiling.
    final, traj = hysteresis_search(8, measure=lambda w: 100.0 * w, efficiency=0.7)
    assert final == 8
    assert all(eff >= 0.7 for _, _, eff in traj[1:])


def test_saturating_curve_stops_below_jobs():
    # Throughput saturates at 4 workers; cumulative efficiency falls below 0.7
    # shortly after, so the controller stops well below the -j=20 ceiling.
    final, traj = hysteresis_search(20, measure=lambda w: 100.0 * min(w, 4),
                                    efficiency=0.7)
    assert 4 <= final <= 6      # near the knee, not pegged at 20
    assert final < 20


def test_higher_threshold_stops_earlier():
    near_knee = hysteresis_search(20, lambda w: 100.0 * min(w, 4), efficiency=0.95)[0]
    looser = hysteresis_search(20, lambda w: 100.0 * min(w, 4), efficiency=0.7)[0]
    assert near_knee <= looser   # stricter efficiency -> fewer workers


def test_flat_throughput_stays_at_one():
    # Flat throughput: adding a 2nd worker yields eff 0.5 < 0.7 -> hold at 1.
    final, _ = hysteresis_search(20, lambda w: 100.0, efficiency=0.7)
    assert final == 1


def test_late_baseline_when_first_probe_zero():
    # T(1)=0 (no usable baseline), T(>=2) positive -> adopt late baseline, proceed.
    seq = {1: 0.0, 2: 200.0, 3: 300.0}
    final, traj = hysteresis_search(4, lambda w: seq.get(w, 300.0), efficiency=0.7)
    assert final >= 2
    assert traj[0] == (1, 0.0, 1.0)


def test_noisy_saturation_does_not_peg_at_jobs():
    import numpy as np
    rng = np.random.default_rng(1)
    def measure(w):
        return 100.0 * min(w, 3) + rng.normal(0, 2)
    final, _ = hysteresis_search(20, measure, efficiency=0.7)
    assert final <= 8   # settles near the knee, nowhere near 20


# ============================ async controller =================================

def test_async_controller_settles_with_synthetic_meter():
    # The async controller, driven over a fake meter whose throughput scales with
    # gate.active up to a knee of 3, must settle near the knee (not peg at -j).
    async def driver():
        gate = WorkerGate(jobs=10, active=1)

        class FakeMeter:
            def recent_average(self, n):
                return 100.0 * min(gate.active, 3)

        ctrl = HysteresisController(gate, FakeMeter(), probe_window=2, efficiency=0.7)
        task = asyncio.ensure_future(ctrl.run())
        await asyncio.sleep(2 * 8)        # enough real time for several 2s probes
        ctrl.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return gate.active, ctrl.trajectory

    active, traj = asyncio.run(driver())
    assert 3 <= active <= 6               # near the knee of 3 (cumulative-eff overshoot)
    assert len(traj) >= 2


# ============================ DirGrowthMeter ===================================

def test_dir_growth_meter_measures_writes(tmp_path):
    async def main():
        meter = DirGrowthMeter(tmp_path, interval=0.05)
        meter.start()
        f = tmp_path / "f.bin"
        with open(f, "wb") as fh:
            for _ in range(6):
                fh.write(b"x" * (256 * 1024))
                fh.flush()
                await asyncio.sleep(0.05)
        await asyncio.sleep(0.05)
        s = meter.samples()
        await meter.stop()
        return s
    samples = asyncio.run(main())
    assert samples
    assert any(x > 0 for x in samples)


# ============================ fake-ascp end-to-end =============================

def test_aspera_pool_with_fake_ascp(tmp_path):
    # download_fn simulates ascp: writes the file's bytes over a short interval.
    sizes = {f"a{i}.gz": (200 * 1024 * (i + 1)) for i in range(6)}

    def fake_ascp(task: DownloadTask) -> bool:
        path = tmp_path / task.save_path
        n = sizes[task.save_path]
        with open(path, "wb") as fh:
            written = 0
            while written < n:
                chunk = min(64 * 1024, n - written)
                fh.write(b"y" * chunk)
                fh.flush()
                written += chunk
                time.sleep(0.005)
        return True

    opts = Options(aspera=True, adaptive=True, jobs=4, quiet=True, probe_window=2,
                   aspera_efficiency=0.7)
    tasks = [DownloadTask("fasp://h/" + n, n, "ACC", aspera_db="ENA") for n in sizes]
    bd = AsperaBatchDownloader(fake_ascp, opts, tmp_path)
    failed = asyncio.run(bd.run(tasks))
    assert failed == set()
    for n, sz in sizes.items():
        assert (tmp_path / n).stat().st_size == sz


def test_aspera_pool_worker_slots_capped_to_task_count(tmp_path):
    def fake_ascp(task: DownloadTask) -> bool:
        (tmp_path / task.save_path).write_bytes(b"ok")
        return True

    opts = Options(aspera=True, adaptive=False, jobs=20, quiet=True)
    tasks = [
        DownloadTask(f"fasp://h/a{i}.gz", f"a{i}.gz", "ACC", aspera_db="ENA")
        for i in range(3)
    ]
    bd = AsperaBatchDownloader(fake_ascp, opts, tmp_path)

    failed = asyncio.run(bd.run(tasks))

    assert failed == set()
    assert bd._worker_slots == 3
    assert bd._initial_active == 3
    assert bd._gate.jobs == 3


def test_aspera_pool_gate_is_lowered_as_remaining_files_drain():
    class _P:
        total, done = 8, 6

    gate = WorkerGate(jobs=8, active=8)
    AsperaBatchDownloader._cap_gate_to_remaining(_P(), gate)
    assert gate.active == 2
    assert AsperaBatchDownloader._visible_workers(_P(), gate) == 2


def test_aspera_pool_retries_then_fails(tmp_path):
    def always_fail(task):
        return False
    opts = Options(aspera=True, adaptive=False, jobs=2, quiet=True)
    tasks = [DownloadTask("fasp://h/x.gz", "x.gz", "ACC", aspera_db="ENA")]
    failed = asyncio.run(AsperaBatchDownloader(always_fail, opts, tmp_path).run(tasks))
    assert failed == {"x.gz"}
