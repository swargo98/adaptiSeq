"""Part 2 segmented HTTP engine: unit + local-server integration tests.

Covers the deterministic parts the sandbox can run offline (spec §8): segment
calculation, ``.part.meta`` resume bookkeeping, the token-bucket limiter, the
per-host cap, the circuit breaker, and end-to-end byte-identical segmented
download + mid-file resume against a local Range server.
"""

import asyncio
import hashlib
import os
import time

import aiohttp
import pytest

from adaptiseq.engine import segmented as S
from adaptiseq.engine.ratelimit import HostGuard, TokenBucket, host_of
from adaptiseq.engine.seam import SegmentedEngine, _to_https
from adaptiseq.options import Options
from tests.servers import RangeServer


def run(coro):
    return asyncio.run(coro)


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


# ============================== segment calculation ============================

def test_calculate_segments_small_file_single():
    segs = S.calculate_segments(
        1000, min_file_size=5_000_000, max_segments=8, segment_size=1_000_000
    )
    assert segs == [(0, 999)]


def test_calculate_segments_capped_and_remainder():
    size = 10_000_003
    segs = S.calculate_segments(
        size, min_file_size=1_000_000, max_segments=8, segment_size=1_000_000
    )
    assert len(segs) == 8  # min(8, 10) -> 8
    assert segs[0][0] == 0
    assert segs[-1][1] == size - 1  # last segment takes the remainder
    # contiguous, non-overlapping
    for (s1, e1), (s2, e2) in zip(segs, segs[1:]):
        assert e1 + 1 == s2


def test_calculate_segments_few_for_modest_size():
    # size // segment_size = 3 -> 3 segments even though ceiling is 8
    segs = S.calculate_segments(
        3_500_000, min_file_size=1_000_000, max_segments=8, segment_size=1_000_000
    )
    assert len(segs) == 3


# ============================== resume bookkeeping ============================

def test_part_meta_roundtrip_and_partials(tmp_path):
    meta = str(tmp_path / "f.part.meta")
    segments = [(0, 99), (100, 199), (200, 299)]
    completed = {0}
    S.write_part_meta(meta, 300, segments, completed, {1: 150})
    loaded = S.read_part_meta(meta)
    assert loaded["file_size"] == 300
    assert loaded["completed_indices"] == [0]
    assert loaded["partial_offsets"] == {"1": 150}

    completed2 = set(loaded["completed_indices"])
    offsets = S.load_partial_offsets(loaded, segments, completed2)
    assert offsets == {1: 150}


def test_load_partial_offsets_promotes_finished_segment():
    segments = [(0, 99), (100, 199)]
    completed = set()
    meta = {"partial_offsets": {"1": 200}}  # offset past end -> segment complete
    offsets = S.load_partial_offsets(meta, segments, completed)
    assert 1 in completed
    assert offsets == {}


# ============================== token bucket ================================

def test_token_bucket_limits_rate():
    rate = 4 * 1024 * 1024  # 4 MB/s
    bucket = TokenBucket(rate)

    async def pull():
        t0 = time.monotonic()
        # consume 8 MB worth in 1 MB chunks; should take ~ (8-1)/4 s after burst
        for _ in range(8):
            await bucket.acquire(1024 * 1024)
        return time.monotonic() - t0

    elapsed = run(pull())
    # With 4 MB/s and ~4 MB burst capacity, 8 MB takes at least ~1s.
    assert elapsed >= 0.8


def test_token_bucket_unlimited_when_rate_zero():
    bucket = TokenBucket(0)
    run(bucket.acquire(10 ** 9))  # returns immediately, no error


# ============================== per-host cap =================================

def test_host_guard_caps_in_flight():
    guard = HostGuard(default_cap=3)
    host = "h"
    peak = 0

    async def worker():
        nonlocal peak
        async with guard.connection(host):
            peak = max(peak, guard.in_flight_of(host))
            await asyncio.sleep(0.02)

    async def main():
        await asyncio.gather(*[worker() for _ in range(12)])

    run(main())
    assert peak <= 3
    assert guard.in_flight_of(host) == 0


