"""pysradb adapter.

Phase mapping:
* ``metadata`` — ``pysradb metadata ACC --detailed`` (study/run metadata table).
* ``data``     — ``pysradb download -y -t 4 --out-dir WD ACC`` (fetches via ENA/SRA).
* ``md5``      — pysradb performs no integrity check by default, so this phase is
  reported as ``n/a`` (returncode -1, zero duration) for honest accounting.

pysradb's ``download`` works most naturally on study/project accessions; for a bare
run accession it may resolve via its SRAweb lookup. The runner records whatever bytes
land plus the format, so a partial/empty download is reported rather than hidden.
"""
from __future__ import annotations

from pathlib import Path

from .base import Adapter, RunResult, StepResult
from ..phases import PhaseTimeline


class PysradbAdapter(Adapter):
    name = "pysradb"
    requires = ("pysradb",)

    def run(self, accession: str, workdir: Path, timeline: PhaseTimeline) -> RunResult:
        wd = Path(workdir)
        wd.mkdir(parents=True, exist_ok=True)
        rr = RunResult(self.name, accession, str(wd))

        timeline.mark("request")
        meta = self._run_step(timeline, "metadata",
                              ["pysradb", "metadata", accession, "--detailed"], wd)
        rr.steps.append(meta)

        data = self._run_step(timeline, "data",
                             ["pysradb", "download", "-y", "-t", "4",
                              "--out-dir", str(wd), accession], wd)
        rr.steps.append(data)

        # pysradb has no built-in md5 verification.
        rr.steps.append(StepResult("md5", ["<none>"], -1, 0.0,
                                   stderr="pysradb performs no md5 check"))
        rr.note = "md5 phase n/a (pysradb has no integrity check)"

        timeline.mark("idle")
        rr.bytes_downloaded = self._dir_bytes(wd)
        rr.formats = self._formats(wd)
        rr.ok = data.returncode == 0 and rr.bytes_downloaded > 0
        return rr
