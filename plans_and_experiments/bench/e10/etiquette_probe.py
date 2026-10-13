#!/usr/bin/env python3
"""E10c — etiquette / decoupling proof (local, deterministic).

The claim: adaptiSeq's request rate to each endpoint stays **flat at the
documented cap** as `--meta-jobs` rises, because concurrency (pool size) and
request rate (per-endpoint `RateLimiter`) are decoupled. The failure mode it
prevents: a naive thread-per-accession resolver blows linearly past NCBI's
3 rps, risking a server throttle / IP ban.

Proving that against LIVE NCBI would mean actually flooding NCBI (impolite, and
the magnitude is unreproducible). So — exactly as E7 drives the real
`SegmentedDownloader` against a local origin — this drives the **real**
`adaptiseq.ratelimits.EndpointLimiters` / `RateLimiter.acquire` (production code,
unmodified) with the real per-accession endpoint-request pattern (measured in
EXPERIMENT_PLAN_E10.md §2), through a `ThreadPoolExecutor(meta_jobs)` that mirrors
`batch.resolve_all`. Only the "network" is a fixed simulated latency, so the
result is identical on Fabric and Expanse.

Two arms:
  limiter   ratelimits.set_active(EndpointLimiters())  -> the production path
  naive     ratelimits.set_active(None)                -> throttle() is a no-op
and two NCBI-key modes (no key -> cap 3 rps, NCBI_API_KEY -> cap 10 rps).

Emits TSV rows on stdout (schema in EXPERIMENT_PLAN_E10.md §4): one row per
(arm, ncbi_key, meta_jobs, endpoint).
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from adaptiseq import ratelimits  # noqa: E402

# Real endpoint URLs so ratelimits.endpoint_for_url() classifies them exactly as
# in production (host-substring match). No request is actually sent.
_URL = {
    "ena": "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=X",
    "ncbi_esearch": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=sra",
    "ncbi_runinfo": "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/sra-db-be.cgi",
    "gsa": "https://ngdc.cncb.ac.cn/gsa/search/getRunInfoByCra",
}

# Per-accession request patterns (URL sequence), from §2 of the plan.
PATTERNS = {
    "ena":      [_URL["ena"]],                                   # ENA-mirrored run
    "sra_only": [_URL["ena"], _URL["ncbi_esearch"], _URL["ncbi_runinfo"]],  # ENA empty -> NCBI
    "gsa":      [_URL["gsa"]] * 4,                               # GSA browse+runinfo+xlsx
}


def build_batch(n: int):
    """A fixed synthetic batch: 40% true-SRA-only (NCBI-stressing), 40% ENA,
    20% GSA. Deterministic, so the run is reproducible."""
    batch = []
    for i in range(n):
        r = i % 5
        if r < 2:
            batch.append("sra_only")
        elif r < 4:
            batch.append("ena")
        else:
            batch.append("gsa")
    return batch


def run_arm(arm, meta_jobs, batch, latency, ncbi_key):
    """Resolve the batch through a meta_jobs pool; record every request's
    (endpoint, monotonic timestamp) at the moment it is issued (post-throttle)."""
    # ncbi_rps() reads NCBI_API_KEY at limiter construction time.
    if ncbi_key:
        os.environ["NCBI_API_KEY"] = "e10-etiquette-probe-key"
    else:
        os.environ.pop("NCBI_API_KEY", None)

    limiters = ratelimits.EndpointLimiters() if arm == "limiter" else None
    ratelimits.set_active(limiters)

    events = []            # (endpoint, t_issue)
    lock = threading.Lock()

    def resolve_one(kind):
        for url in PATTERNS[kind]:
            ratelimits.throttle(url)          # REAL limiter (no-op when naive)
            ep = ratelimits.endpoint_for_url(url)
            with lock:
                events.append((ep, time.monotonic()))
            if latency > 0:
                time.sleep(latency)           # simulated RTT

    try:
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=max(1, meta_jobs)) as pool:
            list(pool.map(resolve_one, batch))
        wall = time.monotonic() - t0
    finally:
        ratelimits.set_active(None)
    return events, wall


def per_endpoint_stats(events, endpoint):
    ts = sorted(t for ep, t in events if ep == endpoint)
    n = len(ts)
    if n == 0:
        return 0, 0.0, 0.0, 0
    span = ts[-1] - ts[0]
    mean_rps = (n / span) if span > 0 else float(n)
    # peak instantaneous rate: max requests in any 1.0s window starting at a request.
    peak = 0
    j = 0
    for i in range(n):
        while j < n and ts[j] < ts[i] + 1.0:
            j += 1
        peak = max(peak, j - i)
    return n, span, mean_rps, peak


def emit(row):
    print("\t".join(str(x) for x in row), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120, help="synthetic accessions")
    ap.add_argument("--meta-jobs", default="1,3,8,16")
    ap.add_argument("--latency", type=float, default=0.05,
                    help="simulated per-request RTT (s)")
    ap.add_argument("--arms", default="limiter,naive")
    ap.add_argument("--key-modes", default="nokey,key")
    args = ap.parse_args()

    batch = build_batch(args.n)
    mjs = [int(x) for x in args.meta_jobs.split(",") if x]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    key_modes = [k.strip() for k in args.key_modes.split(",") if k.strip()]
    host = os.uname().nodename.split(".")[0]
    endpoints = ["ena", "gsa", "ncbi"]

    for key_mode in key_modes:
        ncbi_key = (key_mode == "key")
        caps = {"ena": 8.0, "gsa": 5.0, "ncbi": (10.0 if ncbi_key else 3.0)}
        for arm in arms:
            for mj in mjs:
                events, wall = run_arm(arm, mj, batch, args.latency, ncbi_key)
                for ep in endpoints:
                    n, span, mean_rps, peak = per_endpoint_stats(events, ep)
                    cap = caps[ep]
                    over = int(peak > cap * 1.15)
                    print(f"[{arm:7s} {key_mode:5s} mj={mj:2d}] {ep:4s} "
                          f"n={n:4d} mean={mean_rps:6.2f} peak1s={peak:3d} "
                          f"cap={cap:.0f} over={'YES' if over else 'no'}",
                          file=sys.stderr)
                    emit([arm, key_mode, mj, ep, f"{cap:.1f}", n, f"{wall:.3f}",
                          f"{mean_rps:.3f}", peak, over, host,
                          time.strftime("%FT%T")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
