"""1 Hz throughput meter fed by the Part 2 byte-count callback.

The clean equivalent of fastbiodl's ``report_network_throughput`` deque, without
the CSV side effects or the ``elapsed > 1000`` heuristic. A background sampler
records per-second aggregate throughput (Mbps) into a rolling buffer; the
optimizer's probe averages a window of it.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from pathlib import Path
from typing import List, Optional


class ThroughputMeter:
    """Accumulates bytes via :meth:`on_bytes` and samples Mbps once per interval."""

    def __init__(self, window: int = 600, interval: float = 1.0):
        self._total = 0
        self._samples: "deque[float]" = deque(maxlen=window)
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop = False

    # Injected as the segmented engine's on_bytes callback (called from segments).
    def on_bytes(self, n: int) -> None:
        self._total += n

    @property
    def total_bytes(self) -> int:
        return self._total

    async def _sampler(self) -> None:
        prev_total = self._total
        prev = time.monotonic()
        while not self._stop:
            await asyncio.sleep(self._interval)
            now = time.monotonic()
            total = self._total
            dt = (now - prev) or 1e-3
            mbps = ((total - prev_total) * 8) / (dt * 1_000_000)
            self._samples.append(round(mbps, 2))
            prev_total, prev = total, now

    def start(self) -> None:
        if self._task is None:
            self._stop = False
            self._task = asyncio.ensure_future(self._sampler())

    async def stop(self) -> None:
        self._stop = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def samples(self) -> List[float]:
        return list(self._samples)

    def recent_average(self, n: int) -> float:
        """Mean of the last ``n`` per-second samples (0.0 if not enough yet)."""
        s = list(self._samples)[-n:]
        return float(sum(s) / len(s)) if s else 0.0

    def last_sample(self) -> float:
        """The most recent 1-second throughput sample (Mbps) — the instantaneous
        number the progress bar shows and the optimizer probes on. 0.0 if none."""
        return self._samples[-1] if self._samples else 0.0

    def have_samples(self, n: int) -> bool:
        return len(self._samples) >= n


class DirGrowthMeter:
    """Throughput meter for *out-of-process* transfers (e.g. ``ascp``).

    The byte-counter callback only sees bytes the Python engine writes; ``ascp``
    writes its own. So this meter samples the summed size of the output directory
    once per interval and reports the per-second growth as aggregate Mbps. It
    exposes the same surface as :class:`ThroughputMeter` (start/stop/
    recent_average/last_sample) so the controller and progress bar use it
    interchangeably.
    """

    def __init__(self, workdir, window: int = 600, interval: float = 1.0):
        self.workdir = Path(workdir)
        self._samples: "deque[float]" = deque(maxlen=window)
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop = False
        self._baseline_bytes = self._dir_bytes()

    def _dir_bytes(self) -> int:
        total = 0
        try:
            for root, _dirs, names in os.walk(self.workdir):
                for n in names:
                    try:
                        total += os.path.getsize(os.path.join(root, n))
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    # No-op: kept so callers can pass meter.on_bytes uniformly with ThroughputMeter.
    def on_bytes(self, n: int) -> None:
        return None

    async def _sampler(self) -> None:
        prev = self._dir_bytes()
        prevt = time.monotonic()
        while not self._stop:
            await asyncio.sleep(self._interval)
            now = time.monotonic()
            cur = self._dir_bytes()
            dt = (now - prevt) or 1e-3
            mbps = max(0.0, (cur - prev) * 8) / (dt * 1_000_000)
            self._samples.append(round(mbps, 2))
            prev, prevt = cur, now

    def start(self) -> None:
        if self._task is None:
            self._stop = False
            self._task = asyncio.ensure_future(self._sampler())

    async def stop(self) -> None:
        self._stop = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def samples(self) -> List[float]:
        return list(self._samples)

    def recent_average(self, n: int) -> float:
        s = list(self._samples)[-n:]
        return float(sum(s) / len(s)) if s else 0.0

    def last_sample(self) -> float:
        return self._samples[-1] if self._samples else 0.0

    def have_samples(self, n: int) -> bool:
        return len(self._samples) >= n
