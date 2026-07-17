"""Segmented, resumable HTTP(S) download engine (fixed concurrency).

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
    file_size: int, *, min_file_size: int, max_segments: int, segment_size: int
) -> List[Tuple[int, int]]:
    """Size-derived segment plan (do not invert): small files -> 1 segment."""
    if file_size < min_file_size:
        return [(0, file_size - 1)]
    num_segments = min(max_segments, max(1, file_size // segment_size))
    segment_list: List[Tuple[int, int]] = []
    bytes_per_segment = file_size // num_segments
    for i in range(num_segments):
        start = i * bytes_per_segment
        end = file_size - 1 if i == num_segments - 1 else (i + 1) * bytes_per_segment - 1
        segment_list.append((start, end))
    return segment_list


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
        on_segments: Optional[Callable[[str, Dict], None]] = None,
    ):
        self.session = session
        self.url = url
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
        self.on_segments = on_segments
        self.host = host_of(url)
        self.free_space_margin = max(0, int(free_space_margin))
        self.total_size = 0
        self.segments: List[Tuple[int, int]] = []

    def _emit_segments(
        self,
        event: str,
        *,
        file_size: int,
        segments: List[Tuple[int, int]],
        completed: Set[int],
        progress_offsets: Dict[int, int],
    ) -> None:
        if self.on_segments is None:
            return
        try:
            self.on_segments(
                event,
                {
                    "event": event,
                    "file_size": file_size,
                    "segments": list(segments),
                    "completed": set(completed),
                    "progress_offsets": dict(progress_offsets),
                },
            )
        except Exception as e:
            log.debug("segment progress callback failed for %s: %s", self.local_path, e)

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
        """Single ``Range: bytes=0-0`` GET. 206 -> ranges + size; 200 -> no ranges."""
        try:
            headers = {"Range": "bytes=0-0"}
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
        except Exception as e:
            log.debug("Range probe failed for %s: %s", self.url, e)
            return None, False

    def calculate_segments(self, file_size: int) -> List[Tuple[int, int]]:
        return calculate_segments(
            file_size,
            min_file_size=self.min_file_size,
            max_segments=self.max_segments,
            segment_size=self.segment_size,
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
        """One ranged GET written at the right offset; strict 206 validation."""
        bytes_written = 0
        current_offset = start
        progress_offsets[segment_id] = start

        for attempt in range(self.max_retries):
            req_start = current_offset
            req_end = end
            expected_bytes = req_end - req_start + 1
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
                            os.pwrite(fd, chunk, current_offset)
                            n = len(chunk)
                            current_offset += n
                            bytes_written += n
                            progress_offsets[segment_id] = current_offset
                            self._emit_segments(
                                "progress",
                                file_size=self.total_size,
                                segments=self.segments,
                                completed=set(),
                                progress_offsets=progress_offsets,
                            )
                            self.on_bytes(n)

                bytes_received = current_offset - req_start
                if bytes_received != expected_bytes:
                    raise Exception(
                        f"Incomplete segment: expected {expected_bytes}, "
                        f"got {bytes_received}"
                    )
                progress_offsets[segment_id] = end + 1
                return segment_id, bytes_written
            except asyncio.CancelledError:
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
                log.warning(
                    "Segment %s attempt %s/%s failed: %s",
                    segment_id, attempt + 1, self.max_retries, e,
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
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

        segments = self.calculate_segments(file_size)
        self.total_size = file_size
        self.segments = segments

        metadata = self.read_metadata()
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
        self._emit_segments(
            "planned",
            file_size=file_size,
            segments=segments,
            completed=completed,
            progress_offsets=progress_offsets,
        )

        fd = None
        try:
            fd = os.open(self.part_path, os.O_CREAT | os.O_RDWR)
            tasks = [
                self.download_segment_streaming(i, s, e, fd, progress_offsets)
                for i, s, e in remaining_segments
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

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
                self._emit_segments(
                    "paused",
                    file_size=file_size,
                    segments=segments,
                    completed=completed,
                    progress_offsets=latest,
                )
                return False, True, num_connections

            if len(completed) == len(segments):
                os.close(fd)
                fd = None
                if os.path.exists(self.part_path):
                    os.replace(self.part_path, self.local_path)
                    if os.path.exists(self.meta_path):
                        os.remove(self.meta_path)
                    log.info("Completed %s", os.path.basename(self.local_path))
                    self._emit_segments(
                        "complete",
                        file_size=file_size,
                        segments=segments,
                        completed=completed,
                        progress_offsets={
                            i: e + 1 for i, (_s, e) in enumerate(segments)
                        },
                    )
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
            self._emit_segments(
                "failed",
                file_size=file_size,
                segments=segments,
                completed=completed,
                progress_offsets=latest,
            )
            return False, False, num_connections
        except asyncio.CancelledError:
            latest = self._partials(remaining_segments, progress_offsets, completed)
            self.write_metadata(file_size, segments, completed, latest)
            self._emit_segments(
                "paused",
                file_size=file_size,
                segments=segments,
                completed=completed,
                progress_offsets=latest,
            )
            return False, True, num_connections
        except Exception as e:
            latest = self._partials(remaining_segments, progress_offsets, completed)
            self.write_metadata(file_size, segments, completed, latest)
            self._emit_segments(
                "failed",
                file_size=file_size,
                segments=segments,
                completed=completed,
                progress_offsets=latest,
            )
            log.error("Failed %s: %s", os.path.basename(self.local_path), e)
            return False, False, num_connections
        finally:
            if fd is not None:
                os.close(fd)

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
                        content_length = int(resp.headers.get("Content-Length") or 0)
                        total_size = (
                            initial_offset + content_length
                            if content_length else expected_remaining_bytes or 0
                        )
                        single_segments = (
                            [(0, total_size - 1)] if total_size > 0 else [(0, 0)]
                        )
                        single_progress = {0: current_offset}
                        self._emit_segments(
                            "planned",
                            file_size=total_size,
                            segments=single_segments,
                            completed=set(),
                            progress_offsets=single_progress,
                        )
                        try:
                            fd = os.open(self.part_path, os.O_CREAT | os.O_RDWR)
                            os.lseek(fd, initial_offset, os.SEEK_SET)
                            async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                                if not self.pause.should_continue():
                                    raise asyncio.CancelledError("paused")
                                if self.rate is not None:
                                    await self.rate.acquire(len(chunk))
                                os.write(fd, chunk)
                                current_offset += len(chunk)
                                single_progress[0] = current_offset
                                self._emit_segments(
                                    "progress",
                                    file_size=total_size,
                                    segments=single_segments,
                                    completed=set(),
                                    progress_offsets=single_progress,
                                )
                                self.on_bytes(len(chunk))
                            os.close(fd)
                            fd = None
                            os.rename(self.part_path, self.local_path)
                            log.info("Completed %s", os.path.basename(self.local_path))
                            self._emit_segments(
                                "complete",
                                file_size=total_size,
                                segments=single_segments,
                                completed={0},
                                progress_offsets={0: single_segments[0][1] + 1},
                            )
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
