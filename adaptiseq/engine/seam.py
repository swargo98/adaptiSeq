"""The ``SegmentedEngine`` that plugs the segmented transport into the Part 1 seam.

Implements the exact same interface as :class:`ClassicEngine`
(``fetch(url, save_path) -> bool`` and ``fetch_aspera(...)``) so it is a drop-in
replacement at the single download call site. It owns transport selection
(spec §5.1): honour an explicit ``-r`` override, otherwise prefer the HTTPS mirror
and confirm cheaply with a per-host probe, falling back to native segmented FTP,
single-stream, or finally ``--engine classic``. It never emits a zero-byte or
truncated file — finalisation is atomic in the downloaders.

The engine only changes *how* bytes arrive, never *which* bytes: it may upgrade an
``ftp://H/path`` to ``https://H/path`` (same host, same file) but does not pick a
different URL, host, database, or path. Aspera is unchanged and bypasses this
engine entirely (delegated to the classic ``ascp`` path).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp

from ..console import green
from .classic import ClassicEngine
from .ftp import FtpSegmentedDownloader, parse_ftp_url, probe_ftp
from .ratelimit import HostGuard, TokenBucket
from .segmented import SegmentedDownloader

log = logging.getLogger("adaptiseq.engine.seam")


def _to_https(url: str) -> str:
    """Same-host scheme upgrade ``ftp://H/path`` -> ``https://H/path``."""
    p = urlparse(url)
    netloc = p.netloc.rsplit("@", 1)[-1]
    path = p.path
    return f"https://{netloc}{path}"


class SegmentedEngine:
    """Segmented HTTP(S)/FTP engine with transport selection and classic fallback."""

    name = "segmented"

    def __init__(self, options, workdir, reporter=None):
        from ..console import NullReporter

        self.options = options
        self.workdir = Path(workdir)
        self.reporter = reporter or NullReporter()
        self._classic = ClassicEngine(options, workdir, reporter)
        # Per-host transport verdict cache (plain data, safe across event loops).
        self._verdict: Dict[str, Tuple[str, str]] = {}

    # --- the seam ---------------------------------------------------------------
    def fetch(self, url: str, save_path: str) -> bool:
        return asyncio.run(self._fetch_one(url, save_path))

    def fetch_aspera(self, link: str, db: str, save_path: Optional[str] = None) -> bool:
        # Aspera is unchanged in Part 2 — delegate straight to the classic ascp path.
        return self._classic.fetch_aspera(link, db, save_path)

    async def _fetch_one(self, url: str, save_path: str) -> bool:
        """Part 2 sequential seam: own session, guard, and rate per call."""
        guard = HostGuard(self.options.max_conns_per_host)
        rate = TokenBucket(self.options.speed * 1024 * 1024)
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
        connector = aiohttp.TCPConnector(limit=0)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            return await self.fetch_async(url, save_path, session=session,
                                          host_guard=guard, rate=rate)

    # --- async core (shared by Part 2 seam and Part 3 batch pool) ---------------
    async def fetch_async(
        self,
        url: str,
        save_path: str,
        *,
        session: aiohttp.ClientSession,
        host_guard: Optional[HostGuard] = None,
        rate: Optional[TokenBucket] = None,
        pause: Optional[object] = None,
        on_bytes: Optional[object] = None,
    ) -> bool:
        """Download one URL in the *current* event loop, with injected session,
        per-host guard, rate limiter, pause token (the worker gate), and byte
        counter (the throughput meter). This is what the Part 3 batch pool drives
        with one shared guard/meter and a per-worker gate token."""
        dest = str(self.workdir / save_path)
        opts = self.options
        guard = host_guard or HostGuard(opts.max_conns_per_host)
        if rate is None:
            rate = TokenBucket(opts.speed * 1024 * 1024)

        kind, eff_url = await self._select_transport(url, session)
        self._log_transport(url, kind, eff_url)

        if kind == "classic":
            return await asyncio.get_event_loop().run_in_executor(
                None, self._classic.fetch, url, save_path
            )
        if kind in ("http-seg", "http-single"):
            d = SegmentedDownloader(
                session, eff_url, dest,
                segment_size=opts.segment_size,
                max_segments=1 if kind == "http-single" else opts.max_segments,
                host_guard=guard, rate=rate, pause=pause, on_bytes=on_bytes,
            )
            return await d.download()
        d = FtpSegmentedDownloader(
            eff_url, dest,
            segment_size=opts.segment_size,
            max_segments=1 if kind == "ftp-single" else opts.max_segments,
            host_guard=guard, rate=rate, pause=pause, on_bytes=on_bytes,
        )
        return await d.download()

    async def _select_transport(
        self, url: str, session: aiohttp.ClientSession
    ) -> Tuple[str, str]:
        p = urlparse(url)
        scheme = p.scheme
        host = p.netloc
        proto = self.options.protocol  # auto | ftp | https

        # Explicit -r override is final (spec §5.1).
        if proto == "https":
            return ("http-seg", _to_https(url) if scheme == "ftp" else url)
        if proto == "ftp":
            if scheme == "ftp":
                return ("ftp-seg", url)
            return ("http-seg", url)

        # auto
        if scheme in ("http", "https"):
            return ("http-seg", url)

        # ftp:// under auto — decide per host and cache only the *kind* (NOT the
        # effective URL, which must be derived per-file: caching a full URL would
        # make every file on a host download the first file's bytes).
        kind = self._verdict.get(host)
        if kind is None:
            kind = await self._probe_ftp_kind(url, session)
            self._verdict[host] = kind
        return (kind, self._eff_url(url, kind))

    @staticmethod
    def _eff_url(url: str, kind: str) -> str:
        """Map a transport kind to the effective URL for *this* file."""
        if kind in ("http-seg", "http-single"):
            return _to_https(url) if urlparse(url).scheme == "ftp" else url
        return url  # ftp-seg / ftp-single / classic keep the original ftp url

    async def _probe_ftp_kind(
        self, url: str, session: aiohttp.ClientSession
    ) -> str:
        """Section 5.1 decision order: HTTPS mirror > segmented FTP > single >
        classic. Returns the transport *kind* only (host-level, URL-independent)."""
        https_url = _to_https(url)
        # 1. HTTPS mirror range-capable?
        probe = SegmentedDownloader(session, https_url, "/dev/null")
        size, supports = await probe.probe_range_support()
        if supports:
            return "http-seg"

        # 2. Native FTP with REST + concurrency?
        host, port, path = parse_ftp_url(url)
        ftp_size, rest_ok, conc_ok = await probe_ftp(host, port, path)
        if rest_ok and conc_ok:
            return "ftp-seg"

        # 3. Single-stream: prefer HTTPS if it served a size at all, else FTP.
        if size is not None:
            return "http-single"
        if ftp_size:
            return "ftp-single"

        # 4. Neither serves ranges/streams cleanly — fall back to classic.
        return "classic"

    def _log_transport(self, url: str, kind: str, eff_url: str) -> None:
        reasons = {
            "http-seg": "HTTPS mirror is range-capable; segmented HTTPS",
            "http-single": "HTTPS reachable but no ranges; single-stream HTTPS",
            "ftp-seg": "FTP supports REST + concurrency; segmented FTP",
            "ftp-single": "FTP single-stream (no concurrency/REST)",
            "classic": "no range/stream support; falling back to classic wget/axel",
        }
        host = urlparse(eff_url).netloc or urlparse(url).netloc
        msg = f"Transport for {host}: {reasons.get(kind, kind)}"
        log.info(msg)
        if not self.options.quiet:
            self.reporter.info(f"{green('Note')}: {msg}")
