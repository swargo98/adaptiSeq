"""pysradb adapter.

Phase mapping:
* ``metadata`` — ``pysradb metadata ACC --detailed`` (run/experiment metadata table);
  the ``experiment_accession`` (SRX/ERX/DRX) is parsed from it for the next step.
* ``data``     — ``pysradb download -y -t 4 --srx <SRX> --out-dir WD``. pysradb's
  ``download`` takes ``--srx``/``--srp``/``--geo`` (NOT a bare run accession), so the
  run is resolved to its experiment first.
* ``md5``      — pysradb performs no integrity check by default → reported ``n/a``.

Environment note: pysradb ``download`` relies on an SRAweb/eutils → ENA lookup that
intermittently returns an empty document (``EmptyDataError``); when that happens the
data step fails and is reported honestly (bytes=0) rather than hidden. The metadata
step is reliable.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .base import Adapter, RunResult, StepResult
from ..phases import PhaseTimeline


def _experiment_from_metadata(stdout: str) -> str:
    """Pull experiment_accession (SRX/ERX/DRX) out of `pysradb metadata` TSV output."""
    try:
        reader = csv.DictReader(io.StringIO(stdout), delimiter="\t")
        for row in reader:
            for key in ("experiment_accession", "experiment"):
                v = (row.get(key) or "").strip()
                if v[:3] in ("SRX", "ERX", "DRX"):
                    return v
    except Exception:
        pass
    # fallback: scan tokens
    for tok in stdout.split():
        if tok[:3] in ("SRX", "ERX", "DRX") and tok[3:].isdigit():
            return tok
    return ""


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

        srx = _experiment_from_metadata(meta.stdout) or accession
        data = self._run_step(timeline, "data",
                             ["pysradb", "download", "-y", "-t", "4",
                              "--srx", srx, "--out-dir", str(wd)], wd)
        rr.steps.append(data)

        # pysradb has no built-in md5 verification.
        rr.steps.append(StepResult("md5", ["<none>"], -1, 0.0,
                                   stderr="pysradb performs no md5 check"))
        rr.note = f"md5 phase n/a (pysradb has no integrity check); resolved srx={srx}"

        timeline.mark("idle")
        rr.bytes_downloaded = self._dir_bytes(wd)
        rr.formats = self._formats(wd)
        rr.ok = data.returncode == 0 and rr.bytes_downloaded > 0
        return rr
