"""Local HTTP test servers for the segmented engine (no network needed).

Deterministic, in-process servers that exercise the live HTTP code paths:
range support, strict 206, the per-host connection cap (via tracked concurrency),
and the circuit breaker (via injected 429s).
"""

from __future__ import annotations

import http.server
import socketserver
import threading
import time
from typing import Optional


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    # injected by the server subclass instance via server attributes
    def do_GET(self):
        srv = self.server
        with srv.lock:
            srv.concurrent += 1
            srv.max_concurrent = max(srv.max_concurrent, srv.concurrent)
            srv.requests += 1
            n = srv.requests
        try:
            if srv.delay:
                time.sleep(srv.delay)

            # Circuit-breaker injection: first `fail_n` requests get 429.
            if srv.fail_n and n <= srv.fail_n:
                self.send_response(429)
                self.send_header("Retry-After", "0")
                self.end_headers()
                return

            data = srv.data
            rng = self.headers.get("Range")
            if rng and not srv.force_200:
                spec = rng.split("=", 1)[1]
                a, b = spec.split("-")
                a = int(a)
                b = int(b) if b else len(data) - 1
                b = min(b, len(data) - 1)
                body = data[a:b + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {a}-{b}/{len(data)}")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        finally:
            with srv.lock:
                srv.concurrent -= 1


class _MultiHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        srv = self.server
        with srv.lock:
            srv.concurrent += 1
            srv.max_concurrent = max(srv.max_concurrent, srv.concurrent)
        try:
            if srv.delay:
                time.sleep(srv.delay)
            name = self.path.lstrip("/")
            data = srv.files.get(name)
            if data is None:
                self.send_response(404)
                self.end_headers()
                return
            rng = self.headers.get("Range")
            if rng:
                a, b = rng.split("=", 1)[1].split("-")
                a = int(a)
                b = int(b) if b else len(data) - 1
                b = min(b, len(data) - 1)
                body = srv.maybe_corrupt(name, data[a:b + 1])
                with srv.lock:
                    srv.range_starts.append((name, a))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {a}-{b}/{len(data)}")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                rate = srv.rate_for(name, a, len(body))
                if rate:
                    piece = 64 * 1024
                    for k in range(0, len(body), piece):
                        self.wfile.write(body[k:k + piece])
                        time.sleep(len(body[k:k + piece]) / rate)
                else:
                    self.wfile.write(body)
            else:
                body = srv.maybe_corrupt(name, data)
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        finally:
            with srv.lock:
                srv.concurrent -= 1


class MultiFileRangeServer(socketserver.ThreadingTCPServer):
    """Serves a dict of ``{name: bytes}`` with Range; unknown names -> 404."""

    daemon_threads = True
    allow_reuse_address = True
    # socketserver's default listen backlog is 5: on a loaded node the single
    # accept thread falls behind, the kernel drops further SYNs and the client
    # retries ~1 s later, so concurrent connections never overlap as intended.
    request_queue_size = 128

    def handle_error(self, request, client_address):
        return

    def __init__(self, files: dict, *, delay: float = 0.0):
        super().__init__(("127.0.0.1", 0), _MultiHandler)
        self.files = files
        self.delay = delay
        self.lock = threading.Lock()
        self.concurrent = 0
        self.max_concurrent = 0
        # {name: n}: the next n data responses for that file (not 1-byte range
        # probes) have one byte flipped -- a transfer that arrives intact in
        # length but fails the md5 check, as ENA's sometimes do.
        self.corrupt = {}
        # {name: (bytes_per_s, start or None)}: stream that file's range responses
        # at this rate -- all of them, or only the one starting at ``start`` (a
        # straggler connection). range_starts records every data request.
        self.throttle = {}
        self.range_starts = []

    def rate_for(self, name: str, start: int, length: int):
        if length <= 1 or name not in self.throttle:
            return None
        rate, only = self.throttle[name]
        return rate if only is None or only == start else None

    def maybe_corrupt(self, name: str, body: bytes) -> bytes:
        if len(body) <= 1:
            return body
        with self.lock:
            left = self.corrupt.get(name, 0)
            if left <= 0:
                return body
            self.corrupt[name] = left - 1
        return bytes([body[0] ^ 0xFF]) + body[1:]

    @property
    def port(self) -> int:
        return self.server_address[1]

    def url(self, name: str) -> str:
        return f"http://127.0.0.1:{self.port}/{name}"

    def __enter__(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.shutdown()
        self.server_close()


class RangeServer(socketserver.ThreadingTCPServer):
    """A threaded Range-capable static server over a fixed byte payload."""

    daemon_threads = True
    allow_reuse_address = True
    # socketserver's default listen backlog is 5: on a loaded node the single
    # accept thread falls behind, the kernel drops further SYNs and the client
    # retries ~1 s later, so concurrent connections never overlap as intended.
    request_queue_size = 128

    def handle_error(self, request, client_address):
        # Clients legitimately close early (probe reads 1 byte; segments close on
        # completion). Swallow the resulting reset noise.
        return

    def __init__(self, data: bytes, *, force_200: bool = False,
                 delay: float = 0.0, fail_n: int = 0):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.data = data
        self.force_200 = force_200
        self.delay = delay
        self.fail_n = fail_n
        self.lock = threading.Lock()
        self.concurrent = 0
        self.max_concurrent = 0
        self.requests = 0
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self.server_address[1]

    def url(self, name: str = "file.bin") -> str:
        return f"http://127.0.0.1:{self.port}/{name}"

    def __enter__(self):
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.shutdown()
        self.server_close()
