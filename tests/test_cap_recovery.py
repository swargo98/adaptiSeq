"""A lowered per-host cap climbs back with time, not only on a new response.

Round 2 panel 4b (2026-10-20/21): every arm that met an early refused connect
was held at exactly the open count (25) for the whole run while the others
reached 50, and GSA tails sank to one connection: the cap rose only on a clean
*new* response, and while it is held at the open count no new response starts.
"""

import asyncio

from adaptiseq.engine import ratelimit
from adaptiseq.engine.ratelimit import HostGuard

H = "ftp.sra.ebi.ac.uk"


def _clock(monkeypatch):
    t = [100.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: t[0])
    return t


def _open(guard, n):
    async def go():
        for _ in range(n):
            await guard.acquire(H)
    asyncio.run(go())


def test_ceiling_pin_recovers_one_per_interval(monkeypatch):
    t = _clock(monkeypatch)
    guard = HostGuard(default_cap=64)
    _open(guard, 25)
    assert asyncio.run(guard.note_refused(H)) is True
    assert guard.cap_of(H) == 25
    t[0] += ratelimit.RECOVER_S - 0.1
    assert guard.cap_of(H) == 25          # not before the interval
    t[0] += 0.1
    assert guard.cap_of(H) == 26
    t[0] += 10 * ratelimit.RECOVER_S
    assert guard.cap_of(H) == 36
    t[0] += 1000
    assert guard.cap_of(H) == 64          # never above the configured cap


def test_a_new_refusal_pins_again_and_restarts_the_clock(monkeypatch):
    t = _clock(monkeypatch)
    guard = HostGuard(default_cap=64)
    _open(guard, 25)
    asyncio.run(guard.note_refused(H))
    t[0] += 3 * ratelimit.RECOVER_S
    assert guard.cap_of(H) == 28
    asyncio.run(guard.note_refused(H))     # 25 still open: the ceiling is real
    assert guard.cap_of(H) == 25
    t[0] += ratelimit.RECOVER_S - 0.1
    assert guard.cap_of(H) == 25


def test_pushback_recovers_only_after_its_backoff(monkeypatch):
    t = _clock(monkeypatch)
    guard = HostGuard(default_cap=40, base_backoff=10.0)
    asyncio.run(guard.note_pushback(H, "429"))
    assert guard.cap_of(H) == 20
    t[0] += 9.0                             # still backing off
    assert guard.cap_of(H) == 20
    t[0] += 1.0 + ratelimit.RECOVER_S
    assert guard.cap_of(H) == 21


def test_a_waiting_connection_gets_the_recovered_slot(monkeypatch):
    guard = HostGuard(default_cap=8, recover_s=0.05)

    async def go():
        for _ in range(4):
            await guard.acquire(H)
        await guard.note_refused(H)          # cap pinned at 4, all 4 in use
        assert guard.cap_of(H) == 4
        # no release happens: only the time-based recovery can admit this one
        await asyncio.wait_for(guard.acquire(H), 1.0)
        return guard.in_flight_of(H)
    assert asyncio.run(go()) == 5


def test_recovery_can_be_switched_off():
    guard = HostGuard(default_cap=8, recover_s=0)
    _open(guard, 3)
    asyncio.run(guard.note_refused(H))
    assert guard.cap_of(H) == 3
