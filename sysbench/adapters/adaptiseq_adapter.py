"""adaptiSeq adapter — drives the public `adaptiseq` CLI as an external tool.

Phase mapping:
* ``metadata`` — ``adaptiseq -m ACC`` (resolve + write metadata TSV). The "request"
  sub-phase (process start → first API call) is folded into the head of this step
  and reported separately by the sampler's first samples.
* ``data``     — ``adaptiseq -i ACC -g -k`` (direct fastq.gz, md5 skipped) so the
  data transfer is isolated from verification.
* ``md5``      — ``adaptiseq -i ACC -g`` again; files are already present, so only the
  integrity (md5) path runs over them.
"""
from __future__ import annotations

from pathlib import Path

from .base import Adapter, RunResult
from ..phases import PhaseTimeline


class AdaptiseqAdapter(Adapter):
    name = "adaptiseq"
    requires = ("adaptiseq",)

    def __init__(self, extra_args=("-d", "ena"), engine_args=()):
        self.extra_args = list(extra_args)
        self.engine_args = list(engine_args)

    def run(self, accession: str, workdir: Path, timeline: PhaseTimeline) -> RunResult:
        wd = Path(workdir)
        wd.mkdir(parents=True, exist_ok=True)
        rr = RunResult(self.name, accession, str(wd))

        timeline.mark("request")  # brief: process launch before first API call
        meta = self._run_step(timeline, "metadata",
                              ["adaptiseq", "-i", accession, "-m", "-o", str(wd)] + self.extra_args,
                              wd)
        rr.steps.append(meta)

        data = self._run_step(timeline, "data",
                             ["adaptiseq", "-i", accession, "-g", "-k", "-o", str(wd)]
                             + self.extra_args + self.engine_args, wd)
        rr.steps.append(data)

        md5 = self._run_step(timeline, "md5",
                            ["adaptiseq", "-i", accession, "-g", "-o", str(wd)]
                            + self.extra_args + self.engine_args, wd)
        rr.steps.append(md5)

        timeline.mark("idle")
        rr.bytes_downloaded = self._dir_bytes(wd)
        rr.formats = self._formats(wd)
        rr.ok = all(s.returncode == 0 for s in rr.steps) and rr.bytes_downloaded > 0
        return rr
