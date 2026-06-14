"""Batch parallel download with adaptive concurrency and parallel resolution.

Single-process asyncio (spec §3): one event loop, one ``HostGuard``, one worker
gate integer, one throughput meter — chosen over a process pool so resume/log
logic stays race-free and the active-worker gate is trivially the integer the
loop reads.

Three cooperating pieces:
* :class:`BatchDownloader` — a pool of ``-j`` workers pulling a download queue;
  each worker runs the Part 2 segmented engine for one file, gated by the worker
  gate. Per-file semantics (skip-if-in-success.log, retry up to 3, fail.log,
  continue past failure, exit non-zero overall) are preserved.
* :class:`AdaptiveController` — the gradient controller (``engine/optimize.py``)
  wired to the live throughput meter; it tunes the gate's active-worker count.
* :func:`resolve_all` — parallel metadata/URL resolution (``--meta-jobs``) that
  runs the *Part 1* multi-database, preference-ordered resolver and streams
  resolved tasks into the download queue as they complete, throttled by
  per-endpoint rate limiters.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

import aiohttp

from . import metadata as _meta
# Import the resolver helpers from the submodule directly: the package attribute
# `adaptiseq.resolve` is the public API *function*, which shadows the submodule.
from .resolve import resolve_gsa_urls, resolve_sra_urls
from .accession import is_gsa
from .console import NullReporter, Reporter, green
from .engine.gate import WorkerGate
from .engine.optimize import EXIT_SIGNAL, gradient_opt_fast
from .engine.ratelimit import HostGuard, TokenBucket
from .engine.throughput import ThroughputMeter
from .logs import in_success
from .options import Options, RunContext
from .ratelimits import EndpointLimiters, set_active

log = logging.getLogger("adaptiseq.batch")


@dataclass
class DownloadTask:
    url: str
    save_path: str       # relative to workdir
    accession: str
    retries: int = 0
    aspera_db: Optional[str] = None   # "ENA"/"GSA" when this task is an ascp link


# ============================== adaptive controller ===========================

class AdaptiveController:
    """Drives ``gate.active`` from the gradient optimizer over the live meter."""

    def __init__(self, gate: WorkerGate, meter: ThroughputMeter, *,
                 probe_window: int = 5, cc_penalty: float = 1.01):
        self.gate = gate
        self.meter = meter
        self.probe_window = max(2, int(probe_window))
        self.cc_penalty = float(cc_penalty)
        self.done = False
        self.trajectory: List[Tuple[int, float]] = []  # (workers, mbps) per probe

    async def _probe(self, w: int) -> float:
        if self.done:
            return EXIT_SIGNAL
        self.gate.set_active(w)
        await asyncio.sleep(1.0)               # let the change settle
        await asyncio.sleep(self.probe_window - 1.0)
        if self.done:
            return EXIT_SIGNAL
        need = max(1, self.probe_window - 1)
        thrpt = self.meter.recent_average(need)
        score = thrpt / (self.cc_penalty ** w) if self.cc_penalty else thrpt
        value = int(round(-score))
        self.trajectory.append((w, round(thrpt, 2)))
        log.info("adaptive probe: workers=%d throughput=%.1fMbps score=%d",
                 w, thrpt, value)
        return value

    async def run(self) -> None:
        loop = asyncio.get_event_loop()
        # One window of settle before the first probe (mirrors run_download_optimizer).
        await asyncio.sleep(self.probe_window)

        def black_box(w: int) -> float:
            if self.done:
                return EXIT_SIGNAL
            fut = asyncio.run_coroutine_threadsafe(self._probe(w), loop)
            return fut.result()

        # gradient_opt_fast is synchronous and blocks on each probe; run it in a
        # thread so the worker pool keeps running on the loop. Each probe is
        # marshalled back onto the loop via run_coroutine_threadsafe.
        await loop.run_in_executor(
            None, lambda: gradient_opt_fast(self.gate.jobs, black_box, log)
        )

    def stop(self) -> None:
        self.done = True


# ============================== batch downloader ==============================

class BatchDownloader:
    """A pool of ``-j`` workers downloading resolved tasks through the segmented
    engine, with the adaptive gate and shared per-host cap."""

    def __init__(self, engine, options: Options, workdir: Path,
                 reporter: Optional[Reporter] = None):
        self.engine = engine
        self.options = options
        self.workdir = Path(workdir)
        self.reporter = reporter or NullReporter()
        self.jobs = max(1, int(options.jobs))
        self.adaptive = bool(options.adaptive)

    async def run(self, tasks: List[DownloadTask]) -> Set[str]:
        """Download all ``tasks``; return the set of save_paths that ultimately
        failed (after retries). Continues past individual failures."""
        if not tasks:
            return set()
        queue: "asyncio.Queue[DownloadTask]" = asyncio.Queue()
        for t in tasks:
            queue.put_nowait(t)

        meter = ThroughputMeter()
        # Non-adaptive: all -j workers active. Adaptive: start at 2 (pre-activate),
        # the controller then tunes from there.
        active0 = self.jobs if not self.adaptive else min(2, self.jobs)
        gate = WorkerGate(self.jobs, active=active0)
        guard = HostGuard(self.options.max_conns_per_host)
        rate = TokenBucket(self.options.speed * 1024 * 1024)
        failed: Set[str] = set()

        from .progress import ProgressBar

        progress = ProgressBar(
            total=len(tasks),
            enabled=(None if not self.options.quiet else False),
        )

        meter.start()
        controller = None
        ctrl_task = None
        if self.adaptive:
            controller = AdaptiveController(
                gate, meter,
                probe_window=self.options.probe_window,
                cc_penalty=self.options.cc_penalty,
            )
            ctrl_task = asyncio.ensure_future(controller.run())
        repaint_task = asyncio.ensure_future(self._repaint(progress, meter, gate))

        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
        connector = aiohttp.TCPConnector(limit=0)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            workers = [
                asyncio.ensure_future(
                    self._worker(i, queue, session, gate, meter, guard, rate,
                                 failed, progress)
                )
                for i in range(self.jobs)
            ]
            await queue.join()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        repaint_task.cancel()
        await asyncio.gather(repaint_task, return_exceptions=True)
        progress.draw(meter.last_sample(), gate.active)
        progress.finish()
        if controller is not None:
            controller.stop()
            if ctrl_task is not None:
                ctrl_task.cancel()
                await asyncio.gather(ctrl_task, return_exceptions=True)
        await meter.stop()
        self._controller = controller  # exposed for tests / trajectory logging
        self._progress = progress
        return failed

    async def _repaint(self, progress, meter, gate) -> None:
        """Repaint the live progress bar ~2.5 Hz until cancelled."""
        try:
            while True:
                progress.draw(meter.last_sample(), gate.active)
                await asyncio.sleep(0.4)
        except asyncio.CancelledError:
            return

    async def _worker(self, i, queue, session, gate, meter, guard, rate, failed,
                      progress=None):
        token = gate.token(i)
        while True:
            # Gate at the file-pickup boundary (NOTES §P3.5): an idle worker waits
            # here until its slot is active, then downloads one file to completion.
            # We deliberately do NOT cancel an in-flight download when the gate
            # lowers — interrupting + resuming mid-file risks corruption for no
            # real benefit. The controller still governs how many files download
            # at once; in-flight files simply finish.
            if not token.should_continue():
                await asyncio.sleep(0.15)
                continue
            try:
                task = queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)
                continue
            try:
                # Skip files already recorded as downloaded (Part 1 semantics).
                if in_success(self.workdir, Path(task.save_path).name):
                    if progress is not None:
                        progress.inc()
                    continue
                try:
                    ok = await self.engine.fetch_async(
                        task.url, task.save_path, session=session,
                        host_guard=guard, rate=rate, on_bytes=meter.on_bytes,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("download error for %s: %s", task.save_path, e)
                    ok = False

                if ok:
                    if progress is not None:
                        progress.inc()
                    log.info("downloaded %s", task.save_path)
                else:
                    task.retries += 1
                    if task.retries < 3:
                        queue.put_nowait(task)
                    else:
                        log.error("failed after retries: %s", task.save_path)
                        failed.add(task.save_path)
            finally:
                queue.task_done()


# ============================== parallel resolution ===========================

def _save_name_for(url: str, run: str) -> str:
    """Mirror Part 1's save names: fastq.gz keeps its basename; an .sra file is
    saved under the run id; GSA files keep their basename."""
    base = url.rsplit("/", 1)[-1]
    if ".fastq.gz" in url or url.endswith(".gz") or "." in base and not base.isalnum():
        return base
    return run


def _resolve_one(accession: str, options: Options, workdir: Path) -> List[DownloadTask]:
    """Run the Part 1 multi-database resolver for one accession and return tasks.

    Reuses the ENA-first / SRA-fallback / GSA / GEO preference chain unchanged.
    """
    ctx = RunContext(options=options, reporter=NullReporter(), workdir=workdir)
    ctx.accession = accession
    ctx.database = options.database
    tasks: List[DownloadTask] = []
    try:
        if is_gsa(accession):
            csv = ctx.metadata_csv(accession)
            if not (csv.exists() and csv.stat().st_size > 0):
                csv = _meta.get_gsa_metadata(ctx, accession)
            lines = csv.read_text(errors="replace").splitlines()
            crrs = sorted({ln.split(",")[0] for ln in lines[1:] if ln.split(",")[0]})
            for crr in crrs:
                for url in resolve_gsa_urls(ctx, crr):
                    tasks.append(DownloadTask(url, url.rsplit("/", 1)[-1], accession))
        else:
            tsv = ctx.metadata_tsv(accession)
            if not (tsv.exists() and tsv.stat().st_size > 0):
                tsv = _meta.get_sra_metadata(ctx, accession)
            lines = tsv.read_text(errors="replace").splitlines()
            for ln in lines[1:]:
                run = ln.split("\t")[0]
                if not run:
                    continue
                for url in resolve_sra_urls(ctx, run):
                    tasks.append(DownloadTask(url, _save_name_for(url, run), accession))
    except Exception as e:
        log.error("resolution failed for %s: %s", accession, e)
        raise
    return tasks


def resolve_all(
    accessions: List[str],
    options: Options,
    workdir: Path,
    *,
    meta_jobs: int = 3,
    on_task: Optional[Callable[[DownloadTask], None]] = None,
    skip_in_success: bool = True,
) -> Tuple[List[DownloadTask], List[str]]:
    """Resolve many accessions in parallel (bounded by ``meta_jobs``), throttled by
    per-endpoint rate limiters. Streams each resolved task to ``on_task`` as it
    completes (overlap with downloading). Returns (all_tasks, unresolved)."""
    workdir = Path(workdir)
    all_tasks: List[DownloadTask] = []
    unresolved: List[str] = []
    limiters = EndpointLimiters()
    set_active(limiters)
    try:
        n = max(1, min(len(accessions), int(meta_jobs)))
        with ThreadPoolExecutor(max_workers=n) as pool:
            futs = {pool.submit(_resolve_one, acc, options, workdir): acc
                    for acc in accessions}
            for fut in as_completed(futs):
                acc = futs[fut]
                try:
                    tasks = fut.result()
                except Exception:
                    unresolved.append(acc)
                    continue
                for t in tasks:
                    if skip_in_success and in_success(workdir, Path(t.save_path).name):
                        continue
                    all_tasks.append(t)
                    if on_task is not None:
                        on_task(t)
    finally:
        set_active(None)
    return all_tasks, unresolved
