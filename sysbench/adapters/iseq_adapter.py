"""Stock iSeq adapter (the Bash original) — the tool adaptiSeq is derived from.

Requires `iseq` on PATH (symlink `iSeq-main/bin/iseq`) and, for `-a`, a real `ascp`
(provision via `bench/setup_real_ascp.sh`). Phase mapping mirrors the adaptiSeq
adapter so the two are directly comparable:

* ``metadata`` — ``iseq -i ACC -m``
* ``data``     — ``iseq -i ACC -g -k`` (direct fastq.gz, md5 skipped)
* ``md5``      — ``iseq -i ACC -g`` (files present → only the md5 check runs)
"""
from __future__ import annotations

from pathlib import Path

from .base import Adapter, RunResult
from ..phases import PhaseTimeline


class IseqAdapter(Adapter):
    name = "iseq"
    requires = ("iseq", "wget")

    def __init__(self, extra_args=("-d", "ena")):
        self.extra_args = list(extra_args)

    def run(self, accession: str, workdir: Path, timeline: PhaseTimeline) -> RunResult:
        wd = Path(workdir)
        wd.mkdir(parents=True, exist_ok=True)
        rr = RunResult(self.name, accession, str(wd))

        timeline.mark("request")
        # iseq writes to its CWD, so each step runs with cwd=wd (set by _run_step).
        meta = self._run_step(timeline, "metadata",
                              ["iseq", "-i", accession, "-m"] + self.extra_args, wd)
        rr.steps.append(meta)

        data = self._run_step(timeline, "data",
                             ["iseq", "-i", accession, "-g", "-k"] + self.extra_args, wd)
        rr.steps.append(data)

        md5 = self._run_step(timeline, "md5",
                            ["iseq", "-i", accession, "-g"] + self.extra_args, wd)
        rr.steps.append(md5)

        timeline.mark("idle")
        rr.bytes_downloaded = self._dir_bytes(wd)
        rr.formats = self._formats(wd)
        rr.ok = data.returncode == 0 and rr.bytes_downloaded > 0
        return rr