def test_host_of():
    assert host_of("https://ftp.sra.ebi.ac.uk/vol1/x") == "ftp.sra.ebi.ac.uk"
    assert host_of("ftp://user@download.big.ac.cn/p") == "download.big.ac.cn"


# ============================== circuit breaker ==============================

def test_circuit_breaker_trips_and_recovers():
    guard = HostGuard(default_cap=8, base_backoff=0.05)
    host = "h"

    async def main():
        await guard.note_pushback(host, "429")
        assert guard.is_tripped(host)
        assert guard.cap_of(host) == 4  # halved
        assert len(guard.trips) == 1
        # acquire must wait out the backoff window before granting
        t0 = time.monotonic()
        await guard.acquire(host)
        waited = time.monotonic() - t0
        await guard.release(host)
        assert waited >= 0.04
        # recovery nudges the cap back up and clears the block
        await guard.note_success(host)
        assert not guard.is_tripped(host)
        assert guard.cap_of(host) == 5

    run(main())


# ============================== end-to-end (local server) ====================

def _engine(outdir, **opts):
    base = dict(engine="segmented", segment_size=1 * 1024 * 1024, max_segments=8,
                max_conns_per_host=8, quiet=True)
    base.update(opts)
    return SegmentedEngine(Options(**base), outdir)


def test_segmented_http_byte_identical(tmp_path):
    data = os.urandom(8 * 1024 * 1024 + 4321)
    with RangeServer(data) as srv:
        eng = _engine(str(tmp_path))
        ok = eng.fetch(srv.url(), "file.bin")
    out = (tmp_path / "file.bin").read_bytes()
    assert ok is True
    assert md5(out) == md5(data)
    assert not (tmp_path / "file.bin.part").exists()
    assert not (tmp_path / "file.bin.part.meta").exists()


def test_segmented_strict_206_falls_back_to_single_on_200(tmp_path):
    # A server that ignores Range (always 200) must still yield the correct file
    # via the single-connection path — never a corrupt/zero-byte file.
    data = os.urandom(3 * 1024 * 1024 + 11)
    with RangeServer(data, force_200=True) as srv:
        eng = _engine(str(tmp_path))
        ok = eng.fetch(srv.url(), "file.bin")
    assert ok is True
    assert md5((tmp_path / "file.bin").read_bytes()) == md5(data)


def test_segmented_resume_mid_file(tmp_path):
    data = os.urandom(8 * 1024 * 1024 + 123)
    url = None
    dest = str(tmp_path / "file.bin")

    class StopAfter:
        def __init__(self, n):
            self.n = n
            self.calls = 0

        def should_continue(self):
            self.calls += 1
            return self.calls <= self.n

    with RangeServer(data) as srv:
        url = srv.url()

        async def first():
            async with aiohttp.ClientSession() as sess:
                d = S.SegmentedDownloader(
                    sess, url, dest, segment_size=4 * 1024 * 1024, max_segments=2,
                    min_file_size_for_segmentation=1024 * 1024, pause=StopAfter(2),
                )
                return await d.download()

        ok1 = run(first())
        # Interrupted: not complete, partial state persisted, final file absent.
        assert ok1 is False
        assert (tmp_path / "file.bin.part").exists()
        assert (tmp_path / "file.bin.part.meta").exists()
        assert not (tmp_path / "file.bin").exists()

        async def resume():
            async with aiohttp.ClientSession() as sess:
                d = S.SegmentedDownloader(
                    sess, url, dest, segment_size=4 * 1024 * 1024, max_segments=2,
                    min_file_size_for_segmentation=1024 * 1024,
                )
                return await d.download()

        ok2 = run(resume())
    assert ok2 is True
    assert md5((tmp_path / "file.bin").read_bytes()) == md5(data)
    assert not (tmp_path / "file.bin.part.meta").exists()


