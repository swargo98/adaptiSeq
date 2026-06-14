"""Progress bar + meter last-sample tests."""

import asyncio
import io

from adaptiseq.engine.throughput import ThroughputMeter
from adaptiseq.progress import ProgressBar


def test_render_line_contents():
    p = ProgressBar(total=35, enabled=False)
    p.done = 12
    line = p.render_line(41.8, 8)
    assert "12/35 files" in line
    assert "41.8 Mbps" in line
    assert "8 workers" in line


def test_draw_writes_when_enabled():
    buf = io.StringIO()
    p = ProgressBar(total=4, stream=buf, enabled=True)
    p.inc()
    p.draw(10.0, 2)
    out = buf.getvalue()
    assert "\r" in out
    assert "1/4 files" in out
    assert "2 workers" in out


def test_draw_silent_when_disabled():
    buf = io.StringIO()
    p = ProgressBar(total=4, stream=buf, enabled=False)
    p.draw(10.0, 2)
    p.finish()
    assert buf.getvalue() == ""


def test_inc_and_finish():
    buf = io.StringIO()
    p = ProgressBar(total=3, stream=buf, enabled=True)
    p.inc(); p.inc()
    assert p.done == 2
    p.finish()
    assert buf.getvalue().endswith("\n")


def test_meter_last_sample():
    async def main():
        m = ThroughputMeter(interval=0.05)
        m.start()
        for _ in range(4):
            m.on_bytes(256 * 1024)
            await asyncio.sleep(0.05)
        last = m.last_sample()
        await m.stop()
        return last, m.samples()

    last, samples = asyncio.run(main())
    assert samples  # has samples
    assert last == samples[-1]
