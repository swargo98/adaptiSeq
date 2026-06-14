"""Phase timeline shared between an adapter and the :class:`~sysbench.sampler.Sampler`.

The four task phases the publication breaks a download into:

* ``request``  — process launch up to the first network byte / first API call.
* ``metadata`` — accession resolution → metadata rows / resolved URLs.
* ``data``     — transfer of the actual NGS sequence-file bytes.
* ``md5``      — integrity verification of the downloaded bytes.

A tool that fuses phases (streams data while still resolving) should mark windows
``overlapped`` rather than pretend they are separable; honesty over tidiness.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

PHASES = ("request", "metadata", "data", "md5", "overlapped", "idle")


@dataclass
class PhaseTimeline:
    """Records phase-boundary timestamps; thread-safe ``current()`` for the sampler."""
    t0: float = field(default_factory=time.monotonic)
    # (start_offset, phase) entries, in order
    marks: List[Tuple[float, str]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def mark(self, phase: str) -> None:
        assert phase in PHASES, f"unknown phase {phase!r}"
        with self._lock:
            self.marks.append((time.monotonic() - self.t0, phase))

    def current(self) -> str:
        with self._lock:
            return self.marks[-1][1] if self.marks else "idle"

    def windows(self, end: Optional[float] = None) -> List[Tuple[str, float, float]]:
        """Return ``(phase, start, end)`` windows in seconds since t0."""
        with self._lock:
            marks = list(self.marks)
        if not marks:
            return []
        if end is None:
            end = time.monotonic() - self.t0
        out = []
        for i, (start, phase) in enumerate(marks):
            stop = marks[i + 1][0] if i + 1 < len(marks) else end
            out.append((phase, start, stop))
        return out

    def durations(self, end: Optional[float] = None) -> dict:
        d: dict = {}
        for phase, s, e in self.windows(end):
            d[phase] = d.get(phase, 0.0) + max(0.0, e - s)
        return d


class phase:  # noqa: N801 — used as a context manager `with phase(tl, "data"):`
    """Context manager that marks a phase on entry (and restores ``idle`` on exit
    only if it is the outermost active phase)."""

    def __init__(self, timeline: PhaseTimeline, name: str):
        self.timeline = timeline
        self.name = name

    def __enter__(self):
        self.timeline.mark(self.name)
        return self

    def __exit__(self, *exc):
        self.timeline.mark("idle")
        return False
