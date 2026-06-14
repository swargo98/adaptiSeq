"""A live, single-line file-level progress bar for batch downloads.

Shows, self-updating on one line:

    adaptiSeq  [=====>     ]  12/35 files | 41.8 Mbps | 8 workers

- **files done / total** — completed files over resolved tasks.
- **instantaneous throughput** — the last 1-second sample (the exact number the
  adaptive optimizer probes on), not the running average.
- **active workers** — the optimizer-controlled worker count.

It is drawn only when enabled (CLI, non-quiet, stderr is a TTY); the library API
and `-Q/--quiet` leave it silent, so it never pollutes piped/log output. The bar
owns stderr; `Note` lines go to stdout, so they do not fight over the carriage
return in a terminal.
"""

from __future__ import annotations

import sys
from typing import Optional, TextIO


def _is_tty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


class ProgressBar:
    def __init__(
        self,
        total: int = 0,
        label: str = "adaptiSeq",
        stream: Optional[TextIO] = None,
        enabled: Optional[bool] = None,
        width: int = 24,
    ):
        self.total = max(0, int(total))
        self.done = 0
        self.label = label
        self.stream = stream if stream is not None else sys.stderr
        self.width = width
        self.enabled = _is_tty(self.stream) if enabled is None else bool(enabled)
        self._last_len = 0

    def set_total(self, n: int) -> None:
        self.total = max(0, int(n))

    def inc(self, n: int = 1) -> None:
        self.done += n

    def render_line(self, mbps: float, workers: int) -> str:
        total = self.total
        done = min(self.done, total) if total else self.done
        frac = (done / total) if total else 0.0
        filled = int(frac * self.width)
        bar = "=" * filled + (">" if filled < self.width else "")
        bar = bar.ljust(self.width)
        counts = f"{done}/{total}" if total else f"{done}"
        return (
            f"{self.label}  [{bar}]  {counts} files | "
            f"{mbps:.1f} Mbps | {workers} workers"
        )

    def draw(self, mbps: float, workers: int) -> None:
        if not self.enabled:
            return
        line = self.render_line(mbps, workers)
        pad = " " * max(0, self._last_len - len(line))
        self.stream.write("\r" + line + pad)
        self.stream.flush()
        self._last_len = len(line)

    def finish(self) -> None:
        if not self.enabled:
            return
        self.stream.write("\n")
        self.stream.flush()
        self._last_len = 0
