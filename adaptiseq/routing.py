"""Database routing and the ``-e`` merge accession-type guards.

Two responsibilities, both faithful ports:

1. Decide whether an accession is handled by the GSA branch or the SRA/ENA/DDBJ/
   GEO branch of the main process loop (``is_gsa`` in :mod:`accession`). The
   ENA-vs-SRA choice within the SRA branch is dynamic (ENA first, fall back to
   SRA when ENA returns no rows) and lives in :mod:`metadata`.
2. Enforce the ``-e ex|sa|st`` accession-type guards that iseq applies up front
   (lines 174-202 of the Bash), with the exact same error/solution text.
"""

from __future__ import annotations

import re
from typing import Iterable

from .accession import is_gsa  # re-exported for convenience
from .errors import AdaptiSeqError

__all__ = ["is_gsa", "route", "check_merge_guard"]

# Verbatim guard patterns (note: include C for GSA, as the Bash does).
_RE_RUN_ANY = re.compile(r"^[CEDS]RR[0-9]{6,}$")
_RE_EXP_ANY = re.compile(r"^[CEDS]RX[0-9]{6,}$")
_RE_SAMPLE_SEC = re.compile(r"^[EDS]RS[0-9]{6,}$")
_RE_SAMPLE_BIO = re.compile(r"^SAM[CEDN][A-Z]?[0-9]+$")


def route(accession: str) -> str:
    """Return ``"gsa"`` or ``"sra"`` for the top-level process branch."""
    return "gsa" if is_gsa(accession) else "sra"


def check_merge_guard(merge: str, accessions: Iterable[str]) -> None:
    """Port of the ``-e`` guard block. Raises :class:`AdaptiSeqError` on a bad type.

    ``merge`` is one of ``ex``/``sa``/``st``. Mirrors the Bash messages exactly.
    """
    for accession in accessions:
        if merge == "ex":
            if _RE_RUN_ANY.match(accession):
                raise AdaptiSeqError(
                    f"{accession} is a Run ID, can not use -e option",
                    'Please use a Project, Study, Sample, or Experiment accession '
                    'for the "-i" option',
                )
        elif merge == "sa":
            if _RE_RUN_ANY.match(accession) or _RE_EXP_ANY.match(accession):
                raise AdaptiSeqError(
                    f"{accession} is a Run ID or Experiment ID, can not use -e option",
                    'Please use a Project, Study, or Sample accession for the '
                    '"-i" option',
                )
        elif merge == "st":
            if (
                _RE_RUN_ANY.match(accession)
                or _RE_EXP_ANY.match(accession)
                or _RE_SAMPLE_SEC.match(accession)
                or _RE_SAMPLE_BIO.match(accession)
            ):
                raise AdaptiSeqError(
                    f"{accession} is a Run ID, Experiment ID, or Sample ID, "
                    "can not use -e option",
                    'Please use a Project or Study accession for the "-i" option',
                )
        else:  # pragma: no cover - guarded by Options validation
            raise AdaptiSeqError(
                f"Invalid merge: {merge}",
                'Please use "ex", "sa", or "st" for the "-e" option',
            )
