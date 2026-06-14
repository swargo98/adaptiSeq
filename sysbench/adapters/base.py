"""Adapter contract for the system benchmark.

An adapter knows how to drive ONE tool through the four phases (request, metadata,
data, md5) for a given accession, marking phase boundaries on a
:class:`~sysbench.phases.PhaseTimeline` so the sampler can attribute each 1 s sample
to a phase. Adapters treat every tool — including adaptiSeq — as an external command;
nothing imports package internals.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..phases import PhaseTimeline


@dataclass
class StepResult:
    phase: str
    argv: List[str]
    returncode: int
    seconds: float
    stdout: str = ""
    stderr: str = ""


@dataclass
class RunResult:
    tool: str
    accession: str
    workdir: str
    steps: List[StepResult] = field(default_factory=list)
    bytes_downloaded: int = 0
    formats: List[str] = field(default_factory=list)
    ok: bool = True
    note: str = ""

    @property
    def returncodes(self):
        return {s.phase: s.returncode for s in self.steps}


class Adapter:
    """Base class. Subclasses implement :meth:`run`."""

    name = "base"
    #: external executables this adapter needs
    requires: tuple = ()

    def available(self) -> Optional[str]:
        """Return None if runnable, else a human reason it is not."""
        missing = [c for c in self.requires if shutil.which(c) is None]
        return None if not missing else f"missing: {', '.join(missing)}"

    # --- helpers ------------------------------------------------------------
    @staticmethod
    def _run_step(timeline: PhaseTimeline, phase: str, argv: List[str],
                  cwd: Path, timeout: float = 1800) -> StepResult:
        timeline.mark(phase)
        t0 = time.monotonic()
        try:
            p = subprocess.run(argv, cwd=str(cwd), capture_output=True,
                               text=True, timeout=timeout)
            rc, out, err = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired as e:
            rc, out, err = 124, "", f"timeout: {e}"
        dt = time.monotonic() - t0
        return StepResult(phase, argv, rc, dt, out[-4000:], err[-4000:])

    @staticmethod
    def _dir_bytes(workdir: Path, patterns=(".fastq.gz", ".fastq", ".sra", ".bam")) -> int:
        total = 0
        for f in Path(workdir).rglob("*"):
            if f.is_file() and any(f.name.endswith(p) for p in patterns):
                total += f.stat().st_size
        return total

    @staticmethod
    def _formats(workdir: Path) -> List[str]:
        exts = set()
        for f in Path(workdir).rglob("*"):
            if f.is_file():
                for p in (".fastq.gz", ".fastq", ".sra", ".bam", ".gz"):
                    if f.name.endswith(p):
                        exts.add(p)
                        break
        return sorted(exts)

    def run(self, accession: str, workdir: Path, timeline: PhaseTimeline) -> RunResult:
        raise NotImplementedError
