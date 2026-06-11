"""Metadata fetching for ENA / SRA-fallback / GSA — faithful port.

Filenames, endpoints, POST bodies, user-agents, and the comma→tab conversion are
reproduced exactly (Section 3.2). All bytes are pulled by ``wget`` (see
:mod:`adaptiseq.net`) so the saved files are byte-identical to iseq's.

Files produced (same as iseq):
* ``${accession}.metadata.tsv``  — ENA filereport, or SRA runinfo (comma→tab).
* ``${accession}.metadata.csv``  — GSA getRunInfo / getRunInfoByCra.
* ``${CRA}.metadata.xlsx``       — GSA exportExcelFile (3 sheets).
"""

from __future__ import annotations

import re
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

def get_sra_metadata(ctx: RunContext, accession: str) -> Path:
    """Port of ``getSRAMetadata``.

    Tries ENA first; on an empty result flips ``ctx.database`` to ``sra`` and
    falls back to the NCBI eutils + sra-db-be runinfo (comma→tab). Raises
    :class:`MetadataError` if both are empty.
    """
    reporter = ctx.reporter
    query = validate_query(accession, reporter)

    tsv = ctx.metadata_tsv(accession)
    wget_to_file(
        ENA_URL.format(query=query, fields=ENA_FIELDS),
        tsv,
        cont=True,
        quiet=True,
    )

    if not _row2_field1(tsv, "\t"):
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
    """Port of ``getGSAxlsx``."""
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
    """Port of ``getGSAMetadata``.

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
        wget_to_file(
            GSA_RUNINFO_BY_CRA,
            tmp,
            post_data=f"searchTerm={cra}&totalDatas=9999&downLoadCount=9999",
            user_agent=USER_AGENT_MOZILLA,
            quiet=True,
        )
        _filter_rows_containing(tmp, csv, accession)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

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
