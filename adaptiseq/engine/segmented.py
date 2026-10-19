"""Segmented, resumable HTTP(S) download engine (fixed concurrency).

Ported from FastBioDL (Swargo RM, Arslan E, Arifuzzaman M. "Adaptive Parallel
Downloader for Large Genomic Datasets." arXiv:2508.05511).

A self-contained port of ``SegmentedDownloader`` from ``fastbiodl_upgrade.py``
(L63-777), decoupled per the plan in ``NOTES.md`` §P2.1: the pause check, byte
counting, connection cap, disk gating, and output directory are all injected
rather than read from module globals or multiprocessing state.

Kept faithfully (spec §3): range probing, size-derived segment count, concurrent
ranged GETs written with ``os.pwrite`` and strict ``206`` validation, ``.part`` +
``.part.meta`` atomic resume, single-connection fallback, and per-segment retry
with exponential backoff. Discarded (spec §4): disk reservation, tmpfs, mp
counters, the in-engine converter, and ``ncbi_lookup``.

Concurrency is **fixed** in Part 2: each file opens
``min(max_segments, max(1, size // segment_size))`` segment connections, bounded
by the per-host cap. The optimizer is Part 3. The ``SegmentedEngine`` seam (which
wires this into the Part 1 download call site, including transport selection and
classic fallback) lives in :mod:`adaptiseq.engine.seam`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Callable, Dict, List, Optional, Set, Tuple

import aiohttp

from .ratelimit import HostGuard, TokenBucket, host_of

log = logging.getLogger("adaptiseq.engine.segmented")

CHUNK_SIZE = 1024 * 1024  # 1 MiB streaming chunks (as in the original)
PUSHBACK_STATUSES = (429, 503)
# A connect refused at the host's connection ceiling waits for a slot this long
# and this many times before it counts as a failed attempt.
CEILING_PAUSE_S = 0.5
MAX_CEILING_WAITS = 120
# Smallest segment a batch-tail split will make (see calculate_segments).
MIN_SPLIT = 64 * 1024 * 1024
# A running segment is split only if each half would get at least this much,
# and the split check runs this often while a file downloads.
MIN_STEAL = 16 * 1024 * 1024
SPLIT_POLL_S = 2.0
PROBE_ATTEMPTS = 4


class ProbeError(Exception):
    """The range probe got no answer from the server after its retries."""


class AlwaysRun:
    """The Part 2 pause token: never pauses. Part 3 swaps in the gradient gate."""

    def should_continue(self) -> bool:
        return True


def _noop_counter(_n: int) -> None:
    return None


# --- shared .part.meta resume helpers (reused by the FTP transport) -------------

def read_part_meta(meta_path: str) -> Optional[Dict]:
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def write_part_meta(
    meta_path: str,
    file_size: int,
    segments: List[Tuple[int, int]],
    completed: Set[int],
    partial_offsets: Optional[Dict[int, int]] = None,
) -> None:
    normalized: Dict[str, int] = {}
    if partial_offsets:
        for seg_idx, offset in partial_offsets.items():
            if seg_idx in completed:
                continue
            if seg_idx < 0 or seg_idx >= len(segments):
                continue
            seg_start, seg_end = segments[seg_idx]
            clamped = max(seg_start, min(int(offset), seg_end + 1))
            if clamped > seg_start:
                normalized[str(seg_idx)] = clamped
    metadata = {
        "file_size": file_size,
        "segments": [[s, e] for s, e in segments],
        "completed_indices": list(completed),
        "partial_offsets": normalized,
    }
    meta_tmp = meta_path + ".tmp"
    with open(meta_tmp, "w") as f:
        json.dump(metadata, f)
        f.flush()
        os.fsync(f.fileno())
    os.rename(meta_tmp, meta_path)


def load_partial_offsets(
    metadata: Dict, segments: List[Tuple[int, int]], completed: Set[int]
) -> Dict[int, int]:
    raw = metadata.get("partial_offsets", {})
    if not isinstance(raw, dict):
        return {}
    offsets: Dict[int, int] = {}
    for key, value in raw.items():
        try:
            seg_idx = int(key)
            offset = int(value)
        except (TypeError, ValueError):
            continue
        if seg_idx in completed or seg_idx < 0 or seg_idx >= len(segments):
            continue
        seg_start, seg_end = segments[seg_idx]
        clamped = max(seg_start, min(offset, seg_end + 1))
        if clamped >= seg_end + 1:
            completed.add(seg_idx)
            continue
        if clamped > seg_start:
            offsets[seg_idx] = clamped
    return offsets


def calculate_segments(
    file_size: int, *, min_file_size: int, max_segments: int, segment_size: int,
    target_segments: int = 0, min_split: int = 0,
) -> List[Tuple[int, int]]:
    """Size-derived segment plan (do not invert): small files -> 1 segment.

    ``target_segments`` raises the count, still within ``max_segments``, for a
    file the batch wants split finer than ``segment_size`` gives (the last files
    of a batch, when connections are free); no segment is made smaller than
    ``min_split``.
    """
    if file_size < min_file_size:
        return [(0, file_size - 1)]
    num_segments = min(max_segments, max(1, file_size // segment_size))
    if target_segments > num_segments:
        finest = max(1, file_size // max(1, min_split or MIN_SPLIT))
        num_segments = max(num_segments, min(max_segments, target_segments, finest))
    segment_list: List[Tuple[int, int]] = []
    bytes_per_segment = file_size // num_segments
    for i in range(num_segments):
        start = i * bytes_per_segment
        end = file_size - 1 if i == num_segments - 1 else (i + 1) * bytes_per_segment - 1
        segment_list.append((start, end))
    return segment_list


def plan_from_meta(
    metadata: Optional[Dict], file_size: int
) -> Optional[List[Tuple[int, int]]]:
    """The segment plan a ``.part.meta`` was written with, if it fits this file.

    A resumed download keeps the plan it started with, so a different split now
    (a batch tail asks for more segments) does not throw away the bytes already
    on disk. Only a plan that tiles ``0 .. file_size - 1`` exactly is accepted.
    """
    if not metadata or metadata.get("file_size") != file_size:
        return None
    raw = metadata.get("segments")
    if not isinstance(raw, list) or not raw:
        return None
    try:
        plan = [(int(a), int(b)) for a, b in raw]
    except (TypeError, ValueError):
        return None
    # Split segments are appended, so the stored order is not the byte order;
    # the indices must stay as stored (completed_indices refers to them).
    pos = 0
    for a, b in sorted(plan):
        if a != pos or b < a:
            return None
        pos = b + 1
    return plan if pos == file_size else None


def ensure_free_space(path: str, needed: int, margin: int = 0) -> None:
    """Single cheap pre-flight free-space check (out of any hot loop)."""
    try:
        free = shutil.disk_usage(os.path.dirname(path) or ".").free
    except Exception:
        return
    if free < needed + margin:
        raise OSError(f"Insufficient free space: need {needed + margin}, have {free}")


class SegmentedDownloader:
    """Download one resolved HTTP(S) URL to one output path, with resume."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        local_path: str,
        *,
        segment_size: int = 512 * 1024 * 1024,
        min_file_size_for_segmentation: int = 5 * 1024 * 1024,
        max_segments: int = 8,
        max_retries: int = 3,
        pause: Optional[object] = None,
        on_bytes: Optional[Callable[[int], None]] = None,
        host_guard: Optional[HostGuard] = None,
        rate: Optional[TokenBucket] = None,
        free_space_margin: int = 0,
        target_segments: int = 0,
        spare_slots: Optional[Callable[[], int]] = None,
    ):
        self.session = session
        self.url = url
        self.target_segments = max(0, int(target_segments))
        # Unused connection budget the batch could give this file (None: never
        # split for spare budget, only to replace a finished segment).
        self.spare_slots = spare_slots
        self.splits = 0
        self._ends: Dict[int, int] = {}
        self.local_path = local_path
        self.part_path = local_path + ".part"
        self.meta_path = local_path + ".part.meta"
        self.segment_size = segment_size
        self.min_file_size = min_file_size_for_segmentation
        self.max_segments = max_segments
        self.max_retries = max_retries
        self.pause = pause or AlwaysRun()
        self.on_bytes = on_bytes or _noop_counter
        self.host_guard = host_guard or HostGuard()
        self.rate = rate
        self.host = host_of(url)
        self.free_space_margin = max(0, int(free_space_margin))
        self.total_size = 0
        self.segments: List[Tuple[int, int]] = []

    # ------------------------------ metadata -----------------------------------

    def read_metadata(self) -> Optional[Dict]:
        return read_part_meta(self.meta_path)

    def write_metadata(
        self,
        file_size: int,
        segments: List[Tuple[int, int]],
        completed: Set[int],
        partial_offsets: Optional[Dict[int, int]] = None,
    ) -> None:
        write_part_meta(self.meta_path, file_size, segments, completed, partial_offsets)

    def _load_partial_offsets(
        self, metadata: Dict, segments: List[Tuple[int, int]], completed: Set[int]
    ) -> Dict[int, int]:
        return load_partial_offsets(metadata, segments, completed)

    # ------------------------------ probing ------------------------------------

    async def probe_range_support(self) -> Tuple[Optional[int], bool]:
        """``Range: bytes=0-0`` GET. 206 -> ranges + size; 200 -> no ranges.

        A probe that cannot get an answer at all (refused, reset, timed out) used
        to report "no ranges", and the whole file then went over one connection:
        in the 0.1.6 check, ENA refused a few probes and five 1.5 to 2 GB files
        downloaded single-stream for 15 to 30 min each. Now the probe takes a
        per-host slot like a segment, waits at the host's connection ceiling, and
        retries; if it still gets no answer it raises, so the file fails and the
        batch retries it later instead of degrading it.
        """
        headers = {"Range": "bytes=0-0"}
        attempt = 0
        ceiling_waits = 0
        while True:
            try:
                async with self.host_guard.connection(self.host):
                    async with self.session.get(
                        self.url, headers=headers, allow_redirects=True
                    ) as resp:
                        if resp.status == 206:
                            file_size = None
                            content_range = resp.headers.get("Content-Range", "")
                            if "/" in content_range:
                                try:
                                    file_size = int(content_range.split("/")[-1])
                                except Exception:
                                    pass
                            return file_size, True
                        elif resp.status == 200:
                            cl = resp.headers.get("Content-Length")
                            return (int(cl) if cl else None), False
                        return None, False
            except asyncio.CancelledError:
                raise
            except aiohttp.ClientConnectorError as e:
                if (await self.host_guard.note_refused(self.host)
                        and ceiling_waits < MAX_CEILING_WAITS):
                    ceiling_waits += 1
                    await asyncio.sleep(CEILING_PAUSE_S)
                    continue
                err = e
            except Exception as e:
                err = e
            attempt += 1
            log.warning("Range probe attempt %s/%s failed for %s: %s", attempt,
                        PROBE_ATTEMPTS, os.path.basename(self.local_path), err)
            if attempt >= PROBE_ATTEMPTS:
                raise ProbeError(f"no answer to the range probe for {self.url}: {err}")
            await asyncio.sleep(2 ** (attempt - 1))

    def calculate_segments(self, file_size: int) -> List[Tuple[int, int]]:
        return calculate_segments(
            file_size,
            min_file_size=self.min_file_size,
            max_segments=self.max_segments,
            segment_size=self.segment_size,
            target_segments=self.target_segments,
        )

    # ------------------------------ streaming ----------------------------------

    async def download_segment_streaming(
        self,
        segment_id: int,
        start: int,
        end: int,
        fd: int,
        progress_offsets: Dict[int, int],
    ) -> Tuple[int, int]:
        """One ranged GET written at the right offset; strict 206 validation.

        The segment's end can move down while it runs: a split hands the second
        half of what is left to a new connection (see ``_split_largest``). The
        response was asked for the old range, so writes are clipped at the new
        end and the rest of the body is not read.
        """
        bytes_written = 0
        current_offset = start
        progress_offsets[segment_id] = start
        self._ends.setdefault(segment_id, end)

        attempt = 0
        ceiling_waits = 0
        while attempt < self.max_retries:
            end = self._ends[segment_id]
            if current_offset > end:
                progress_offsets[segment_id] = end + 1
                return segment_id, bytes_written
            req_start = current_offset
            req_end = end
            headers = {"Range": f"bytes={req_start}-{req_end}"}
            try:
                async with self.host_guard.connection(self.host):
                    async with self.session.get(self.url, headers=headers) as resp:
                        if resp.status in PUSHBACK_STATUSES:
                            await self.host_guard.note_pushback(
                                self.host, str(resp.status)
                            )
                            raise Exception(f"Host pushback: HTTP {resp.status}")
                        if resp.status != 206:
                            raise Exception(
                                f"Expected 206 Partial Content for Range request, got "
                                f"{resp.status}. Server may not support ranges."
                            )
                        content_range = resp.headers.get("Content-Range", "")
                        if not content_range:
                            raise Exception("206 with no Content-Range header")
                        if not content_range.startswith("bytes "):
                            raise Exception(f"Invalid Content-Range: {content_range}")
                        try:
                            range_part = content_range.split()[1]
                            returned_range = range_part.split("/")[0]
                            r_start, r_end = map(int, returned_range.split("-"))
                            if r_start != req_start or r_end != req_end:
                                raise Exception(
                                    f"Server returned different range: asked "
                                    f"{req_start}-{req_end}, got {r_start}-{r_end}"
                                )
                        except Exception as e:
                            raise Exception(f"Bad Content-Range '{content_range}': {e}")

                        await self.host_guard.note_success(self.host)
                        async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                            if not self.pause.should_continue():
                                raise asyncio.CancelledError("paused")
                            if self.rate is not None:
                                await self.rate.acquire(len(chunk))
                            end = self._ends[segment_id]
                            if current_offset + len(chunk) > end + 1:
                                chunk = chunk[:max(0, end + 1 - current_offset)]
                            n = len(chunk)
                            if n:
                                os.pwrite(fd, chunk, current_offset)
                                current_offset += n
                                bytes_written += n
                                progress_offsets[segment_id] = current_offset
                                self.on_bytes(n)
                            if current_offset > end:
                                break   # the rest now belongs to another segment

                end = self._ends[segment_id]
                if current_offset != end + 1:
                    raise Exception(
                        f"Incomplete segment: expected {end - req_start + 1}, "
                        f"got {current_offset - req_start}"
                    )
                progress_offsets[segment_id] = end + 1
                return segment_id, bytes_written
            except asyncio.CancelledError:
                raise
            except aiohttp.ClientConnectorError as e:
                # Refused at connect: nothing was written. If other connections to
                # the host are open this is its connection ceiling; the guard now
                # holds the cap there, so wait for a slot without spending one of
                # the segment's attempts (the whole file is retried otherwise).
                if (await self.host_guard.note_refused(self.host)
                        and ceiling_waits < MAX_CEILING_WAITS):
                    ceiling_waits += 1
                    log.info("Segment %s refused at the host's connection ceiling; "
                             "waiting for a slot", segment_id)
                    await asyncio.sleep(CEILING_PAUSE_S)
                    continue
                log.warning(
                    "Segment %s attempt %s refused: %s", segment_id, attempt + 1, e
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
            except aiohttp.ClientConnectionError as e:
                await self.host_guard.note_pushback(self.host, "refused")
                log.warning(
                    "Segment %s attempt %s refused: %s", segment_id, attempt + 1, e
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
            except Exception as e:
                if isinstance(e, aiohttp.ClientPayloadError):
                    await self.host_guard.note_truncated(self.host)
                log.warning(
                    "Segment %s attempt %s/%s failed: %s",
                    segment_id, attempt + 1, self.max_retries, e,
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
            attempt += 1
        return segment_id, bytes_written

    # ------------------------------ orchestration ------------------------------

    def _ensure_free_space(self, needed: int) -> None:
        ensure_free_space(self.local_path, needed, self.free_space_margin)

    async def download_with_resume(self) -> Tuple[bool, bool, int]:
        if not os.path.exists(self.local_path) and not os.path.exists(self.part_path):
            return await self.download_segmented()

        file_size, supports_ranges = await self.probe_range_support()

        if os.path.exists(self.local_path):
            if file_size and os.path.getsize(self.local_path) == file_size:
                log.info("Already complete: %s", os.path.basename(self.local_path))
                self.on_bytes(file_size)
                return True, False, 0

        if file_size is None:
            return await self.download_single_connection(supports_ranges=False)

        existing_size = 0
        if os.path.exists(self.part_path):
            existing_size = os.path.getsize(self.part_path)
            if existing_size > file_size:
                os.remove(self.part_path)
                existing_size = 0

        if not supports_ranges:
            remaining = max(0, file_size - existing_size)
            return await self.download_single_connection(
                supports_ranges=False,
                resume_from=existing_size,
                expected_remaining_bytes=remaining,
            )
        return await self.download_segmented(file_size)

    async def download_segmented(
        self, file_size: Optional[int] = None
    ) -> Tuple[bool, bool, int]:
        if file_size is None:
            file_size, supports = await self.probe_range_support()
            if not supports:
                return await self.download_single_connection(
                    supports_ranges=False,
                    expected_remaining_bytes=file_size or 0,
                )
            if file_size is None:
                return await self.download_single_connection(supports_ranges=False)

        metadata = self.read_metadata()
        segments = plan_from_meta(metadata, file_size) or self.calculate_segments(file_size)
        completed: Set[int] = set()
        partial_offsets: Dict[int, int] = {}
        if metadata:
            if metadata.get("file_size") == file_size and metadata.get(
                "segments"
            ) == [[s, e] for s, e in segments]:
                completed = set(metadata.get("completed_indices", []))
                partial_offsets = self._load_partial_offsets(
                    metadata, segments, completed
                )
                if len(completed) < len(segments) and not os.path.exists(self.part_path):
                    # resume state without the bytes it describes (e.g. the md5
                    # check deleted a finished file whose .part.meta was left
                    # behind): resuming would write only the unfinished segments
                    # into a new .part and leave the rest as zeros
                    log.warning(
                        "Stale resume metadata for %s (.part missing); restarting",
                        os.path.basename(self.local_path),
                    )
                    os.remove(self.meta_path)
                    completed, partial_offsets = set(), {}
                log.info(
                    "Resume: %s/%s segments complete for %s",
                    len(completed), len(segments), os.path.basename(self.local_path),
                )
            else:
                log.warning(
                    "Metadata mismatch, restarting: %s",
                    os.path.basename(self.local_path),
                )
                for p in (self.meta_path, self.part_path):
                    if os.path.exists(p):
                        os.remove(p)
                completed, partial_offsets = set(), {}

        remaining_segments = [
            (i, partial_offsets.get(i, start), end)
            for i, (start, end) in enumerate(segments)
            if i not in completed
        ]

        if not remaining_segments:
            if os.path.exists(self.part_path):
                os.replace(self.part_path, self.local_path)
                if os.path.exists(self.meta_path):
                    os.remove(self.meta_path)
                return True, False, 0
            if os.path.exists(self.local_path):
                # already finalized on a prior run; the metadata was just stale
                if os.path.exists(self.meta_path):
                    os.remove(self.meta_path)
                return True, False, 0
            # metadata claims completion but neither .part nor the final file
            # exists: it is stale/inconsistent. Discard it and fail cleanly so the
            # batch retry re-downloads from scratch (instead of raising rename's
            # FileNotFoundError).
            log.warning(
                "Stale resume metadata for %s (.part missing); will re-download",
                os.path.basename(self.local_path),
            )
            if os.path.exists(self.meta_path):
                os.remove(self.meta_path)
            return False, False, 0

        remaining_bytes = sum((e - s + 1) for _, s, e in remaining_segments)
        self._ensure_free_space(remaining_bytes)

        os.makedirs(os.path.dirname(self.part_path) or ".", exist_ok=True)
        num_connections = len(remaining_segments)
        progress_offsets: Dict[int, int] = {i: s for i, s, _ in remaining_segments}
        # The plan grows when a segment is split; it always tiles the file, so
        # .part.meta written from it resumes correctly (plan_from_meta).
        segments = [list(x) for x in segments]
        self._ends = {i: e for i, (_s, e) in enumerate(segments)}

        fd = None
        running: Dict["asyncio.Future", int] = {}
        try:
            fd = os.open(self.part_path, os.O_CREAT | os.O_RDWR)
            for i, s0, e0 in remaining_segments:
                running[asyncio.ensure_future(
                    self.download_segment_streaming(i, s0, e0, fd, progress_offsets))] = i
            results = await self._run_segments(running, segments, remaining_segments,
                                               progress_offsets, fd)

            paused = any(isinstance(r, asyncio.CancelledError) for r in results)
            errors = [
                r
                for r in results
                if isinstance(r, Exception)
                and not isinstance(r, asyncio.CancelledError)
            ]
            for r in results:
                if isinstance(r, tuple):
                    completed.add(r[0])

            latest = self._partials(remaining_segments, progress_offsets, completed)

            if paused:
                self.write_metadata(file_size, segments, completed, latest)
                return False, True, num_connections

            if len(completed) == len(segments):
                os.close(fd)
                fd = None
                if os.path.exists(self.part_path):
                    os.replace(self.part_path, self.local_path)
                    if os.path.exists(self.meta_path):
                        os.remove(self.meta_path)
                    log.info("Completed %s", os.path.basename(self.local_path))
                    return True, False, num_connections
                # All segments report complete but the .part file is gone —
                # inconsistent on-disk state. Fail cleanly (drop stale metadata)
                # so the batch retry re-downloads, rather than raising rename's
                # FileNotFoundError.
                log.error(
                    "%s: segments complete but .part missing; will retry",
                    os.path.basename(self.local_path),
                )
                if os.path.exists(self.meta_path):
                    os.remove(self.meta_path)
                return False, False, num_connections

            self.write_metadata(file_size, segments, completed, latest)
            if errors:
                log.error(
                    "Segment errors for %s: %s",
                    os.path.basename(self.local_path), errors[0],
                )
            return False, False, num_connections
        except asyncio.CancelledError:
            for t in running:
                t.cancel()
            await asyncio.gather(*running, return_exceptions=True)
            latest = self._partials(remaining_segments, progress_offsets, completed)
            self.write_metadata(file_size, segments, completed, latest)
            return False, True, num_connections
        except Exception as e:
            latest = self._partials(remaining_segments, progress_offsets, completed)
            self.write_metadata(file_size, segments, completed, latest)
            log.error("Failed %s: %s", os.path.basename(self.local_path), e)
            return False, False, num_connections
        finally:
            if fd is not None:
                os.close(fd)

    async def _run_segments(self, running, segments, remaining_segments,
                            progress_offsets, fd) -> list:
        """Wait for the segment tasks like ``gather(return_exceptions=True)``, but
        keep the file's connections busy while it runs.

        A file's split is fixed at its start, so its last bytes used to arrive on
        one slow connection while the others sat idle (panel 3b of the full run:
        the last 5 files on about 5 connections for 15 min). Now, when a segment
        finishes, its connection takes over the second half of the largest
        remainder. And when ``spare_slots`` (the batch) reports unused connection
        budget, the file splits again, up to ``max_segments`` connections.
        """
        results = []
        failed = False
        while running:
            done, _ = await asyncio.wait(list(running), timeout=SPLIT_POLL_S,
                                         return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                running.pop(t)
                try:
                    results.append(t.result())
                except BaseException as exc:   # CancelledError included, as gather would
                    results.append(exc)
                    failed = True
                    continue
                if not failed:
                    self._split_largest(running, segments, remaining_segments,
                                        progress_offsets, fd)
            if (not failed and running and self.spare_slots is not None
                    and len(running) < self.max_segments and self.spare_slots() > 0):
                self._split_largest(running, segments, remaining_segments,
                                    progress_offsets, fd)
        return results

    def _split_largest(self, running, segments, remaining_segments, progress_offsets,
                       fd) -> bool:
        """Give the second half of the largest running remainder to a new segment."""
        best, best_left = None, 0
        for i in running.values():
            left = self._ends[i] + 1 - progress_offsets.get(i, segments[i][0])
            if left > best_left:
                best, best_left = i, left
        if best is None or best_left < 2 * MIN_STEAL:
            return False
        cut = progress_offsets.get(best, segments[best][0]) + best_left // 2
        new_end = self._ends[best]
        self._ends[best] = cut - 1
        segments[best][1] = cut - 1
        j = len(segments)
        segments.append([cut, new_end])
        self._ends[j] = new_end
        for k, (i, s0, _e0) in enumerate(remaining_segments):
            if i == best:
                remaining_segments[k] = (i, s0, cut - 1)
        remaining_segments.append((j, cut, new_end))
        progress_offsets[j] = cut
        running[asyncio.ensure_future(
            self.download_segment_streaming(j, cut, new_end, fd, progress_offsets))] = j
        self.splits += 1
        log.info("Split segment %s of %s at %s (%s MiB to a new connection)", best,
                 os.path.basename(self.local_path), cut, (new_end - cut + 1) >> 20)
        return True

    @staticmethod
    def _partials(remaining_segments, progress_offsets, completed) -> Dict[int, int]:
        out: Dict[int, int] = {}
        for seg_id, seg_start, seg_end in remaining_segments:
            if seg_id in completed:
                continue
            latest = progress_offsets.get(seg_id, seg_start)
            latest = max(seg_start, min(latest, seg_end + 1))
            if latest >= seg_end + 1:
                completed.add(seg_id)
                continue
            if latest > seg_start:
                out[seg_id] = latest
        return out

    async def download_single_connection(
        self,
        supports_ranges: bool = True,
        resume_from: int = 0,
        expected_remaining_bytes: int = 0,
    ) -> Tuple[bool, bool, int]:
        if expected_remaining_bytes:
            self._ensure_free_space(expected_remaining_bytes)
        for attempt in range(self.max_retries):
            try:
                headers = {}
                if resume_from > 0 and supports_ranges:
                    headers["Range"] = f"bytes={resume_from}-"
                os.makedirs(os.path.dirname(self.part_path) or ".", exist_ok=True)
                async with self.host_guard.connection(self.host):
                    async with self.session.get(self.url, headers=headers) as resp:
                        if resp.status in PUSHBACK_STATUSES:
                            await self.host_guard.note_pushback(
                                self.host, str(resp.status)
                            )
                            raise Exception(f"Host pushback: HTTP {resp.status}")
                        if resume_from > 0 and supports_ranges:
                            if resp.status == 206:
                                initial_offset = resume_from
                            elif resp.status == 200:
                                initial_offset = 0
                                if os.path.exists(self.part_path):
                                    os.remove(self.part_path)
                            else:
                                raise Exception(f"Unexpected status {resp.status}")
                        else:
                            if resp.status != 200:
                                raise Exception(f"Expected 200 OK, got {resp.status}")
                            initial_offset = 0
                        await self.host_guard.note_success(self.host)

                        fd = None
                        current_offset = initial_offset
                        try:
                            flags = os.O_CREAT | os.O_RDWR
                            if initial_offset == 0:
                                # whole file from the start: nothing of an older
                                # .part may survive past the new end
                                flags |= os.O_TRUNC
                            fd = os.open(self.part_path, flags)
                            os.lseek(fd, initial_offset, os.SEEK_SET)
                            async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                                if not self.pause.should_continue():
                                    raise asyncio.CancelledError("paused")
                                if self.rate is not None:
                                    await self.rate.acquire(len(chunk))
                                os.write(fd, chunk)
                                current_offset += len(chunk)
                                self.on_bytes(len(chunk))
                            os.close(fd)
                            fd = None
                            os.rename(self.part_path, self.local_path)
                            # the segmented attempt that may have run before
                            # this one left its resume state; it is now stale
                            if os.path.exists(self.meta_path):
                                os.remove(self.meta_path)
                            log.info("Completed %s", os.path.basename(self.local_path))
                            return True, False, 1
                        finally:
                            if fd is not None:
                                os.close(fd)
            except asyncio.CancelledError:
                return False, True, 1
            except Exception as e:
                log.warning(
                    "Single-conn attempt %s/%s failed: %s",
                    attempt + 1, self.max_retries, e,
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    log.error("Failed %s: %s", os.path.basename(self.local_path), e)
                    return False, False, 1
        return False, False, 1

    async def download(self) -> bool:
        """Top-level entry: returns True on success."""
        success, _paused, _conns = await self.download_with_resume()
        return success
