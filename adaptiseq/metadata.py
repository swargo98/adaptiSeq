"""Metadata fetching for ENA / SRA-fallback / GSA.

Filenames, endpoints, POST bodies, user-agents, and the comma→tab conversion are
fixed by the archive APIs. All bytes are pulled by ``wget`` (see
:mod:`adaptiseq.net`) so the saved files are exactly what the archive serves.

Files produced:
* ``${accession}.metadata.tsv``  — ENA filereport, or SRA runinfo (comma→tab).
* ``${accession}.metadata.csv``  — GSA getRunInfo / getRunInfoByCra.
* ``${CRA}.metadata.xlsx``       — GSA exportExcelFile (3 sheets).
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import List, Optional

from .accession import (
    RE_CRA_SCRAPE,
    RE_GSA_CRR_CRX,
    RE_GSA_PROJECT,
    _uniq_adjacent,
    validate_query,
)
from .console import bright_yellow, green, red_bold
from .errors import MetadataError
from .net import USER_AGENT_MOZILLA, wget_capture, wget_to_file
from .options import RunContext

# The exact ENA filereport field list from getSRAMetadata (do not reorder).
ENA_FIELDS = (
    "study_accession,secondary_study_accession,sample_accession,"
    "secondary_sample_accession,experiment_accession,run_accession,"
    "submission_accession,tax_id,scientific_name,instrument_platform,"
    "instrument_model,library_name,nominal_length,library_layout,"
    "library_strategy,library_source,library_selection,read_count,base_count,"
    "center_name,first_public,last_updated,experiment_title,study_title,"
    "study_alias,experiment_alias,run_alias,fastq_bytes,fastq_md5,fastq_ftp,"
    "fastq_aspera,fastq_galaxy,submitted_bytes,submitted_md5,submitted_ftp,"
    "submitted_aspera,submitted_galaxy,submitted_format,sra_bytes,sra_md5,"
    "sra_ftp,sra_aspera,sra_galaxy,sample_alias,broker_name,sample_title,"
    "nominal_sdev,first_created,bam_ftp,bam_bytes,bam_md5"
)

ENA_URL = (
    "https://www.ebi.ac.uk/ena/portal/api/filereport?accession={query}"
    "&result=read_run&fields={fields}&format=tsv&download=true&limit=0"
)
ESEARCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    "?db=sra&term={accession}&usehistory=y"
)
SRA_DB_BE_URL = (
    "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/sra-db-be.cgi"
    "?rettype=runinfo&WebEnv={webenv}&query_key={querykey}"
)
GSA_SEARCH_URL = "https://ngdc.cncb.ac.cn/gsa/search?searchTerm={term}"
GSA_RUNINFO_BY_CRA = "https://ngdc.cncb.ac.cn/gsa/search/getRunInfoByCra"
GSA_RUNINFO = "https://ngdc.cncb.ac.cn/gsa/search/getRunInfo"
GSA_EXPORT_XLSX = "https://ngdc.cncb.ac.cn/gsa/file/exportExcelFile"

_RE_WEBENV = re.compile(r"<WebEnv>([^<]+)")
_RE_QUERYKEY = re.compile(r"<QueryKey>([^<]+)")


# ENA's portal sometimes answers with HTTP 200 and, in place of (or after) the
# rows, a line "ERROR occurred. Not all results may have been written.Query:
# {...}". Taken at face value that line becomes a Run called "ERROR occurred..."
# and the accession is lost; seen on 2026-10-13 for about 1 query in 60, by every
# tool in the benchmark. The answer is transient: the same query succeeds later.
ENA_ERROR_MARKER = "ERROR occurred"
ENA_RETRY_BASE_S = 2.0    # sleep 2, 4, 8, 16, 30, 30 ... s between tries
# During the ENA portal outage of 2026-10-15 the portal also answered with HTTP
# 500 (wget exits non-zero and leaves an empty file), timed out, or returned
# HTTP 200 with the header line and no rows for a Run that is in ENA. Each of
# these used to read as "not in ENA" and sent the Run to SRA, whose converted
# FASTQ cannot match ENA's md5. A failed request is retried like an error body;
# an empty answer is retried once, so a Run that is really SRA-only costs one
# extra query.
ENA_EMPTY_ATTEMPTS = 2
# Round 2 rep 3 (2026-10-21): the portal answered in 24-45 s with an HTTP 500 now
# and then for three hours, and two runs went to SRA (unverifiable) after about
# 15 s of retries. Retries are now bounded by time, and the time is shared by
# every accession: the portal may keep failing for ENA_PATIENCE_S, counted from
# the first failure of the current streak, before runs fall back to SRA. So one
# long outage costs a 241-run list about that long once, not once per run. Each
# accession still tries ENA_MIN_ATTEMPTS times. An empty answer counts as "not
# in ENA" only when it came back quickly (a healthy portal answers in about a
# second) and nothing else is failing; a slow one is the portal under strain.
ENA_ATTEMPTS = 12         # hard cap per accession
ENA_RETRY_MAX_S = 30.0
ENA_PATIENCE_S = 180.0
ENA_MIN_ATTEMPTS = 2
ENA_SLOW_S = 5.0
ENA_STREAK_GAP_S = 60.0   # a streak ends after this long without a failure
_sleep = time.sleep       # patched in tests
_now = time.monotonic     # patched in tests
_ena_lock = threading.Lock()
_ena_streak = {"since": None, "last": None}


def _ena_failing(now: float) -> Optional[float]:
    """Start of the current ENA failure streak, or None if ENA is healthy."""
    with _ena_lock:
        last = _ena_streak["last"]
        if last is None or now - last > ENA_STREAK_GAP_S:
            _ena_streak["since"] = _ena_streak["last"] = None
        return _ena_streak["since"]


def _ena_note(ok: bool, now: float) -> None:
    with _ena_lock:
        if ok:
            _ena_streak["since"] = _ena_streak["last"] = None
        else:
            if _ena_streak["since"] is None:
                _ena_streak["since"] = now
            _ena_streak["last"] = now


def reset_ena_streak() -> None:
    """Forget past ENA failures (tests; a new process starts clean anyway)."""
    _ena_note(True, 0.0)
# GSA's getRunInfoByCra can answer with a table that lacks a Run (round 2 rep 1,
# 2026-10-20: CRR120307's table had only the header). Filtered to that Run, the
# CSV then held no rows and the Run was skipped with exit 0. Retry, then fail.
GSA_ATTEMPTS = 4
GSA_RETRY_BASE_S = 2.0


def gsa_csv_has_rows(path: Path) -> bool:
    """True if a GSA metadata CSV has at least one Run row under its header."""
    return bool(_row2_field1(path, ","))


def has_ena_error(path: Path) -> bool:
    """True if a saved metadata TSV contains ENA's in-band error line."""
    try:
        with open(path, "r", errors="replace") as fh:
            return any(ln.lstrip().startswith(ENA_ERROR_MARKER) for ln in fh)
    except FileNotFoundError:
        return False


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _ena_problem(rc: int, tsv: Path) -> str:
    """Why an ENA filereport answer can't be used ("" if it can)."""
    if rc != 0:
        return f"request failed, wget exit {rc}"
    if has_ena_error(tsv):
        return "error body"
    if not _row2_field1(tsv, "\t"):
        return "empty answer"
    return ""


