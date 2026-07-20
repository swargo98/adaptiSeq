#!/usr/bin/env python3
"""E7c/E7d: drive the REAL engine against the local origin and score the result.

This is the deterministic half of E7. It does NOT touch a public archive: it spawns
`e7_origin.py` (a server we fully control), reads its ground-truth JSON, then points
`adaptiseq.engine.segmented.SegmentedDownloader` + `HostGuard` at it. Because both
the client (the shipped engine) and the server are local, the never-truncate and
circuit-breaker verdicts are identical on Fabric and Expanse.

Checks (``--check``):
  never_truncate   origin=norange  -> single-stream path must produce the FULL file
                   with the expected md5 (no silent truncation on a range-incapable
                   host). C4.
  short_read       origin=truncate -> a dropped-mid-body response must NEVER be
                   finalised as the real file; a wrong-md5 final file is a failure.
                   C4.
  circuit_breaker  origin=throttle -> 429s must trip HostGuard (cap halves per trip,
                   exponential backoff), and the transfer must STILL complete with a
                   valid md5. Records the cap trajectory for the E7d figure. C5.

Emits one TSV row on stdout:
  subexp  check  mode  passed  detail
and, for circuit_breaker, a cap-vs-time trace to --trace.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from adaptiseq.engine.ratelimit import HostGuard, host_of  # noqa: E402
from adaptiseq.engine.segmented import SegmentedDownloader  # noqa: E402
import aiohttp  # noqa: E402


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def start_origin(py: str, origin: str, mode: str, size: int, **extra) -> tuple:
    """Spawn e7_origin.py; return (proc, info_dict)."""
    cmd = [py, origin, "--mode", mode, "--size", str(size)]
    for k, v in extra.items():
        cmd += [f"--{k.replace('_', '-')}", str(v)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    line = proc.stdout.readline()          # blocks until the server prints its JSON
    if not line:
        raise RuntimeError("origin failed to start")
    return proc, json.loads(line)


async def _download(url: str, dest: Path, *, guard: HostGuard,
                    max_segments: int, segment_size: int):
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        dl = SegmentedDownloader(
            session, url, str(dest),
            segment_size=segment_size,
            min_file_size_for_segmentation=1024,   # segment even the small test file
            max_segments=max_segments,
            host_guard=guard,
        )
        try:
            ok, _resumed, _n = await dl.download_segmented()
        except Exception as exc:                   # a clean failure is a valid result
            return False, f"exc={type(exc).__name__}:{exc}"
        return ok, ""


def check_never_truncate(args, info) -> tuple:
    dest = Path(args.workdir) / "nt.bin"
    guard = HostGuard(args.cap)
    ok, err = asyncio.run(_download(info["url"], dest, guard=guard,
                                    max_segments=8, segment_size=8 << 20))
    if not dest.exists():
        return False, f"no file produced ({err})"
    size = dest.stat().st_size
    digest = md5_of(dest)
    passed = ok and size == info["size"] and digest == info["md5"]
    return passed, f"size={size}/{info['size']} md5={'match' if digest == info['md5'] else 'MISMATCH'}"


def check_short_read(args, info) -> tuple:
    dest = Path(args.workdir) / "sr.bin"
    guard = HostGuard(args.cap)
    ok, err = asyncio.run(_download(info["url"], dest, guard=guard,
                                    max_segments=8, segment_size=8 << 20))
    # The guarantee is: a truncated transfer is NEVER finalised as the real file.
    if dest.exists():
        size = dest.stat().st_size
        digest = md5_of(dest)
        if size == info["size"] and digest == info["md5"]:
            # Extremely unlikely for a truncating server, but if it somehow
            # delivered the whole thing, that is fine (complete + correct).
            return True, f"complete size={size} md5=match (server served full)"
        return False, f"FINALISED TRUNCATED FILE size={size}/{info['size']} md5=MISMATCH"
    # No final file: the engine refused to promote a short .part -> the guarantee holds.
    return True, f"not finalised (ok={ok} {err}); .part left, no corrupt final"


def check_circuit_breaker(args, info) -> tuple:
    dest = Path(args.workdir) / "cb.bin"
    host = host_of(info["url"])
    guard = HostGuard(args.cap)

    # Sample the effective per-host cap on a wall clock while the loop runs, so the
    # figure can show cap halving on each trip and recovering afterwards.
    trace = []
    stop = threading.Event()
    t0 = time.monotonic()

    def sampler():
        while not stop.is_set():
            trace.append((time.monotonic() - t0, guard.cap_of(host),
                          guard.in_flight_of(host)))
            time.sleep(0.1)

    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    ok, err = asyncio.run(_download(info["url"], dest, guard=guard,
                                    max_segments=8, segment_size=8 << 20))
    stop.set(); th.join(timeout=1)

    trips = list(guard.trips)
    n_trips = len(trips)
    backoffs = [round(d, 2) for (_h, _k, d) in trips]
    completed = dest.exists() and md5_of(dest) == info["md5"] if dest.exists() else False
    # C5 verdict: the breaker MUST have fired, and the transfer MUST still complete.
    passed = n_trips > 0 and completed and ok

    if args.trace:
        with open(args.trace, "w") as fh:
            fh.write("t_rel_s\tcap\tin_flight\n")
            for (t, cap, inf) in trace:
                fh.write(f"{t:.2f}\t{cap}\t{inf}\n")

    caps = sorted({cap for (_t, cap, _i) in trace})
    detail = (f"trips={n_trips} cap_range={min(caps) if caps else '?'}"
              f"..{max(caps) if caps else '?'} backoff={backoffs} "
              f"completed={'yes' if completed else 'NO'} ({err})")
    return passed, detail


CHECKS = {
    "never_truncate": ("norange", check_never_truncate, {}),
    "short_read": ("truncate", check_short_read, {"truncate_frac": 0.6}),
    "circuit_breaker": ("throttle", check_circuit_breaker,
                        {"status": 429, "trip_first": 4}),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", required=True, choices=list(CHECKS))
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--origin", default=str(Path(__file__).with_name("e7_origin.py")))
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--size", type=int, default=64 * 1024 * 1024)
    ap.add_argument("--cap", type=int, default=8)
    ap.add_argument("--trace", default="")
    args = ap.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    mode, fn, extra = CHECKS[args.check]
    size = 256 * 1024 * 1024 if args.check == "circuit_breaker" else args.size
    proc, info = start_origin(args.python, args.origin, mode, size, **extra)
    try:
        passed, detail = fn(args, info)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    print(f"E7c-d\t{args.check}\t{mode}\t{'PASS' if passed else 'FAIL'}\t{detail}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
