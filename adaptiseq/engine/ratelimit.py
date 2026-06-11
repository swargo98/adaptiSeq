"""Rate limiting, the global per-host connection cap, and a circuit breaker.

Part 2 fills this stub (Part 1 mapped ``-s/--speed`` onto wget/axel/ascp). The
segmented engine shares one :class:`TokenBucket` across a file's segments and
acquires a slot from one process-wide :class:`HostGuard` before opening any
segment connection — that cap is the binding safety bound Part 3's worker pool
relies on (spec §6). The :class:`HostGuard` also embeds a reactive circuit
breaker: a host that returns 429/503 or refuses connections is backed off
globally with exponential delay and a temporarily lowered cap, recovering slowly.

Everything here is asyncio-native, self-contained, and depends only on the
standard library.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Dict
from urllib.parse import urlparse

__all__ = ["TokenBucket", "HostGuard", "host_of"]


def host_of(url: str) -> str:
    """Return the ``host[:port]`` key used for per-host accounting."""
    netloc = urlparse(url).netloc
    if "@" in netloc:  # strip any userinfo
        netloc = netloc.rsplit("@", 1)[-1]
    return netloc.lower()


class TokenBucket:
    """A simple async token-bucket byte-rate limiter, shared across segments.

    ``rate`` is bytes/second (from ``-s/--speed`` MB/s). One bucket per file; all
    of that file's segments call :meth:`acquire` before counting written bytes, so
    the aggregate throughput is bounded regardless of segment count.
    """

    def __init__(self, rate_bytes_per_sec: float):
        self.rate = float(rate_bytes_per_sec)
        # 1 second of burst capacity; grown on demand if a single chunk exceeds it.
        self.capacity = max(1.0, self.rate)
        self.tokens = self.capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, nbytes: int) -> None:
        if self.rate <= 0 or nbytes <= 0:
            return
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                cap = max(self.capacity, float(nbytes))
                self.tokens = min(cap, self.tokens + elapsed * self.rate)
                if self.tokens >= nbytes:
                    self.tokens -= nbytes
                    return
                deficit = nbytes - self.tokens
                await asyncio.sleep(deficit / self.rate)


class _HostState:
    __slots__ = ("cap", "in_flight", "blocked_until", "backoff_level")

    def __init__(self, cap: int):
        self.cap = cap
        self.in_flight = 0
        self.blocked_until = 0.0
        self.backoff_level = 0


class HostGuard:
    """Process-wide per-host connection cap + reactive circuit breaker.

    Acquire a slot with ``async with guard.connection(host):`` around each segment
    connection. Report server pushback via :meth:`note_pushback` (429/503/refused)
    and clean responses via :meth:`note_success`; the breaker lowers/raises the
    effective cap and imposes exponential global backoff per host.
    """

    def __init__(
        self,
        default_cap: int = 8,
        *,
        min_cap: int = 1,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ):
        self.default_cap = max(1, int(default_cap))
        self.min_cap = max(1, int(min_cap))
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self._hosts: Dict[str, _HostState] = {}
        self._cond = asyncio.Condition()
        self.trips: list = []  # (host, kind, backoff) — for logging/tests

    def _state(self, host: str) -> _HostState:
        st = self._hosts.get(host)
        if st is None:
            st = _HostState(self.default_cap)
            self._hosts[host] = st
        return st

    async def acquire(self, host: str) -> None:
        async with self._cond:
            while True:
                st = self._state(host)
                now = time.monotonic()
                if st.blocked_until > now:
                    wait = st.blocked_until - now
                    # release the condition while sleeping out the global backoff
                    self._cond.release()
                    try:
                        await asyncio.sleep(wait)
                    finally:
                        await self._cond.acquire()
                    continue
                if st.in_flight < st.cap:
                    st.in_flight += 1
                    return
                await self._cond.wait()

    async def release(self, host: str) -> None:
        async with self._cond:
            st = self._state(host)
            if st.in_flight > 0:
                st.in_flight -= 1
            self._cond.notify_all()

    @asynccontextmanager
    async def connection(self, host: str):
        await self.acquire(host)
        try:
            yield
        finally:
            await self.release(host)

    async def note_pushback(self, host: str, kind: str = "pushback") -> None:
        """Trip the breaker for ``host``: exponential global backoff + halved cap."""
        async with self._cond:
            st = self._state(host)
            st.backoff_level += 1
            delay = min(
                self.max_backoff, self.base_backoff * (2 ** (st.backoff_level - 1))
            )
            st.blocked_until = time.monotonic() + delay
            st.cap = max(self.min_cap, st.cap // 2)
            self.trips.append((host, kind, delay))
            self._cond.notify_all()

    async def note_success(self, host: str) -> None:
        """A clean response: recover slowly (clear backoff, nudge cap upward)."""
        async with self._cond:
            st = self._state(host)
            st.backoff_level = 0
            st.blocked_until = 0.0
            if st.cap < self.default_cap:
                st.cap += 1
            self._cond.notify_all()

    # --- sync inspection for tests/logging ---
    def in_flight_of(self, host: str) -> int:
        st = self._hosts.get(host)
        return st.in_flight if st else 0

    def cap_of(self, host: str) -> int:
        st = self._hosts.get(host)
        return st.cap if st else self.default_cap

    def is_tripped(self, host: str) -> bool:
        st = self._hosts.get(host)
        return bool(st and st.blocked_until > time.monotonic())