# --- small awk-equivalents ------------------------------------------------------

def _row2_field1(path: Path, sep: str) -> str:
    """``awk -vFS=sep 'NR==2 {print $1}' file`` — first field of the 2nd line."""
    try:
        with open(path, "r", errors="replace") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return ""
    if len(lines) < 2:
        return ""
    fields = lines[1].split(sep)
    return fields[0] if fields else ""


# ================================ ENA / SRA =====================================

def is_ena_tsv(path: Path) -> bool:
    """True if ``path`` holds an ENA filereport (not the SRA runinfo fallback)."""
    try:
        with open(path, errors="replace") as fh:
            return fh.readline().startswith("study_accession\t")
    except OSError:
        return False


def get_sra_metadata(ctx: RunContext, accession: str) -> Path:
    """Fetch SRA/ENA run metadata.

    Tries ENA first; on an empty result flips ``ctx.database`` to ``sra`` and
    falls back to the NCBI eutils + sra-db-be runinfo (comma→tab). Raises
    :class:`MetadataError` if both are empty.
    """
    reporter = ctx.reporter
    query = validate_query(accession, reporter)

    tsv = ctx.metadata_tsv(accession)
    empty = 0
    for attempt in range(1, ENA_ATTEMPTS + 1):
        if has_ena_error(tsv):
            _unlink(tsv)  # never resume (-c) onto an error body
        t0 = _now()
        rc = wget_to_file(
            ENA_URL.format(query=query, fields=ENA_FIELDS),
            tsv,
            cont=True,
            quiet=True,
        )
        now = _now()
        problem = _ena_problem(rc, tsv)
        if not problem:
            _ena_note(True, now)
            break
        # Drop whatever came back (error page, partial or header-only file):
        # never resume onto it, and let the SRA path below start clean.
        _unlink(tsv)
        if (problem == "empty answer" and now - t0 < ENA_SLOW_S
                and _ena_failing(now) is None):
            empty += 1
            if empty >= ENA_EMPTY_ATTEMPTS:
                break  # ENA keeps answering with no rows: not in ENA
        else:
            if problem == "empty answer":
                problem = f"empty answer after {now - t0:.0f} s"
            _ena_note(False, now)
            since = _ena_failing(now)
            if (attempt >= ENA_MIN_ATTEMPTS and since is not None
                    and now - since >= ENA_PATIENCE_S):
                break  # ENA has been failing for minutes: fall back
        if attempt < ENA_ATTEMPTS:
            delay = min(ENA_RETRY_MAX_S, ENA_RETRY_BASE_S * 2 ** (attempt - 1))
            reporter.info(
                f"{bright_yellow('Note')}: ENA query for {accession} failed "
                f"({problem}, attempt {attempt}/{ENA_ATTEMPTS}), retrying in {delay:.0f} s"
            )
            _sleep(delay)

    if not _row2_field1(tsv, "\t"):
        if ctx.options.no_sra_fallback:
            raise MetadataError(
                f"No usable ENA metadata for {accession}, and SRA fallback is "
                "disabled (--no-sra-fallback)",
                "ENA may be down or the run may exist only in SRA: retry later, "
                "or drop --no-sra-fallback to accept files that cannot be checked "
                "against ENA's md5",
            )
        reporter.info(
            f"{bright_yellow('Note')}: No metadata information found for "
            f"{accession} in the ENA database, try to download from the SRA database"
        )
        ctx.database = "sra"
        xml = ctx.path(f"{accession}.xml")
        wget_to_file(ESEARCH_URL.format(accession=accession), xml, quiet=True)
        body = xml.read_text(errors="replace") if xml.exists() else ""
        webenv_m = _RE_WEBENV.search(body)
        querykey_m = _RE_QUERYKEY.search(body)
        webenv = webenv_m.group(1) if webenv_m else ""
        querykey = querykey_m.group(1) if querykey_m else ""
        try:
            xml.unlink()
        except FileNotFoundError:
            pass
        wget_to_file(
            SRA_DB_BE_URL.format(webenv=webenv, querykey=querykey),
            tsv,
            quiet=True,
        )
        _comma_to_tab_inplace(tsv)

        if not _row2_field1(tsv, "\t"):
            try:
                tsv.unlink()
            except FileNotFoundError:
                pass
            raise MetadataError(
                f"No metadata information found for {accession} in the all databases",
                f"1. Check your accession format: {accession}; 2. {accession} is "
                "not available in the SRA database; 3. Network is not available on "
                "your server",
            )
    return tsv


