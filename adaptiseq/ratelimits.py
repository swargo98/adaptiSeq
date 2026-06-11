"""Per-endpoint request-rate limiters for parallel metadata/URL resolution.

Distinct from :mod:`adaptiseq.engine.ratelimit` (which caps *download* bytes and
connections). Here we cap the *request rate* to each resolution endpoint — ENA,
NCBI, GSA — because one accession's resolution may touch more than one, and the
worker-pool size must not be the thing that controls request rate (spec §4).

NCBI E-utilities rate-limits to **3 requests/second without an API key** and 10
with one; we read an optional ``NCBI_API_KEY`` (and ``NCBI_EMAIL``) from the
environment and never exceed the unauthenticated limit when no key is present.

These are thread-safe (the parallel resolver fans out with a thread pool, and the
Part 1 resolver shells to ``wget``), and gate the actual requests in
:mod:`adaptiseq.net`, so whichever resolution path runs is throttled.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

# Host-substring -> endpoint key.
_ENDPOINT_HOSTS = {
    "ebi.ac.uk": "ena",
    "ncbi.nlm.nih.gov": "ncbi",
    "ngdc.cncb.ac.cn": "gsa",
    "cncb.ac.cn": "gsa",
}


def endpoint_for_url(url: str) -> Optional[str]:
    for host, key in _ENDPOINT_HOSTS.items():
        if host in url:
            return key
    return None


def ncbi_rps() -> float:
    """3 req/s unauthenticated, 10 with NCBI_API_KEY (spec §4)."""
    return 10.0 if os.environ.get("NCBI_API_KEY") else 3.0


class RateLimiter:
    """Thread-safe minimum-interval limiter (``rps`` requests per second)."""

    def __init__(self, rps: float):
        self.rps = float(rps)
        self._min_interval = 1.0 / self.rps if self.rps > 0 else 0.0
        self._next_at = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next_at = max(now, self._next_at) + self._min_interval


class EndpointLimiters:
    """One :class:`RateLimiter` per endpoint; ``throttle(url)`` gates a request."""

    def __init__(self, ena_rps: float = 8.0, gsa_rps: float = 5.0,
                 ncbi_rps_value: Optional[float] = None):
        self._limiters = {
            "ena": RateLimiter(ena_rps),
            "gsa": RateLimiter(gsa_rps),
            "ncbi": RateLimiter(ncbi_rps_value if ncbi_rps_value is not None else ncbi_rps()),
        }

    def throttle(self, url: str) -> None:
        key = endpoint_for_url(url)
        if key and key in self._limiters:
            self._limiters[key].acquire()

    def limiter(self, key: str) -> Optional[RateLimiter]:
        return self._limiters.get(key)


# --- process-wide active limiters (installed only during parallel resolution) ---
_ACTIVE: Optional[EndpointLimiters] = None
_ACTIVE_LOCK = threading.Lock()


def set_active(limiters: Optional[EndpointLimiters]) -> None:
    global _ACTIVE
    with _ACTIVE_LOCK:
        _ACTIVE = limiters


def get_active() -> Optional[EndpointLimiters]:
    return _ACTIVE


def throttle(url: str) -> None:
    """Consulted by :mod:`adaptiseq.net` before each request; no-op when inactive
    (so Part 1/2 behaviour is unchanged)."""
    active = _ACTIVE
    if active is not None:
        active.throttle(url)
