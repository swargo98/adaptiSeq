"""Part 2 native segmented FTP: probe + byte-identical download against aioftp.

These exercise the FTP transport live against a local ``aioftp`` server: the
``REST``/concurrency probe and the segmented REST/RETR download with exact
byte-count accounting (FTP has no Content-Range to validate).
"""

import asyncio
import hashlib
import logging
import os

import aioftp
import pytest

from adaptiseq.engine.ftp import FtpSegmentedDownloader, probe_ftp
from adaptiseq.engine.ratelimit import HostGuard

# aioftp logs a benign "dispatcher caught exception" when we abort a RETR early
# (expected when a segment's byte budget is filled); keep test output clean.
logging.getLogger("aioftp").setLevel(logging.CRITICAL)


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


async def _with_server(srcdir, fn):
    user = aioftp.User(
        login="anonymous",
        base_path=srcdir,
        permissions=[aioftp.Permission("/", readable=True, writable=False)],
    )
    server = aioftp.Server([user])
    await server.start("127.0.0.1", 0)
    port = server.server.sockets[0].getsockname()[1]
    try:
        return await fn(port)
    finally:
        await server.close()


def test_ftp_probe_reports_size_rest_concurrency(tmp_path):
    data = os.urandom(4 * 1024 * 1024 + 17)
    (tmp_path / "file.bin").write_bytes(data)

    async def body(port):
        return await probe_ftp("127.0.0.1", port, "/file.bin")

    size, rest_ok, conc_ok = asyncio.run(_with_server(str(tmp_path), body))
    assert size == len(data)
    assert rest_ok is True
    assert conc_ok is True


def test_ftp_segmented_byte_identical(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    data = os.urandom(6 * 1024 * 1024 + 777)
    (src / "file.bin").write_bytes(data)
    outdir = tmp_path / "out"
    outdir.mkdir()

    async def body(port):
        url = f"ftp://127.0.0.1:{port}/file.bin"
        d = FtpSegmentedDownloader(
            url, str(outdir / "file.bin"),
            segment_size=1024 * 1024, max_segments=8,
            min_file_size_for_segmentation=1024 * 1024,
            host_guard=HostGuard(8),
        )
        return await d.download()

    ok = asyncio.run(_with_server(str(src), body))
    assert ok is True
    assert md5((outdir / "file.bin").read_bytes()) == md5(data)
    assert not (outdir / "file.bin.part").exists()
    assert not (outdir / "file.bin.part.meta").exists()


def test_ftp_single_segment_accounting(tmp_path):
    # max_segments=1 -> single REST/RETR; still byte-identical (no concurrency).
    src = tmp_path / "src"
    src.mkdir()
    data = os.urandom(2 * 1024 * 1024 + 3)
    (src / "f.bin").write_bytes(data)
    outdir = tmp_path / "out"
    outdir.mkdir()

    async def body(port):
        d = FtpSegmentedDownloader(
            f"ftp://127.0.0.1:{port}/f.bin", str(outdir / "f.bin"),
            segment_size=64 * 1024 * 1024, max_segments=1,
            min_file_size_for_segmentation=1024 * 1024,
        )
        return await d.download()

    ok = asyncio.run(_with_server(str(src), body))
    assert ok is True
    assert md5((outdir / "f.bin").read_bytes()) == md5(data)
