"""Native segmented FTP transport (REST + RETR) via ``aioftp``.

Part 2 (spec §5): FTP can be segmented and resumed too. Each segment opens its own
control+data connection, issues ``REST <start>`` then ``RETR <file>``, reads
exactly ``end - start + 1`` bytes (bounding its own reads — FTP has no server-side
end offset), and writes them at the right offset with ``os.pwrite``. The same
``.part`` + ``.part.meta`` resume metadata as the HTTP engine applies unchanged
(reused from :mod:`adaptiseq.engine.segmented`). There is no ``Content-Range`` to
validate, so correctness is enforced by exact byte-count accounting and a final
size check, and short reads are treated strictly.

Depends only on ``aioftp``, the standard library, and our own
:mod:`adaptiseq.engine.ratelimit` / :mod:`adaptiseq.engine.segmented` helpers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

import aioftp

from .ratelimit import HostGuard, TokenBucket
from .segmented import (
    AlwaysRun,
    calculate_segments,
    ensure_free_space,
    load_partial_offsets,
    read_part_meta,
    write_part_meta,
)

log = logging.getLogger("adaptiseq.engine.ftp")

CHUNK_SIZE = 1024 * 1024
DEFAULT_USER = "anonymous"
DEFAULT_PASSWORD = "anonymous@"


def parse_ftp_url(url: str) -> Tuple[str, int, str]:
    """Return ``(host, port, path)`` for an ``ftp://`` URL."""
    p = urlparse(url)
    return p.hostname or "", (p.port or 21), unquote(p.path)


async def _connect(host: str, port: int) -> aioftp.Client:
    client = aioftp.Client()
    await client.connect(host, port)
    await client.login(DEFAULT_USER, DEFAULT_PASSWORD)
    return client


async def _ftp_size(client: aioftp.Client, path: str) -> Optional[int]:
    """Best-effort total size via the ``SIZE`` command, then MLST/stat fallback."""
    try:
        code, info = await client.command("SIZE " + path, "213")
        if info:
            return int(info[-1].strip())
    except Exception:
        pass
    try:
        stat = await client.stat(path)
        size = stat.get("size") if isinstance(stat, dict) else None
        return int(size) if size is not None else None
    except Exception:
        return None


async def probe_ftp(host: str, port: int, path: str) -> Tuple[Optional[int], bool, bool]:
    """Probe ``(size, rest_supported, concurrency_ok)`` for an FTP host (spec §5.1).

    ``rest_supported`` is confirmed by a ``REST`` at a non-zero offset returning
    data; ``concurrency_ok`` by opening a second data connection alongside.
    """
    size = None
    rest_ok = False
    concurrency_ok = False
    client = None
    client2 = None
    try:
        client = await _connect(host, port)
        size = await _ftp_size(client, path)

        # Concurrency: a second control connection accepted alongside the first
        # (this is exactly what EBI caps per IP). Done before the REST probe so an
        # early-aborted transfer cannot disturb the ordering.
        try:
            client2 = await _connect(host, port)
            await _ftp_size(client2, path)
            concurrency_ok = True
        except Exception as e:
            log.debug("FTP concurrency probe failed for %s: %s", host, e)

        # REST: a transfer started at a non-zero offset returns data.
        offset = 1 if (size or 0) > 2 else 0
        try:
            async with client.download_stream(path, offset=offset) as stream:
                async for _block in stream.iter_by_block(64 * 1024):
                    rest_ok = True
                    break
        except Exception as e:
            log.debug("FTP REST probe failed for %s: %s", host, e)
    except Exception as e:
        log.debug("FTP probe could not connect to %s:%s: %s", host, port, e)
    finally:
        for c in (client, client2):
            if c is not None:
                try:
                    await c.quit()
                except Exception:
                    pass
    return size, rest_ok, concurrency_ok


