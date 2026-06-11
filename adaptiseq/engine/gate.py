"""The worker gate — the single integer the optimizer actually controls.

Replaces fastbiodl's ``download_process_status`` shared array
(``status[i] = 1 if i < active else 0``) with one mutable ``active`` count. Each
pool worker holds a :class:`WorkerToken` (the Part 2 pause token): worker ``i``
keeps downloading only while ``i < active``. Lowering ``active`` makes higher-index
workers' ``should_continue()`` go False, so the segmented downloader cancels its
in-flight segments, writes ``.part.meta``, and the worker re-queues the file —
exactly the fastbiodl pause/re-queue behaviour, race-free in one event loop.
"""

from __future__ import annotations


class WorkerGate:
    """A clamped, mutable active-worker count shared by the pool and optimizer."""

    def __init__(self, jobs: int, active: int = 1):
        self.jobs = max(1, int(jobs))
        self._active = max(1, min(int(active), self.jobs))

    @property
    def active(self) -> int:
        return self._active

    def set_active(self, w: int) -> int:
        """Set the active-worker count, clamped to ``[1, jobs]``. Returns it."""
        self._active = max(1, min(int(w), self.jobs))
        return self._active

    def is_active(self, worker_index: int) -> bool:
        return worker_index < self._active

    def token(self, worker_index: int) -> "WorkerToken":
        return WorkerToken(self, worker_index)


class WorkerToken:
    """Part 2 pause-token shape (``should_continue() -> bool``) backed by the gate."""

    __slots__ = ("_gate", "_index")

    def __init__(self, gate: WorkerGate, index: int):
        self._gate = gate
        self._index = index

    def should_continue(self) -> bool:
        return self._gate.is_active(self._index)
