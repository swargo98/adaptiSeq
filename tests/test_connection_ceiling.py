"""A refused connect while other connections are open is a ceiling, not distress.

Full run, panel 3b: each adaptiSeq arm logged 6 to 8 refused connects to
ftp.sra.ebi.ac.uk, and connections never rose past 25, the level the old breaker
settled at (0.1.5, with this change, held up to 45). A refusal used to halve
the process-wide per-host cap and block the host for a backoff, and each one cost
the segment an attempt (three refusals failed the whole file). Now the guard
holds the cap at the number of open connections and the segment waits for a free
slot without spending an attempt; with nothing else open, a refusal is ordinary
pushback as before.
"""

import asyncio
import os
import socket

import aiohttp
import pytest

from adaptiseq.engine import segmented
from adaptiseq.engine.ratelimit import HostGuard
from adaptiseq.engine.segmented import SegmentedDownloader


def run(coro):
    return asyncio.run(coro)


def test_refusal_with_connections_open_holds_cap_at_the_open_count():
    guard = HostGuard(default_cap=40, base_backoff=0.05)

    async def main():
        for _ in range(25):
            await guard.acquire("h")
        assert await guard.note_refused("h") is True
        assert guard.cap_of("h") == 25
        assert not guard.is_tripped("h")
        assert guard.trips[-1][1] == "ceiling"
        # a clean response re-tests the ceiling one connection higher
        await guard.note_success("h")
        assert guard.cap_of("h") == 26

    run(main())


def test_refusal_with_nothing_open_is_ordinary_pushback():
    guard = HostGuard(default_cap=8, base_backoff=0.05)

    async def main():
        assert await guard.note_refused("h") is False
        assert guard.cap_of("h") == 4
        assert guard.is_tripped("h")

    run(main())


class _CeilingGuard(HostGuard):
    """Always reports a ceiling, never blocks: isolates the segment's retry loop."""

    def __init__(self):
        super().__init__(default_cap=100)
        self.refusals = 0

    async def note_refused(self, host):
        self.refusals += 1
        return True


def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_ceiling_refusals_do_not_spend_segment_attempts(monkeypatch, tmp_path):
    monkeypatch.setattr(segmented, "MAX_CEILING_WAITS", 4)
    monkeypatch.setattr(segmented, "CEILING_PAUSE_S", 0.0)
    guard = _CeilingGuard()
    url = f"http://127.0.0.1:{_closed_port()}/f.bin"

    async def main():
        async with aiohttp.ClientSession() as s:
            d = SegmentedDownloader(s, url, str(tmp_path / "f.bin"), host_guard=guard,
                                    max_retries=2)
            fd = os.open(tmp_path / "f.part", os.O_CREAT | os.O_RDWR)
            try:
                with pytest.raises(aiohttp.ClientConnectorError):
                    await d.download_segment_streaming(0, 0, 99, fd, {})
            finally:
                os.close(fd)

    run(main())
    # 4 waits at the ceiling, then the 2 real attempts
    assert guard.refusals == 4 + 2
