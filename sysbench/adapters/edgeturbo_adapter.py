"""EdgeTurbo adapter — NGDC/CNCB's GSA download accelerator (the iSeq paper's GSA
comparator in Fig. 1D).

EdgeTurbo is **GSA-only** and daemon-based: a background ``serv_edgeturbo`` does a
UDP-accelerated transfer, driven by an interactive ``edgeturbo`` CLI whose status
window is a ``top``-style UI that **requires a TTY**. So this adapter drives ``dl``
under a pseudo-terminal (``pty``) and polls the captured TTY log for completion.

Accession form: pass the **GSA remote path** (EdgeTurbo's native input), e.g.
``/gsa/CRA004720/CRR311238/CRR311238.fq.gz``. (A bare ``CRR`` could be resolved to a
path via the GSA listing; kept explicit here to match how EdgeTurbo is actually used.)

Phase mapping:
* ``request``  — ``edgeturbo restart`` (start/refresh the service + set local dir).
* ``data``     — ``edgeturbo dl <path>`` under a pty; poll until the file lands.
* ``md5``      — GSA publishes ``<CRA>.md5sum.txt``; verification is left to the GSA
  integrity path and marked here if unavailable.

SANDBOX LIMITATION (2026-06): the client installs and the daemon opens its transport
ports, but the UDP-accelerated transfer to NGDC **stalls at 0%** from this (US) test
host — NGDC's accelerated transport is unreachable here, while ENA Aspera to EBI works
fine. Run this adapter from a network with working NGDC connectivity (e.g. within
CN/CSTNET) to produce real EdgeTurbo numbers; otherwise it reports a stall, honestly.
"""
from __future__ import annotations

import os
import pty
import re
import shutil
import subprocess
import time
from pathlib import Path

from .base import Adapter, RunResult, StepResult
from ..phases import PhaseTimeline

_PCT = re.compile(rb"(\d{1,3})%")


class EdgeturboAdapter(Adapter):
    name = "edgeturbo"
    requires = ("edgeturbo",)

    def __init__(self, poll_timeout: float = 1800, settle: float = 3.0):
        self.poll_timeout = poll_timeout
        self.settle = settle

    def _dl_under_pty(self, remote_path: str, wd: Path) -> StepResult:
        """Run `edgeturbo dl` under a pty, polling until the target file completes."""
        target = wd / Path(remote_path).name
        argv = ["edgeturbo", "dl", remote_path]
        t0 = time.monotonic()
        pid, fd = pty.fork()
        if pid == 0:  # child: exec inside the pty so the top-style UI initialises
            os.chdir(str(wd))
            os.execvp(argv[0], argv)
            os._exit(127)  # unreachable
        last_pct = b"0"
        done = False
        try:
            while time.monotonic() - t0 < self.poll_timeout:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    chunk = b""
                if chunk:
                    m = _PCT.findall(chunk)
                    if m:
                        last_pct = m[-1]
                # completion = file present and size stable, or 100% seen
                if target.exists() and target.stat().st_size > 0:
                    s1 = target.stat().st_size
                    time.sleep(1.0)
                    if target.exists() and target.stat().st_size == s1:
                        done = True
                        break
                if last_pct == b"100":
                    done = True
                    break
                time.sleep(0.5)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass
        rc = 0 if done else 124
        return StepResult("data", argv, rc, time.monotonic() - t0,
                          stderr="" if done else f"stalled at {last_pct.decode()}%")

    def run(self, accession: str, workdir: Path, timeline: PhaseTimeline) -> RunResult:
        wd = Path(workdir)
        wd.mkdir(parents=True, exist_ok=True)
        rr = RunResult(self.name, accession, str(wd))

        timeline.mark("request")
        self._run_step(timeline, "request", ["edgeturbo", "restart"], wd, timeout=30)
        self._run_step(timeline, "request", ["edgeturbo", "set", str(wd)], wd, timeout=30)

        timeline.mark("data")
        data = self._dl_under_pty(accession, wd)
        rr.steps.append(data)

        # GSA md5: <CRA>.md5sum.txt verification is handled by the GSA integrity path;
        # not reproduced here. Marked n/a so accounting stays honest.
        rr.steps.append(StepResult("md5", ["<gsa-md5>"], -1, 0.0,
                                   stderr="GSA md5 via CRA.md5sum.txt not run in adapter"))
        timeline.mark("idle")

        # cleanup: stop the long-lived daemon between runs
        subprocess.run(["edgeturbo", "stop"], cwd=str(wd),
                       capture_output=True, timeout=30)

        rr.bytes_downloaded = self._dir_bytes(wd, patterns=(".fq.gz", ".fastq.gz", ".sra"))
        rr.formats = self._formats(wd)
        rr.ok = data.returncode == 0 and rr.bytes_downloaded > 0
        if data.returncode != 0:
            rr.note = ("edgeturbo transport stalled (NGDC accelerated transport "
                       "unreachable from this host); run from an NGDC-reachable network")
        return rr