def _comma_to_tab_inplace(path: Path) -> None:
    """``sed -i "s/,/\\t/g"`` — replace every comma with a tab."""
    if not path.exists():
        return
    data = path.read_text(errors="replace")
    path.write_text(data.replace(",", "\t"))


# ==================================== GSA =======================================

def get_gsa_xlsx(ctx: RunContext, cra: str) -> Path:
    """Fetch the GSA metadata XLSX (``exportExcelFile``)."""
    out = ctx.path(f"{cra}.metadata.xlsx")
    wget_to_file(
        GSA_EXPORT_XLSX,
        out,
        post_data=f"type=3&dlAcession={cra}",
        user_agent=USER_AGENT_MOZILLA,
        quiet=True,
    )
    return out


def get_gsa_metadata(ctx: RunContext, accession: str) -> Path:
    """Fetch GSA metadata.

    Produces ``${accession}.metadata.csv`` plus ``${CRA}.metadata.xlsx`` for each
    owning project. Raises :class:`MetadataError` on an unresolvable accession.
    """
    reporter = ctx.reporter
    csv = ctx.metadata_csv(accession)

    if RE_GSA_CRR_CRX.match(accession):
        html = wget_capture(
            GSA_SEARCH_URL.format(term=accession), user_agent=USER_AGENT_MOZILLA
        )
        cleaned = [ln for ln in html.splitlines() if "example" not in ln]
        cra_matches = _uniq_adjacent(
            RE_CRA_SCRAPE.findall("\n".join(cleaned))
        )
        cra = cra_matches[0] if cra_matches else ""
        if not cra:
            raise MetadataError(
                f"Cannot infer the Project ID (CRA*) for {accession}.",
                "1. Check your internet connection (You can try "
                f'"wget {GSA_SEARCH_URL.format(term=accession)}" for a test). '
                f"2. Check the format of {accession}.",
            )
        tmp = ctx.path(f"{accession}.tmp")
        for attempt in range(1, GSA_ATTEMPTS + 1):
            wget_to_file(
                GSA_RUNINFO_BY_CRA,
                tmp,
                post_data=f"searchTerm={cra}&totalDatas=9999&downLoadCount=9999",
                user_agent=USER_AGENT_MOZILLA,
                quiet=True,
            )
            _filter_rows_containing(tmp, csv, accession)
            _unlink(tmp)
            if gsa_csv_has_rows(csv):
                break
            if attempt < GSA_ATTEMPTS:
                delay = GSA_RETRY_BASE_S * 2 ** (attempt - 1)
                reporter.info(
                    f"{bright_yellow('Note')}: GSA run-info for {cra} has no row "
                    f"for {accession} (attempt {attempt}/{GSA_ATTEMPTS}), "
                    f"retrying in {delay:.0f} s"
                )
                _sleep(delay)
        if not gsa_csv_has_rows(csv):
            _unlink(csv)
            raise MetadataError(
                f"GSA's run-info table for {cra} has no row for {accession} "
                f"after {GSA_ATTEMPTS} tries",
                "GSA may be answering with a partial table: retry later, or "
                f"check that {accession} is public in {cra}",
            )

        if not ctx.path(f"{cra}.metadata.xlsx").is_file():
            reporter.info(
                f"{green('Note')}: {accession} belongs to {cra}, "
                f"{cra}.metadata.xlsx will also be downloaded"
            )
            get_gsa_xlsx(ctx, cra)

    elif RE_GSA_PROJECT.match(accession):
        if re.match(r"^PRJC[A-Z][0-9]+$|^SAMC[0-9]+$", accession):
            wget_to_file(
                GSA_RUNINFO,
                csv,
                post_data=(
                    f"searchTerm=%26quot%3B{accession}"
                    "%26quot%3BtotalDatas=9999%3BdownLoadCount=9999"
                ),
                user_agent=USER_AGENT_MOZILLA,
                quiet=True,
            )
        else:  # CRA
            wget_to_file(
                GSA_RUNINFO_BY_CRA,
                csv,
                post_data=f"searchTerm={accession}&totalDatas=9999&downLoadCount=9999",
                user_agent=USER_AGENT_MOZILLA,
                quiet=True,
            )

        if not _row2_field1(csv, ","):
            try:
                csv.unlink()
            except FileNotFoundError:
                pass
            raise MetadataError(
                f"{accession} is not a valid Study, Sample, or Experiment accession."
            )

        cra_list = _uniq_adjacent(
            RE_CRA_SCRAPE.findall(csv.read_text(errors="replace"))
        )
        for cra in cra_list:
            if not ctx.path(f"{cra}.metadata.xlsx").is_file():
                if re.match(r"^CRA[0-9]+$", accession):
                    reporter.info(
                        f"{green('Note')}: {cra}.metadata.xlsx will also be downloaded"
                    )
                else:
                    reporter.info(
                        f"{green('Note')}: {accession} belongs to {cra}, "
                        f"{cra}.metadata.xlsx will also be downloaded"
                    )
                get_gsa_xlsx(ctx, cra)
    else:
        raise MetadataError(
            f"{accession} is not a valid Study, Sample, Experiment, or Run accession."
        )
    return csv


def _filter_rows_containing(src: Path, dst: Path, accession: str) -> None:
    """``awk 'NR==1{print} NR>1{if($0~accession) print}'`` — keep header + matches."""
    lines = src.read_text(errors="replace").splitlines(keepends=True)
    out: List[str] = []
    for i, line in enumerate(lines):
        if i == 0:
            out.append(line)
        elif accession in line:
            out.append(line)
    dst.write_text("".join(out))


# --- helpers for the public get_metadata() API ----------------------------------

def parse_tsv(path: Path) -> List[dict]:
    """Parse a ``.metadata.tsv`` into a list of row dicts (header-keyed)."""
    lines = Path(path).read_text(errors="replace").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if not line:
            continue
        values = line.split("\t")
        rows.append(dict(zip(header, values)))
    return rows


def parse_csv(path: Path) -> List[dict]:
    """Parse a GSA ``.metadata.csv`` into a list of row dicts."""
    import csv as _csv

    with open(path, "r", errors="replace", newline="") as fh:
        return list(_csv.DictReader(fh))
