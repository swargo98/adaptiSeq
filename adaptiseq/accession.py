"""Accession validation and GEO resolution (``validateQuery``).

The regexes are a behavioural contract: they define exactly which accession forms
are accepted. Extended-regex ``=~`` patterns map directly to Python ``re`` with the
same anchors and quantifiers.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .console import green, red_bold, Reporter, NullReporter
from .errors import InvalidAccessionError
from .net import wget_capture

# --- Accession guard patterns (=~ style) ----------------------------------------
# validateQuery (SRA/ENA/DDBJ/GEO path):
RE_PROJECT_STUDY = re.compile(r"^PRJ[EDN][A-Z][0-9]+$|^[EDS]RP[0-9]{6,}$")
RE_BIOSAMPLE_SAMPLE = re.compile(r"^SAM[EDN][A-Z]?[0-9]+$|^[EDS]RS[0-9]{6,}$")
RE_EXPERIMENT = re.compile(r"^[EDS]RX[0-9]{6,}$")
RE_RUN = re.compile(r"^[EDS]RR[0-9]{6,}$")
RE_GSE = re.compile(r"^GSE[0-9]+$")
RE_GSM = re.compile(r"^GSM[0-9]+$")

# GSA routing (main loop / getGSAMetadata):
RE_GSA = re.compile(r"^PRJC[A-Z][0-9]+$|^SAMC[0-9]+$|^CRA[0-9]+$|^CRX[0-9]+$|^CRR[0-9]+$")
RE_GSA_CRR_CRX = re.compile(r"^CRR[0-9]+$|^CRX[0-9]+$")
RE_GSA_PROJECT = re.compile(r"^PRJC[A-Z][0-9]+$|^SAMC[0-9]+$|^CRA[0-9]+$")

# grep -oe patterns used to scrape resolved IDs from HTML / metadata:
RE_BIOPROJECT_SCRAPE = re.compile(r"PRJ[EDN][A-Z][0-9]+")
RE_BIOSAMPLE_SCRAPE = re.compile(r"SAM[EDN][A-Z]?[0-9]+")
RE_CRA_SCRAPE = re.compile(r"CRA[0-9]+")

GEO_URL = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={acc}"


def is_gsa(accession: str) -> bool:
    """True if the accession routes to the GSA database (PRJC/SAMC/CRA/CRX/CRR)."""
    return bool(RE_GSA.match(accession))


def _uniq_adjacent(items: List[str]) -> List[str]:
    """Reproduce ``uniq`` (collapse *adjacent* duplicates, not a global sort)."""
    out: List[str] = []
    for it in items:
        if not out or out[-1] != it:
            out.append(it)
    return out


def validate_query(accession: str, reporter: Optional[Reporter] = None) -> str:
    """``validateQuery``: validate and normalise an accession.

    Returns the query accession to feed the ENA/SRA metadata API. Direct
    accession types pass through unchanged; GEO ``GSE``/``GSM`` are resolved to a
    BioProject / BioSample via the NCBI GEO page. Raises
    :class:`InvalidAccessionError` for anything unrecognised.
    """
    reporter = reporter or NullReporter()

    if RE_PROJECT_STUDY.match(accession):
        return accession
    if RE_BIOSAMPLE_SAMPLE.match(accession):
        return accession
    if RE_EXPERIMENT.match(accession):
        return accession
    if RE_RUN.match(accession):
        return accession
    if RE_GSE.match(accession):
        html = wget_capture(GEO_URL.format(acc=accession))
        matches = _uniq_adjacent(RE_BIOPROJECT_SCRAPE.findall(html))
        if not matches:
            raise InvalidAccessionError(
                f"{accession} is not valid GEO Series accession."
            )
        bioproject = "\n".join(matches)
        reporter.error(f"{green('Note')}: {accession} belongs to {bioproject}")
        return bioproject
    if RE_GSM.match(accession):
        html = wget_capture(GEO_URL.format(acc=accession))
        matches = _uniq_adjacent(RE_BIOSAMPLE_SCRAPE.findall(html))
        if not matches:
            raise InvalidAccessionError(
                f"{accession} is not a valid GEO Sample accession."
            )
        biosample = "\n".join(matches)
        reporter.error(f"{green('Note')}: {accession} belongs to {biosample}")
        return biosample

    raise InvalidAccessionError(
        f"{accession} is not a valid Study, Sample, Experiment, or Run accession."
    )
