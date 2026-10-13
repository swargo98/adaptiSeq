"""Per-second resource sampler for the adaptiSeq publication benchmark.

Standalone — imports nothing from the ``adaptiseq`` package. It walks a process
**tree** (the tool + all descendants: ``ascp``/``wget``/``prefetch``/``pigz``/
``fasterq-dump`` are children), and every tick records, summed over the tree:

* ``cpu_pct``     — CPU utilisation (sum of per-process ``cpu_percent``; can exceed
                    100 on multi-core).
* ``rss_mb``      — resident memory (sum of RSS over the tree).
* ``read_mbps`` / ``write_mbps`` — disk I/O rate from ``io_counters`` deltas.
* ``net_recv_mbps`` / ``net_sent_mbps`` — **system-wide** net deltas as a proxy
  (per-process net counters need root / are not portable; documented limitation).

Each row is tagged with the **phase** active at that instant, read from a shared
:class:`~sysbench.phases.PhaseTimeline`. MB here means 10**6 bytes (decimal), to
match download-tool reporting; "mbps" columns are **megabytes/s**, not megabits.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

import psutil


@dataclass
class Sample:
    t: float                # seconds since sampler start
    phase: str
    cpu_pct: float
    rss_mb: float
    read_mbps: float
    write_mbps: float
    net_recv_mbps: float
    net_sent_mbps: float
    nprocs: int

    def as_row(self) -> dict:
        return {
            "t": round(self.t, 3),
            "phase": self.phase,
            "cpu_pct": round(self.cpu_pct, 1),
            "rss_mb": round(self.rss_mb, 1),
            "read_mbps": round(self.read_mbps, 3),
            "write_mbps": round(self.write_mbps, 3),
            "net_recv_mbps": round(self.net_recv_mbps, 3),
            "net_sent_mbps": round(self.net_sent_mbps, 3),
            "nprocs": self.nprocs,
        }


class Sampler:
    """Background thread sampling a process tree at a fixed interval."""

    def __init__(self, pid: int, timeline=None, interval: float = 1.0):
        self.root_pid = pid
        self.timeline = timeline
        self.interval = float(interval)
        self.samples: List[Sample] = []
        self._stop = threading.Event()
        # Set once the IO/net baselines are primed. start() waits on it so a
        # caller cannot begin its workload before the sampler has a reference
        # point — bytes moved before priming are invisible to the first rate.
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._t0 = 0.0
        # Cache Process objects across ticks: cpu_percent(interval=None) is stateful
        # per object (it needs the previous reading), so recreating Process objects
        # every tick would always return 0. Keyed by pid.
        self._procs: dict = {}

    # --- tree walking -------------------------------------------------------
    def _tree(self) -> List[psutil.Process]:
        """Refresh the cached process tree, priming cpu_percent on newly seen pids."""
        try:
            root = psutil.Process(self.root_pid)
        except psutil.NoSuchProcess:
            return []
        seen = {self.root_pid: root}
        try:
            for c in root.children(recursive=True):
                seen[c.pid] = c
        except psutil.NoSuchProcess:
            pass
        for pid, proc in seen.items():
            if pid not in self._procs:
                self._procs[pid] = proc
                try:
                    proc.cpu_percent(interval=None)  # prime new child
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        # drop pids no longer present
        for pid in list(self._procs):
            if pid not in seen:
                del self._procs[pid]
        return list(self._procs.values())

    @staticmethod
    def _io_sum(procs):
        r = w = 0
        for p in procs:
            try:
                io = p.io_counters()
                r += io.read_bytes
                w += io.write_bytes
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue
        return r, w

    @staticmethod
    def _cpu_rss(procs):
        cpu = rss = 0.0
        n = 0
        for p in procs:
            try:
                cpu += p.cpu_percent(interval=None)
                rss += p.memory_info().rss
                n += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return cpu, rss, n

    # --- lifecycle ----------------------------------------------------------
    def _run(self):
        # prime cpu_percent (first call returns 0.0) and io/net baselines
        for p in self._tree():
            try:
                p.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        try:
            last_io = self._io_sum(self._tree())
            last_net = psutil.net_io_counters()
            last_t = time.monotonic()
        except BaseException:
            self._ready.set()   # never leave start() blocked on a dead thread
            raise

        # Track peak cumulative IO so a child exiting between ticks doesn't make
        # the running total go backwards (rates are clamped to >= 0).
        peak_read, peak_write = last_io
        self._ready.set()

        while not self._stop.wait(self.interval):
            now = time.monotonic()
            dt = max(1e-6, now - last_t)
            procs = self._tree()
            cpu, rss, n = self._cpu_rss(procs)
            cur_io = self._io_sum(procs)
            cur_net = psutil.net_io_counters()

            peak_read = max(peak_read, cur_io[0])
            peak_write = max(peak_write, cur_io[1])
            read_rate = max(0.0, cur_io[0] - last_io[0]) / dt / 1e6
            write_rate = max(0.0, cur_io[1] - last_io[1]) / dt / 1e6
            net_recv = max(0.0, cur_net.bytes_recv - last_net.bytes_recv) / dt / 1e6
            net_sent = max(0.0, cur_net.bytes_sent - last_net.bytes_sent) / dt / 1e6

            phase = self.timeline.current() if self.timeline else "all"
            self.samples.append(Sample(
                t=now - self._t0, phase=phase, cpu_pct=cpu, rss_mb=rss / 1e6,
                read_mbps=read_rate, write_mbps=write_rate,
                net_recv_mbps=net_recv, net_sent_mbps=net_sent, nprocs=n,
            ))
            last_io, last_net, last_t = cur_io, cur_net, now

    def start(self):
        self._t0 = time.monotonic()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # Block until baselines exist (bounded, so a priming failure can't hang
        # the caller). Without this the workload can race ahead of the sampler.
        self._ready.wait(timeout=max(1.0, self.interval * 3))
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 3)
        return self.samples

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
