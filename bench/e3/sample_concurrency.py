#!/usr/bin/env python3
"""Sample instantaneous concurrency of a running arm, from the outside.

WHY EXTERNAL, NOT INTERNAL
--------------------------
adaptiSeq knows its own `gate.active`, but (a) it only surfaces it through the
progress bar, which is silent under -Q and on a non-TTY (i.e. always, in Slurm),
and (b) no competitor exposes anything comparable. An internal-only number would
also measure *intent* -- what the controller asked for -- rather than what the
process actually did to the archive.

So we sample from outside: every tick, count ESTABLISHED TCP connections held by
the arm's process tree. That is the same measurement for iseq (wget subprocesses),
iseq -p 8 (axel's 8 connections), kingfisher (aria2c), and adaptiSeq (one asyncio
process holding N sockets) -- so the arms are finally comparable on *what they do
to the server*, not just on how fast they finish.

This gives, for free:
  * E4 Fig 4  -- the adaptive worker trajectory vs a fixed arm, on a real clock;
  * E9        -- where the per-host cap / circuit breaker becomes the limit;
  * C5/E10    -- good-citizen evidence: concurrency actually offered per host.

SAMPLING RATE (default 5 Hz, not 2)
-----------------------------------
Instantaneous sampling can only see connections that are alive at a tick. On the
headline panel (D1, ~22 MB/file) an iseq `wget` lives ~1 s, so 2 Hz would catch
it once or not at all -- undersampling the very arm the figure is about. 5 Hz
costs ~1% of one core (a tree walk + one /proc/<pid>/fd scan per process) and is
applied identically to every arm, so it cannot bias the comparison. Raise it with
E3_CONC_HZ for short-lived-connection regimes.

Sub-tick connections remain invisible in principle: conc_* is a SAMPLED
statistic, not an exact count. Report it as such.

COVERAGE: only processes in the arm's tree are visible. Verified for iseq
(wget children), iseq -p 8 (axel), kingfisher (aria2c), fastq-dl and adaptiSeq.
NOT verified for fetchngs, whose Nextflow+Singularity workers may run outside the
tree's PID namespace -- treat its conc_* columns as unreliable until checked
(it is off by default, ENABLE_FETCHNGS=1).

Self-terminates when the watched tree exits, then prints a summary line of
key=value pairs for the harness to splice into its TSV row.

Usage:
    python bench/e3/sample_concurrency.py --pid <pid> --out conc.tsv [--hz 2]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from typing import List

# Every exit path must emit EVERY key: the harness eval()s this line under
# `set -u`, so a partial summary would abort the arm rather than degrade.
# Defined before the psutil import guard, which is one of those exit paths.
NULL_SUMMARY = ("conc_med=0 conc_p95=0 conc_max=0 conc_per_host_max=0 "
                "procs_max=0 conc_samples=0")

try:
    import psutil
except ImportError:
    sys.stderr.write("sample_concurrency: psutil missing; concurrency not sampled\n")
    print(NULL_SUMMARY)
    sys.exit(0)

# Remote ports that mean "talking to an archive": HTTPS/HTTP, FTP control+data,
# and Aspera's TCP side. Loopback/local chatter is excluded by construction since
# we only count connections with a remote endpoint off-host.
ARCHIVE_PORTS = {80, 443, 21, 20, 33001, 989, 990}


def pct(vals: List[int], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return float(s[i])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hz", type=float, default=5.0)
    ap.add_argument("--max-seconds", type=float, default=90000.0)
    args = ap.parse_args()

    period = 1.0 / max(0.1, args.hz)
    t0 = time.monotonic()
    conc_series: List[int] = []
    procs_series: List[int] = []
    host_peak: Counter = Counter()

    try:
        root = psutil.Process(args.pid)
    except psutil.Error:
        print(NULL_SUMMARY)
        return 0

    fh = open(args.out, "w", buffering=1)
    fh.write("t_rel_s\tn_procs\tconns_established\tconns_archive\trss_mb\ttop_hosts\n")

    while True:
        now = time.monotonic() - t0
        if now > args.max_seconds:
            break
        try:
            if not root.is_running() or root.status() == psutil.STATUS_ZOMBIE:
                break
            procs = [root] + root.children(recursive=True)
        except psutil.Error:
            break

        est = 0
        arch = 0
        rss = 0
        hosts: Counter = Counter()
        for p in procs:
            try:
                # net_connections() replaced connections() in psutil 6.0.
                getter = getattr(p, "net_connections", None) or p.connections
                for c in getter(kind="tcp"):
                    if c.status != psutil.CONN_ESTABLISHED or not c.raddr:
                        continue
                    est += 1
                    if c.raddr.port in ARCHIVE_PORTS:
                        arch += 1
                        hosts[c.raddr.ip] += 1
                rss += p.memory_info().rss
            except (psutil.Error, OSError):
                continue

        for h, n in hosts.items():
            host_peak[h] = max(host_peak[h], n)

        conc_series.append(arch)
        procs_series.append(len(procs))
        top = ",".join(f"{h}:{n}" for h, n in hosts.most_common(3)) or "-"
        fh.write(f"{now:.2f}\t{len(procs)}\t{est}\t{arch}\t{rss/1e6:.1f}\t{top}\n")

        time.sleep(period)

    fh.close()

    # Idle head/tail samples (resolution, md5 verification, teardown) would drag
    # the median toward zero and understate what the tool actually offered the
    # server, so the summary describes the ACTIVE transfer phase only.
    active = [c for c in conc_series if c > 0]
    peak_host = host_peak.most_common(1)[0][1] if host_peak else 0
    print(
        f"conc_med={pct(active, 0.5):.0f} "
        f"conc_p95={pct(active, 0.95):.0f} "
        f"conc_max={max(conc_series) if conc_series else 0} "
        f"conc_per_host_max={peak_host} "
        f"procs_max={max(procs_series) if procs_series else 0} "
        f"conc_samples={len(conc_series)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
