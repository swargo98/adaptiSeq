#!/usr/bin/env python3
"""E7b: kill a download mid-flight, restart it, and prove it RESUMED (not restarted).

This is the headline C4 evidence and the thing iSeq's Supplementary S1 never tested.
The harness is tool-agnostic: it watches the largest file in the output directory
(adaptiSeq's ``<name>.part``, wget's in-place target, aria2c's partial), so it can
score adaptiseq, iseq (``wget -c``) and kingfisher (``aria2c``) on the same footing.

Per trial:
  1. launch <cmd> in its own process group (cwd = a fresh workdir);
  2. poll the largest file at --poll-hz; when it reaches kill_frac x file_bytes,
     send SIGKILL to the whole group -- a hard kill, the worst case for resume;
  3. record offset_at_kill = bytes on disk at the kill;
  4. relaunch the IDENTICAL command and record resume_start = the smallest partial
     size seen just after restart (>= offset_at_kill => resumed; ~0 => restarted);
  5. wait for completion and judge the final file against the ENA manifest md5.

Verdict:
  RESUMED    resume_start ~ offset_at_kill AND final md5 matches (bytes_wasted ~ 0)
  RESTARTED  resume_start ~ 0 (re-downloaded offset_at_kill bytes needlessly)
  CORRUPT    a full-size file was finalised but its md5 fails (the worst outcome)
  INCOMPLETE never finished within the timeout

Emits one TSV row on stdout (header written by the caller).

NOTE on measurement honesty: adaptiSeq's resume trial is run single-stream
(--max-segments 1 in the arm) so the .part grows contiguously and its size IS the
contiguous bytes on disk. With scattered-pwrite segments, .part size is the highest
offset touched, not contiguous bytes, and a resume offset would be unmeasurable.
For wget/aria2c the partial is likewise contiguous. The instrument is a sampled
size, so resume_start uses a short min-window; sub-poll transients are invisible.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def largest_file(root: Path) -> int:
    best = 0
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.endswith((".log", ".json", ".csv")) or f.startswith("."):
                continue
            try:
                sz = os.path.getsize(os.path.join(dp, f))
            except OSError:
                continue
            if sz > best:
                best = sz
    return best


def spawn(cmd: str, workdir: Path):
    return subprocess.Popen(
        ["bash", "-c", cmd], cwd=str(workdir),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,          # own process group -> we can kill the tree
    )


def killtree(proc) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def run_to_target(cmd, workdir, target_bytes, poll_dt, timeout) -> tuple:
    """Run until largest file >= target_bytes, then SIGKILL. Returns offset_at_kill."""
    proc = spawn(cmd, workdir)
    t0 = time.monotonic()
    offset = 0
    while True:
        if proc.poll() is not None:
            # finished before we could kill it (target too high / file too small)
            return largest_file(workdir), "finished_early"
        offset = largest_file(workdir)
        if offset >= target_bytes:
            killtree(proc)
            return offset, "killed"
        if time.monotonic() - t0 > timeout:
            killtree(proc)
            return offset, "timeout_before_kill"
        time.sleep(poll_dt)


def run_resume(cmd, workdir, file_bytes, poll_dt, timeout) -> tuple:
    """Relaunch; return (resume_start, wall_s, finished)."""
    proc = spawn(cmd, workdir)
    t0 = time.monotonic()
    # resume_start = smallest partial size observed in the first window after a file
    # exists. If the tool resumed, the .part is already large; if it wiped and
    # restarted, we catch it near zero.
    resume_start = None
    window = 3.0
    while True:
        done = proc.poll() is not None
        sz = largest_file(workdir)
        if sz > 0:
            if resume_start is None or sz < resume_start:
                if time.monotonic() - t0 <= window:
                    resume_start = sz
        if done:
            return (resume_start or 0), time.monotonic() - t0, True
        if time.monotonic() - t0 > timeout:
            killtree(proc)
            return (resume_start or 0), time.monotonic() - t0, False
        time.sleep(poll_dt)


def verify(python, verify_py, manifest, workdir, jobs) -> dict:
    out = subprocess.run(
        [python, verify_py, "--manifest", manifest, "--outdir", str(workdir),
         "--jobs", str(jobs)],
        capture_output=True, text=True,
    ).stdout.strip()
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
    ap.add_argument("--file-bytes", type=int, required=True)
    ap.add_argument("--kill-frac", type=float, required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--verify", required=True, help="path to verify_output.py")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--poll-hz", type=float, default=10.0)
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--tool", default="adaptiseq")
    ap.add_argument("--rep", type=int, default=1)
    args = ap.parse_args()

    wd = Path(args.workdir)
    if wd.exists():
        subprocess.run(["rm", "-rf", str(wd)])
    wd.mkdir(parents=True, exist_ok=True)

    poll_dt = 1.0 / max(1.0, args.poll_hz)
    target = int(args.kill_frac * args.file_bytes)

    offset_at_kill, kstatus = run_to_target(
        args.cmd, wd, target, poll_dt, args.timeout)
    resume_start, wall_resume, finished = run_resume(
        args.cmd, wd, args.file_bytes, poll_dt, args.timeout)

    v = verify(args.python, args.verify, args.manifest, wd, args.jobs)
    bytes_verified = int(v.get("bytes_verified", 0))
    bytes_on_disk = int(v.get("bytes_on_disk", 0))
    runs_complete = int(v.get("runs_complete", 0))
    final_md5_ok = runs_complete >= 1 and bytes_verified > 0

    bytes_wasted = max(0, offset_at_kill - resume_start)

    if not finished or (runs_complete == 0 and bytes_on_disk < args.file_bytes):
        verdict = "INCOMPLETE"
    elif bytes_on_disk >= args.file_bytes and not final_md5_ok:
        verdict = "CORRUPT"
    elif final_md5_ok and resume_start >= 0.5 * max(1, offset_at_kill):
        verdict = "RESUMED"
    elif final_md5_ok:
        verdict = "RESTARTED"
    else:
        verdict = "INCOMPLETE"

    row = "\t".join(str(x) for x in [
        "E7b", args.tool, args.file_bytes, f"{args.kill_frac:.2f}",
        offset_at_kill, resume_start, bytes_wasted,
        int(verdict == "RESUMED"), int(final_md5_ok),
        f"{wall_resume:.1f}", verdict, kstatus, args.rep,
        os.uname().nodename.split(".")[0],
        time.strftime("%Y-%m-%dT%H:%M:%S"),
    ])
    print(row)

    subprocess.run(["rm", "-rf", str(wd)])   # payload is transient (E3 §disk hygiene)
    return 0


if __name__ == "__main__":
    sys.exit(main())
