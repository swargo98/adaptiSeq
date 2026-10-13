"""SRA Toolkit adapter — `prefetch` (+ `vdb-validate`).

Phase mapping:
* ``metadata`` — ``srapath ACC`` (resolve the object location). prefetch fetches its
  own metadata internally; ``srapath`` is the closest discrete resolution step.
* ``data``     — ``prefetch ACC`` (downloads the ``.sra`` object).
* ``md5``      — ``vdb-validate`` over the downloaded object (checksum/structure).

Note: prefetch fetches ``.sra`` (not ``.fastq.gz``); the runner records bytes+format
so the cross-tool comparison stays fair (different payloads).
"""
from __future__ import annotations

from pathlib import Path

from .base import Adapter, RunResult
from ..phases import PhaseTimeline


class SraToolkitAdapter(Adapter):
    name = "sra-toolkit"
    requires = ("prefetch", "vdb-validate")

    def run(self, accession: str, workdir: Path, timeline: PhaseTimeline) -> RunResult:
        wd = Path(workdir)
        wd.mkdir(parents=True, exist_ok=True)
        rr = RunResult(self.name, accession, str(wd))

        timeline.mark("request")
        meta = self._run_step(timeline, "metadata", ["srapath", accession], wd)
        rr.steps.append(meta)

        data = self._run_step(timeline, "data",
                             ["prefetch", accession, "-O", str(wd)], wd)
        rr.steps.append(data)

        sra = next((p for p in wd.rglob("*.sra")), None)
        md5 = self._run_step(timeline, "md5",
                            ["vdb-validate", str(sra) if sra else accession], wd)
        rr.steps.append(md5)

        timeline.mark("idle")
        rr.bytes_downloaded = self._dir_bytes(wd, patterns=(".sra",))
        rr.formats = self._formats(wd)
        rr.ok = data.returncode == 0 and rr.bytes_downloaded > 0
        return rr
