"""Adaptive parallel Aspera (``ascp``) download.

``ascp`` transfers cannot be paused/resumed mid-file, so the gradient controller
(which pauses + re-queues) does not apply. Aspera concurrency is controlled only
at **file-pickup boundaries** (start / don't-start a new ``ascp``), and tuned by an
**additive-increase + efficiency-hysteresis** controller (user spec, Part 5 item
3):

* establish a per-worker baseline throughput at one worker;
* each interval, tentatively add one worker and measure aggregate throughput;
* if it reaches at least ``--aspera-efficiency`` (default 0.70) of the *theoretical*
  ``workers × baseline``, keep the worker and try one more; otherwise drop that
  worker and hold (hysteresis — stop adding, don't flap).

Throughput is measured by a :class:`DirGrowthMeter` (ascp's bytes are written
out-of-process). The download itself is delegated to a ``download_fn(task) -> bool``
so tests can drive the whole pool with a fake ``ascp`` while production passes
:meth:`ClassicEngine.fetch_aspera`.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

from .batch import DownloadTask
from .console import NullReporter, Reporter, green
from .engine.gate import WorkerGate
from .engine.throughput import DirGrowthMeter
from .logs import in_success

log = logging.getLogger("adaptiseq.aspera")


# ============================ pure controller logic ===========================

def hysteresis_search(
    jobs: int,
    measure: Callable[[int], float],
    efficiency: float,
    *,
    max_steps: Optional[int] = None,
) -> Tuple[int, List[Tuple[int, float, float]]]:
    """Additive-increase with efficiency hysteresis (pure + testable).

    ``measure(w)`` returns aggregate throughput at ``w`` active workers. Returns
    ``(final_active, trajectory)`` where each trajectory entry is
    ``(workers, throughput, efficiency)``. ``efficiency`` is the keep/stop
    threshold in [0, 1].
    """
    jobs = max(1, int(jobs))
    traj: List[Tuple[int, float, float]] = []

    base_t = measure(1)
    baseline = base_t if base_t > 0 else 0.0
    traj.append((1, base_t, 1.0))
    active = 1
    steps = 0

    while active < jobs:
        steps += 1
        cand = active + 1
        t = measure(cand)

        if baseline <= 0:
            # Never got a usable baseline at 1 worker; adopt this observation as
            # the per-worker baseline and accept the worker once.
            baseline = (t / cand) if cand else 0.0
            eff = 1.0 if t > 0 else 0.0
        else:
            theoretical = cand * baseline
            eff = (t / theoretical) if theoretical > 0 else 0.0

        traj.append((cand, t, round(eff, 3)))

        if eff >= efficiency:
            active = cand            # worker justified — keep it, try one more
        else:
            break                    # diminishing returns — drop it, hold (hysteresis)

        if max_steps is not None and steps >= max_steps:
            break

    return active, traj


# ============================ async controller ================================

class HysteresisController:
    """Drives ``gate.active`` for ascp via :func:`hysteresis_search` over a meter."""

    def __init__(self, gate: WorkerGate, meter, *, probe_window: int = 5,
                 efficiency: float = 0.70):
        self.gate = gate
        self.meter = meter
        self.probe_window = max(2, int(probe_window))
        self.efficiency = float(efficiency)
        self.done = False
        self.trajectory: List[Tuple[int, float, float]] = []

    async def _measure(self, w: int) -> float:
        self.gate.set_active(w)
        await asyncio.sleep(1.0)                      # settle
        await asyncio.sleep(self.probe_window - 1.0)  # observe
        if self.done:
            return 0.0
        return self.meter.recent_average(max(1, self.probe_window - 1))

    async def run(self) -> None:
        await asyncio.sleep(self.probe_window)        # initial settle

        async def measure(w: int) -> float:
            if self.done:
                return 0.0
            return await self._measure(w)

        base_t = await measure(1)
        baseline = base_t if base_t > 0 else 0.0
        traj: List[Tuple[int, float, float]] = [(1, base_t, 1.0)]
        active = 1

        while active < self.gate.jobs and not self.done:
            cand = active + 1
            t = await measure(cand)
            if self.done:
                break

            if baseline <= 0:
                baseline = (t / cand) if cand else 0.0
                eff = 1.0 if t > 0 else 0.0
            else:
                theoretical = cand * baseline
                eff = (t / theoretical) if theoretical > 0 else 0.0

            traj.append((cand, t, round(eff, 3)))
            if eff >= self.efficiency:
                active = cand
            else:
                break

        self.trajectory = traj
        self.gate.set_active(active)
        log.info("aspera controller settled at %d workers (efficiency>=%.2f)",
                 active, self.efficiency)
        while not self.done:                          # hold until the queue drains
            await asyncio.sleep(0.5)

    def stop(self) -> None:
        self.done = True


# ============================ aspera batch pool ===============================

class AsperaBatchDownloader:
    """Parallel ascp pool with file-boundary gating + the hysteresis controller."""

    def __init__(self, download_fn: Callable[[DownloadTask], bool], options,
                 workdir: Path, reporter: Optional[Reporter] = None):
        self.download_fn = download_fn
        self.options = options
        self.workdir = Path(workdir)
        self.reporter = reporter or NullReporter()
        self.jobs = max(1, int(options.jobs))
        self.adaptive = bool(options.adaptive)

    async def run(self, tasks: List[DownloadTask]) -> Set[str]:
        if not tasks:
            return set()
        from .progress import ProgressBar

        queue: "asyncio.Queue[DownloadTask]" = asyncio.Queue()
        for t in tasks:
            queue.put_nowait(t)

        meter = DirGrowthMeter(self.workdir)
        worker_slots = min(self.jobs, len(tasks))
        active0 = worker_slots if not self.adaptive else 1
        gate = WorkerGate(worker_slots, active=active0)
        executor = ThreadPoolExecutor(max_workers=worker_slots)
        self._executor = executor
        failed: Set[str] = set()
        progress = ProgressBar(
            total=len(tasks),
            enabled=(None if not self.options.quiet else False),
            label="aspera",
        )

        meter.start()
        controller = None
        ctrl_task = None
        if self.adaptive:
            controller = HysteresisController(
                gate, meter,
                probe_window=self.options.probe_window,
                efficiency=self.options.aspera_efficiency,
            )
            ctrl_task = asyncio.ensure_future(controller.run())
        repaint = asyncio.ensure_future(self._repaint(progress, meter, gate))

        try:
            workers = [
                asyncio.ensure_future(self._worker(i, queue, gate, failed, progress))
                for i in range(worker_slots)
            ]
            await queue.join()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            repaint.cancel()
            await asyncio.gather(repaint, return_exceptions=True)
            progress.draw(meter.last_sample(), self._visible_workers(progress, gate))
            progress.finish()
            if controller is not None:
                controller.stop()
                if ctrl_task is not None:
                    ctrl_task.cancel()
                    await asyncio.gather(ctrl_task, return_exceptions=True)
            await meter.stop()
            self._controller = controller
            self._progress = progress
            self._gate = gate
            self._worker_slots = worker_slots
            self._initial_active = active0
            return failed
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

    @staticmethod
    def _remaining_files(progress) -> int:
        return max(0, progress.total - progress.done)

    @classmethod
    def _visible_workers(cls, progress, gate) -> int:
        remaining = cls._remaining_files(progress)
        if remaining == 0:
            return 0
        return min(gate.active, remaining)

    @classmethod
    def _cap_gate_to_remaining(cls, progress, gate) -> None:
        remaining = cls._remaining_files(progress)
        if remaining > 0 and gate.active > remaining:
            gate.set_active(remaining)

    def _already_successful(self, task: DownloadTask) -> bool:
        save_name = Path(task.save_path).name
        return (
            in_success(self.workdir, task.accession)
            or in_success(self.workdir, save_name)
        )

    async def _repaint(self, progress, meter, gate) -> None:
        try:
            while True:
                self._cap_gate_to_remaining(progress, gate)
                progress.draw(meter.last_sample(), self._visible_workers(progress, gate))
                await asyncio.sleep(0.4)
        except asyncio.CancelledError:
            return

    async def _worker(self, i, queue, gate, failed, progress) -> None:
        token = gate.token(i)
        loop = asyncio.get_event_loop()
        while True:
            if not token.should_continue():
                await asyncio.sleep(0.15)
                continue
            try:
                task = queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)
                continue
            try:
                if self._already_successful(task):
                    progress.inc()
                    self._cap_gate_to_remaining(progress, gate)
                    continue
                try:
                    # ascp is a blocking subprocess — run it off the event loop.
                    ok = await loop.run_in_executor(
                        self._executor, self.download_fn, task
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("aspera error for %s: %s", task.save_path, e)
                    ok = False
                if ok:
                    progress.inc()
                    self._cap_gate_to_remaining(progress, gate)
                else:
                    task.retries += 1
                    if task.retries < 3:
                        queue.put_nowait(task)
                    else:
                        failed.add(task.save_path)
            finally:
                queue.task_done()
