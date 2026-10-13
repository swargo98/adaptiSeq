#!/usr/bin/env python3
"""E8: run one download arm under a process-tree resource profiler (iSeq Fig 1D).

Launches <cmd> in its own process group, samples the WHOLE process tree at --hz
(default 2 Hz) with psutil -- RSS, CPU (from cpu_times deltas), disk read/write --
and watches the output dir to split the run into three phases (setup / fetch-data /
verify) from first-byte / last-growth / exit timestamps. The instrument is external
to every tool, so it cannot favour adaptiSeq's single-process model over iSeq's
subprocess-per-run model or prefetch's fasterq-dump converter (parent §10).

Writes:
  * a 2 Hz trace TSV (--trace): t_rel_s, rss_mb, cpu_pct, read_mbps, write_mbps, nprocs
  * one summary row on stdout (header written by the caller)

Judged by the ENA manifest md5 when --manifest is given (reused verify_output.py);
otherwise by bytes-on-disk (the SRA panel, whose sizes are not in the ENA portal).
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

SKIP_SUFFIX = (".log", ".json", ".tsv", ".csv", ".yml", ".yaml", ".part.meta",
               ".md5", ".flag", ".tmp")


def data_bytes(root: Path) -> tuple:
    """(total bytes, file count) of everything that looks like payload."""
    total = 0
    n = 0
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in (".nextflow", "work")]
        for f in fn:
            if f.startswith(".") or f.endswith(SKIP_SUFFIX):
                continue
            try:
                total += os.path.getsize(os.path.join(dp, f))
                n += 1
            except OSError:
                pass
    return total, n


def tree(root_pid: int):
    try:
        p = psutil.Process(root_pid)
    except psutil.NoSuchProcess:
        return []
    procs = [p]
    try:
        procs += p.children(recursive=True)
    except psutil.NoSuchProcess:
        pass
    return procs


def sample(procs, prev_cpu: dict) -> tuple:
    """Return (rss_bytes, cpu_seconds_total, read_bytes, write_bytes, nprocs)."""
    rss = read_b = write_b = 0
    cpu_now = {}
    alive = 0
    for p in procs:
        try:
            with p.oneshot():
                rss += p.memory_info().rss
                ct = p.cpu_times()
                cpu_now[p.pid] = ct.user + ct.system
                try:
                    io = p.io_counters()
                    read_b += io.read_bytes
                    write_b += io.write_bytes
                except (psutil.AccessDenied, AttributeError):
                    pass
                alive += 1
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    # cpu_seconds accumulated since start: keep the max seen per pid so a child that
    # dies between ticks does not zero out its contribution.
    for pid, c in cpu_now.items():
        prev_cpu[pid] = max(prev_cpu.get(pid, 0.0), c)
    cpu_total = sum(prev_cpu.values())
    return rss, cpu_total, read_b, write_b, alive


def verify(python, verify_py, manifest, workdir, jobs) -> dict:
    out = subprocess.run(
        [python, verify_py, "--manifest", manifest, "--outdir", str(workdir),
         "--jobs", str(jobs)], capture_output=True, text=True).stdout.strip()
    d = {}
    for tok in out.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            d[k] = v
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--panel", required=True)
    ap.add_argument("--dataset", default="-")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--tool", required=True)
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--hz", type=float, default=2.0)
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--trace", default="")
    ap.add_argument("--manifest", default="")          # ENA panel only
    ap.add_argument("--verify", default="")            # path to verify_output.py
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    wd = Path(args.workdir)
    subprocess.run(["rm", "-rf", str(wd)])
    wd.mkdir(parents=True, exist_ok=True)

    dt = 1.0 / max(0.5, args.hz)
    proc = subprocess.Popen(["bash", "-c", args.cmd], cwd=str(wd),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            preexec_fn=os.setsid)
    root = psutil.Process(proc.pid)

    t0 = time.monotonic()
    prev_cpu: dict = {}
    trace_rows = []
    peak_rss = 0
    read_prev = write_prev = None
    read_accum = write_accum = 0.0   # ∫ positive per-tick deltas (survives child death)
    t_prev = t0
    first_byte_t = None
    last_growth_t = None
    last_bytes = 0
    status = "ok"

    while True:
        finished = proc.poll() is not None
        now = time.monotonic()
        procs = tree(proc.pid)
        rss, cpu_total, read_b, write_b, nproc = sample(procs, prev_cpu)
        peak_rss = max(peak_rss, rss)

        db, _n = data_bytes(wd)
        if db > 0 and first_byte_t is None:
            first_byte_t = now - t0
        if db > last_bytes:
            last_growth_t = now - t0
            last_bytes = db

        # instantaneous I/O rates from cumulative counter deltas. A child that dies
        # between ticks drops its counter, making the delta negative -> clamp to 0
        # (we lose at most that child's last sub-tick of I/O, never overcount). The
        # positive deltas are integrated into read/write totals so the total does
        # not collapse to the last live sample (which is ~0 once children exit).
        if read_prev is not None and now > t_prev:
            d_read = max(0, read_b - read_prev)
            d_write = max(0, write_b - write_prev)
            rd = d_read / 1e6 / (now - t_prev)
            wr = d_write / 1e6 / (now - t_prev)
            read_accum += d_read / 1e6
            write_accum += d_write / 1e6
        else:
            rd = wr = 0.0
        # instantaneous CPU% from cpu-seconds delta
        cpu_pct = 0.0
        if trace_rows and now > t_prev:
            dcpu = cpu_total - trace_rows[-1][5]
            cpu_pct = 100.0 * max(0.0, dcpu) / (now - t_prev)
        trace_rows.append((now - t0, rss / 1e6, cpu_pct, rd, wr, cpu_total, nproc))

        read_prev, write_prev, t_prev = read_b, write_b, now

        if finished:
            break
        if now - t0 > args.timeout:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            status = "TIMEOUT"
            break
        time.sleep(dt)

    proc.wait()
    wall = time.monotonic() - t0
    rc = proc.returncode
    if status == "ok" and rc not in (0, None):
        status = f"rc={rc}"

    # phases (2 Hz quantised; §5)
    setup = first_byte_t if first_byte_t is not None else wall
    data_end = last_growth_t if last_growth_t is not None else setup
    phase_setup = round(setup, 2)
    phase_data = round(max(0.0, data_end - setup), 2)
    phase_verify = round(max(0.0, wall - data_end), 2)

    # cpu_core_s = final accumulated cpu-seconds over the tree (the energy proxy)
    cpu_core_s = trace_rows[-1][5] if trace_rows else 0.0
    read_total = read_accum
    write_total = write_accum
    mean_cpu = (sum(r[2] for r in trace_rows) / len(trace_rows)) if trace_rows else 0.0
    peak_cpu = max((r[2] for r in trace_rows), default=0.0)
    mean_rss = (sum(r[1] for r in trace_rows) / len(trace_rows)) if trace_rows else 0.0
    mean_write_mbps = (write_total / wall) if wall > 0 else 0.0

    bytes_on_disk, files_on_disk = data_bytes(wd)
    bytes_verified = bytes_on_disk
    md5_ok = "-"
    fmt = "sra" if args.panel.endswith("SRA") else "gz"
    if args.manifest and args.verify and Path(args.manifest).exists():
        v = verify(args.python, args.verify, args.manifest, wd, args.jobs)
        bytes_verified = int(v.get("bytes_verified", 0))
        md5_ok = "1" if int(v.get("runs_complete", 0)) >= 1 and bytes_verified > 0 else "0"
        fmt = v.get("format", fmt)

    if args.trace:
        with open(args.trace, "w") as fh:
            fh.write("t_rel_s\trss_mb\tcpu_pct\tread_mbps\twrite_mbps\tnprocs\n")
            for r in trace_rows:
                fh.write(f"{r[0]:.2f}\t{r[1]:.1f}\t{r[2]:.1f}\t{r[3]:.2f}\t{r[4]:.2f}\t{r[6]}\n")

    print("\t".join(str(x) for x in [
        args.panel, args.dataset, args.arm, args.tool, args.rep,
        f"{wall:.2f}", rc if rc is not None else -1, status,
        f"{peak_rss/1e6:.1f}", f"{mean_rss:.1f}", f"{mean_cpu:.1f}", f"{peak_cpu:.1f}",
        f"{cpu_core_s:.2f}", f"{read_total:.1f}", f"{write_total:.1f}",
        f"{mean_write_mbps:.2f}", phase_setup, phase_data, phase_verify,
        bytes_verified, bytes_on_disk, files_on_disk, fmt, md5_ok,
        os.uname().nodename.split(".")[0], time.strftime("%Y-%m-%dT%H:%M:%S"),
    ]))

    subprocess.run(["rm", "-rf", str(wd)])   # payload is transient (E3 §disk hygiene)
    return 0


if __name__ == "__main__":
    sys.exit(main())
