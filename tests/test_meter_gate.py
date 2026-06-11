"""Throughput meter + worker gate unit tests."""

import asyncio

from adaptiseq.engine.gate import WorkerGate
from adaptiseq.engine.throughput import ThroughputMeter


def test_gate_clamps_and_reflects_active():
    gate = WorkerGate(jobs=20, active=1)
    assert gate.active == 1
    assert gate.token(0).should_continue() is True
    assert gate.token(1).should_continue() is False

    gate.set_active(5)
    assert gate.active == 5
    assert gate.token(4).should_continue() is True
    assert gate.token(5).should_continue() is False

    # clamping
    assert gate.set_active(999) == 20
    assert gate.set_active(0) == 1
    assert gate.set_active(-3) == 1


def test_meter_samples_throughput():
    async def main():
        meter = ThroughputMeter(interval=0.05)
        meter.start()
        # ~2 MB over ~0.2s -> a few samples around ~80 Mbps; we only assert > 0.
        for _ in range(4):
            meter.on_bytes(512 * 1024)
            await asyncio.sleep(0.05)
        await meter.stop()
        return meter.samples(), meter.total_bytes

    samples, total = asyncio.run(main())
    assert total == 4 * 512 * 1024
    assert len(samples) >= 2
    assert any(s > 0 for s in samples)


def test_meter_recent_average_empty_is_zero():
    meter = ThroughputMeter()
    assert meter.recent_average(5) == 0.0
    assert meter.have_samples(1) is False