class FtpSegmentedDownloader:
    """Segmented, resumable native-FTP download of one URL to one path."""

    def __init__(
        self,
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
    ):
        self.url = url
        self.host, self.port, self.path = parse_ftp_url(url)
        self.local_path = local_path
        self.part_path = local_path + ".part"
        self.meta_path = local_path + ".part.meta"
        self.segment_size = segment_size
        self.min_file_size = min_file_size_for_segmentation
        self.max_segments = max_segments
        self.max_retries = max_retries
        self.pause = pause or AlwaysRun()
        self.on_bytes = on_bytes or (lambda _n: None)
        self.host_guard = host_guard or HostGuard()
        self.rate = rate
        self.free_space_margin = max(0, int(free_space_margin))

    def calculate_segments(self, file_size: int) -> List[Tuple[int, int]]:
        return calculate_segments(
            file_size,
            min_file_size=self.min_file_size,
            max_segments=self.max_segments,
            segment_size=self.segment_size,
        )

    async def _download_segment(
        self, seg_id: int, start: int, end: int, fd: int, progress: Dict[int, int]
    ) -> Tuple[int, int]:
        offset = start
        progress[seg_id] = start
        for attempt in range(self.max_retries):
            need = end - offset + 1
            if need <= 0:
                progress[seg_id] = end + 1
                return seg_id, end - start + 1
            try:
                async with self.host_guard.connection(self.host):
                    client = await _connect(self.host, self.port)
                    try:
                        async with client.download_stream(self.path, offset=offset) as stream:
                            async for block in stream.iter_by_block(CHUNK_SIZE):
                                if not self.pause.should_continue():
                                    raise asyncio.CancelledError("paused")
                                remaining = end - offset + 1
                                if remaining <= 0:
                                    break
                                take = block[:remaining]
                                if self.rate is not None:
                                    await self.rate.acquire(len(take))
                                os.pwrite(fd, take, offset)
                                offset += len(take)
                                progress[seg_id] = offset
                                self.on_bytes(len(take))
                                if offset > end:
                                    break
                    finally:
                        try:
                            await client.quit()
                        except Exception:
                            pass
                if offset != end + 1:
                    raise Exception(
                        f"FTP segment short read: at {offset}, expected end {end}"
                    )
                progress[seg_id] = end + 1
                return seg_id, end - start + 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await self.host_guard.note_pushback(self.host, "ftp-error")
                log.warning(
                    "FTP segment %s attempt %s/%s failed: %s",
                    seg_id, attempt + 1, self.max_retries, e,
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        return seg_id, offset - start

    async def download(self, file_size: Optional[int] = None) -> bool:
        if file_size is None:
            client = None
            try:
                client = await _connect(self.host, self.port)
                file_size = await _ftp_size(client, self.path)
            except Exception as e:
                log.error("FTP connect/size failed for %s: %s", self.url, e)
                return False
            finally:
                if client is not None:
                    try:
                        await client.quit()
                    except Exception:
                        pass
        if not file_size:
            log.error("FTP could not determine size for %s", self.url)
            return False

        if os.path.exists(self.local_path) and os.path.getsize(self.local_path) == file_size:
            self.on_bytes(file_size)
            return True

        segments = self.calculate_segments(file_size)
        meta = read_part_meta(self.meta_path)
        completed: Set[int] = set()
        partial: Dict[int, int] = {}
        if meta:
            if meta.get("file_size") == file_size and meta.get("segments") == [
                [s, e] for s, e in segments
            ]:
                completed = set(meta.get("completed_indices", []))
                partial = load_partial_offsets(meta, segments, completed)
            else:
                for p in (self.meta_path, self.part_path):
                    if os.path.exists(p):
                        os.remove(p)

        remaining = [
            (i, partial.get(i, s), e)
            for i, (s, e) in enumerate(segments)
            if i not in completed
        ]
        if not remaining:
            if os.path.exists(self.part_path):
                os.rename(self.part_path, self.local_path)
            if os.path.exists(self.meta_path):
                os.remove(self.meta_path)
            return True

        ensure_free_space(
            self.local_path,
            sum((e - s + 1) for _, s, e in remaining),
            self.free_space_margin,
        )
        os.makedirs(os.path.dirname(self.part_path) or ".", exist_ok=True)
        progress: Dict[int, int] = {i: s for i, s, _ in remaining}

        fd = None
        try:
            fd = os.open(self.part_path, os.O_CREAT | os.O_RDWR)
            results = await asyncio.gather(
                *[self._download_segment(i, s, e, fd, progress) for i, s, e in remaining],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, tuple):
                    completed.add(r[0])
            latest = {}
            for seg_id, s, e in remaining:
                if seg_id in completed:
                    continue
                off = max(s, min(progress.get(seg_id, s), e + 1))
                if off >= e + 1:
                    completed.add(seg_id)
                elif off > s:
                    latest[seg_id] = off

            if len(completed) == len(segments):
                os.close(fd)
                fd = None
                os.rename(self.part_path, self.local_path)
                if os.path.exists(self.meta_path):
                    os.remove(self.meta_path)
                # final size check (no Content-Range to trust)
                if os.path.getsize(self.local_path) != file_size:
                    log.error("FTP final size mismatch for %s", self.local_path)
                    return False
                log.info("Completed (ftp) %s", os.path.basename(self.local_path))
                return True
            write_part_meta(self.meta_path, file_size, segments, completed, latest)
            return False
        except Exception as e:
            log.error("FTP download failed for %s: %s", self.url, e)
            try:
                latest = {}
                write_part_meta(self.meta_path, file_size, segments, completed, latest)
            except Exception:
                pass
            return False
        finally:
            if fd is not None:
                os.close(fd)
