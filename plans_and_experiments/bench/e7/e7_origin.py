#!/usr/bin/env python3
"""A self-contained local HTTP origin for E7c/E7d — the deterministic half of E7.

The reliability behaviours E7 must test cannot be summoned on demand from a public
archive: EBI will not, on request, become range-incapable, truncate a response, or
return 429 to half of your segment GETs. Testing those against live infrastructure
would be non-reproducible *and* impolite. So E7c/E7d drive the REAL engine
(`SegmentedDownloader`, `HostGuard`) against a server we fully control, which makes
them identical on Fabric and Expanse.

Modes (``--mode``):
  range     honest server: 200 + Accept-Ranges, serves 206 for Range GETs.
  norange   200 only, NO Accept-Ranges, ignores Range -> forces the single-stream
            never-truncate path (E7c).
  truncate  serves range/full but drops the connection after --truncate-frac of the
            body -> a short read the engine must NOT finalise (E7c).
  throttle  returns --status (429/503) to drive the circuit breaker (E7d). Two
            deterministic-vs-stochastic knobs: --trip-first N trips the first N
            *segment* (Range) GETs then serves cleanly (reproducible, always
            completes); --prob p trips a p fraction of them (stress). trip-first
            wins if both are set.
  corrupt   flips one byte of the served body -> md5 mismatch (used by the
            end-to-end corruption check, though E7c prefers the live-ENA variant).

The file it serves is generated deterministically (seeded) so the client can know
the expected md5 without a manifest. Prints one JSON line to stdout on startup:
  {"url": "...", "size": N, "md5": "...", "mode": "..."}
so the caller (engine_probe.py) can read the ground truth and then hit the URL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PATH = "/payload.bin"


def make_body(size: int, seed: int) -> bytes:
    rng = random.Random(seed)
    # randbytes is deterministic under the seed and ~1000x faster than a
    # getrandbits loop. But CPython's randbytes(n) calls getrandbits(n*8), and on
    # Python 3.10 n*8 >= 2**31 (i.e. size >= 256 MiB) raises OverflowError. Generate
    # in <256 MiB chunks so the 256 MB circuit-breaker payload works too, while
    # staying byte-for-byte deterministic under the seed.
    chunk = 32 * 1024 * 1024
    parts = []
    remaining = size
    while remaining > 0:
        n = min(chunk, remaining)
        parts.append(rng.randbytes(n))
        remaining -= n
    return b"".join(parts)


class Origin(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, *, body, mode, status, prob, trip_first,
                 trunc_frac):
        super().__init__(addr, handler)
        self.body = body
        self.mode = mode
        self.status = status
        self.prob = prob
        self.trip_first = trip_first
        self.trunc_frac = trunc_frac
        self.rng = random.Random(0xE7)
        self.lock = threading.Lock()
        self.n_range_gets = 0
        self.n_pushbacks = 0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # keep the benchmark logs clean
        pass

    # HEAD is used by some range probes; answer it like a GET header.
    def do_HEAD(self):
        self._respond(head_only=True)

    def do_GET(self):
        self._respond(head_only=False)

    def _respond(self, head_only: bool):
        srv: Origin = self.server  # type: ignore[assignment]
        if self.path != PATH:
            self.send_error(404)
            return
        body = srv.body
        total = len(body)
        rng_hdr = self.headers.get("Range")
        is_range = rng_hdr is not None and srv.mode != "norange"

        start, end = 0, total - 1
        if is_range:
            try:
                spec = rng_hdr.split("=", 1)[1]
                s, e = spec.split("-", 1)
                start = int(s) if s else 0
                end = int(e) if e else total - 1
            except Exception:
                start, end = 0, total - 1
            end = min(end, total - 1)

        # The engine's range-support probe is a `bytes=0-0` GET; it must SUCCEED so
        # the engine chooses the segmented path. Throttling it would just swallow
        # the 429 into a single-stream fallback (the ungated-probe behaviour noted
        # in EXPERIMENT_PLAN_E3.md §7b) and the breaker would never see a segment
        # 429. So only real segment GETs (not the 0-0 probe) are eligible to trip.
        is_probe = is_range and start == 0 and end == 0
        if srv.mode == "throttle" and is_range and not is_probe:
            with srv.lock:
                srv.n_range_gets += 1
                if srv.trip_first > 0:
                    trip = srv.n_range_gets <= srv.trip_first
                else:
                    trip = srv.rng.random() < srv.prob
                if trip:
                    srv.n_pushbacks += 1
            if trip:
                self.send_response(srv.status)
                self.send_header("Content-Length", "0")
                self.send_header("Retry-After", "1")
                self.end_headers()
                return

        chunk = body[start:end + 1]

        # E7c: short read — drop the connection partway through the body.
        cut = len(chunk)
        if srv.mode == "truncate":
            cut = int(len(chunk) * srv.trunc_frac)

        if is_range:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Accept-Ranges", "bytes")
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(chunk)))
            if srv.mode == "range":
                self.send_header("Accept-Ranges", "bytes")
            # norange: deliberately omit Accept-Ranges
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        if head_only:
            return
        try:
            self.wfile.write(chunk[:cut])
            if srv.mode == "truncate":
                # Slam the socket shut mid-body: the client sees a short read.
                self.close_connection = True
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="range",
                    choices=["range", "norange", "truncate", "throttle", "corrupt"])
    ap.add_argument("--size", type=int, default=64 * 1024 * 1024)
    ap.add_argument("--seed", type=int, default=20260720)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="0 = pick a free port")
    ap.add_argument("--status", type=int, default=429, help="throttle status")
    ap.add_argument("--prob", type=float, default=0.5, help="throttle probability")
    ap.add_argument("--trip-first", type=int, default=0,
                    help="trip the first N range GETs then serve cleanly (deterministic)")
    ap.add_argument("--truncate-frac", type=float, default=0.6)
    args = ap.parse_args()

    body = make_body(args.size, args.seed)
    if args.mode == "corrupt":
        b = bytearray(body)
        b[len(b) // 2] ^= 0xFF
        served = bytes(b)          # what the client receives
        truth = body              # what its md5 "should" be
    else:
        served = truth = body
    md5 = hashlib.md5(truth).hexdigest()

    srv = Origin((args.host, args.port), Handler, body=served, mode=args.mode,
                 status=args.status, prob=args.prob, trip_first=args.trip_first,
                 trunc_frac=args.truncate_frac)
    host, port = srv.server_address
    url = f"http://{host}:{port}{PATH}"
    print(json.dumps({"url": url, "size": args.size, "md5": md5,
                      "mode": args.mode}), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