def test_per_host_cap_enforced_end_to_end(tmp_path):
    data = os.urandom(8 * 1024 * 1024 + 5)
    with RangeServer(data, delay=0.05) as srv:
        eng = _engine(str(tmp_path), max_conns_per_host=2)
        ok = eng.fetch(srv.url(), "file.bin")
        assert ok is True
        assert md5((tmp_path / "file.bin").read_bytes()) == md5(data)
        assert srv.max_concurrent <= 2


def test_circuit_breaker_completes_despite_429s(tmp_path):
    # First two requests get 429; the engine must back off, retry, and still
    # produce a correct file (acceptance #8: trips and recovers, no corruption).
    data = os.urandom(2 * 1024 * 1024 + 9)
    with RangeServer(data, fail_n=2) as srv:
        eng = _engine(str(tmp_path), max_segments=2, segment_size=1024 * 1024)
        ok = eng.fetch(srv.url(), "file.bin")
    assert ok is True
    assert md5((tmp_path / "file.bin").read_bytes()) == md5(data)


# ============================== transport selection ==========================

def test_to_https_upgrade():
    assert _to_https("ftp://ftp.sra.ebi.ac.uk/vol1/x.gz") == \
        "https://ftp.sra.ebi.ac.uk/vol1/x.gz"


def test_transport_explicit_overrides(tmp_path):
    eng = _engine(str(tmp_path), protocol="https")

    async def main():
        async with aiohttp.ClientSession() as s:
            kind, url = await eng._select_transport("ftp://h/x.gz", s)
            return kind, url

    kind, url = run(main())
    assert kind == "http-seg"
    assert url == "https://h/x.gz"


def test_transport_cache_derives_url_per_file(tmp_path):
    # Regression: the per-host transport cache must store only the *kind*, and
    # derive the effective URL per file. Two files on the same host must map to
    # two different https URLs, not the first file's cached URL.
    eng = _engine(str(tmp_path))
    eng._verdict["h"] = "http-seg"  # pretend the host was already probed
    assert eng._eff_url("ftp://h/SRR_1.fastq.gz", "http-seg") == "https://h/SRR_1.fastq.gz"
    assert eng._eff_url("ftp://h/SRR_2.fastq.gz", "http-seg") == "https://h/SRR_2.fastq.gz"

    async def main():
        async with aiohttp.ClientSession() as s:
            k1, u1 = await eng._select_transport("ftp://h/a_1.fastq.gz", s)
            k2, u2 = await eng._select_transport("ftp://h/a_2.fastq.gz", s)
            return (k1, u1), (k2, u2)

    (k1, u1), (k2, u2) = run(main())
    assert k1 == k2 == "http-seg"
    assert u1.endswith("a_1.fastq.gz") and u2.endswith("a_2.fastq.gz")
    assert u1 != u2


def test_transport_ftp_override(tmp_path):
    eng = _engine(str(tmp_path), protocol="ftp")

    async def main():
        async with aiohttp.ClientSession() as s:
            return await eng._select_transport("ftp://h/x.gz", s)

    kind, url = run(main())
    assert kind == "ftp-seg"
    assert url == "ftp://h/x.gz"


def test_self_contained_no_forbidden_imports():
    # Acceptance #9: the engine modules must be importable with only aiohttp,
    # aioftp, the stdlib, and our own code — no fastbiodl globals, multiprocessing,
    # numpy, or tmpfs machinery. Inspect the actual import statements via AST so
    # docstring prose (which legitimately cites fastbiodl_upgrade.py) doesn't trip.
    import ast

    import adaptiseq.engine.segmented as seg
    import adaptiseq.engine.ftp as ftpmod
    import adaptiseq.engine.ratelimit as rl

    forbidden = {
        "multiprocessing", "numpy", "fastbiodl_upgrade", "config_fastbiodl",
        "storage_config", "converter", "ncbi_lookup", "search",
    }
    for mod in (seg, ftpmod, rl):
        tree = ast.parse(open(mod.__file__).read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        bad = imported & forbidden
        assert not bad, f"{mod.__name__} imports forbidden module(s): {bad}"
