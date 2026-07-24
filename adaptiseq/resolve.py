"""Per-run URL resolution — faithful ports of ``downloadSRA`` / ``downloadGSA``.

This is where the host/path decisions live (ENA vol path vs ``srapath``, GSA
Huawei Cloud vs ftp, ``.fastq.gz`` vs ``.sra``, and the ``-g``/``-d``/``-a``/``-r``
interactions). Every byte is fetched through the engine seam
(:meth:`ClassicEngine.fetch` / :meth:`ClassicEngine.fetch_aspera`), never inline.
"""

from __future__ import annotations

import re
import subprocess
from typing import List, Optional

from .accession import _uniq_adjacent
from .console import bright_yellow, green
from .errors import DownloadError, PreflightError
from .integrity import verify_gsa
from .logs import in_success, mark_fail, mark_success
from .net import USER_AGENT_MOZILLA, wget_capture, wget_spider_size
from .options import RunContext

# grep patterns from downloadSRA (dots left as "." to mirror grep exactly).
_RE_SRALINK = re.compile(r"ftp.sra.ebi.ac.uk/vol[0-9]/[sde]rr")
_RE_FASTQLINK = re.compile(r"ftp.sra.ebi.ac.uk/vol[0-9]/fastq")
# GSA browse link scrape (grep -oE '(https|ftp)://[^"]*\.(gz|bam|tar|bz2)').
_RE_GSA_LINK = re.compile(r'(?:https|ftp)://[^"]*\.(?:gz|bam|tar|bz2)')
_RE_CRA = re.compile(r"CRA[0-9]+")


# --- token helpers --------------------------------------------------------------

def _lines_with(text: str, token: str) -> List[str]:
    return [ln for ln in text.splitlines() if token in ln]


def _tokens(lines: List[str]) -> List[str]:
    out: List[str] = []
    for ln in lines:
        out.extend(ln.split("\t"))
    return out


def _extract(tokens: List[str], pattern: "re.Pattern", exclude: Optional[str] = None):
    out = [t for t in tokens if pattern.search(t) and (exclude is None or exclude not in t)]
    return _uniq_adjacent(out)


def _srapath(srr: str) -> str:
    # srapath is needed to resolve the SRA-fallback URL (any non-direct-ENA Run).
    # If it is missing, raise the same clean "install sra-tools" guidance the
    # upfront preflight would, rather than returning "" — which the caller would
    # otherwise mislabel as "not available in all databases" (a confusing lie when
    # the file may exist and only the tool is absent). Needs-based preflight does
    # not require srapath for pure-ENA fastq.gz runs, so this is the right place
    # to surface the dependency: only when the SRA path is actually taken.
    from .preflight import check_software

    check_software("srapath", "sra-tools>=2.11.0")
    out = subprocess.run(["srapath", srr], capture_output=True, text=True).stdout
    return out.strip()


# ================================ downloadSRA ===================================

def download_sra(ctx: RunContext, srr: str) -> None:
    """``downloadSRA``: resolve and fetch one Run."""
    opts = ctx.options
    reporter = ctx.reporter
    tsv_text = ctx.metadata_tsv().read_text(errors="replace")

    matched = _lines_with(tsv_text, srr)
    toks = _tokens(matched)
    sra_links = _extract(toks, _RE_SRALINK, exclude="lite")
    fastq_links = _extract(toks, _RE_FASTQLINK)
    sra_link = sra_links[0] if sra_links else ""
    fastq_link = fastq_links[0] if fastq_links else ""

    gzip_direct = (
        opts.gzip and fastq_link and ctx.database != "sra" and not opts.fastq
    )

    if gzip_direct:
        reporter.info(
            f"{green('Note')}: -g used, download FASTQ files in gzip format directly"
        )
        layouts = ["paired" if "PAIRED" in ln else "single" for ln in matched]
        layout = (_uniq_adjacent(layouts) or ["single"])[0]
        parts = fastq_link.split(";")
        link_num = len(parts)

        if layout == "single" and link_num == 1:
            link = _first_containing(parts, "fastq.gz")
            _download_ena_fastq(ctx, link)
        else:
            if layout == "single":
                reporter.info(
                    f"{bright_yellow('Note')}: {srr} is single-end data, "
                    "but has multiple links"
                )
            if link_num == 2:
                link1 = _first_containing(parts, "_1.fastq.gz")
                link2 = _first_containing(parts, "_2.fastq.gz")
                _download_ena_fastq(ctx, link1)
                _download_ena_fastq(ctx, link2)
            elif link_num == 1:
                reporter.info(
                    f"{bright_yellow('Note')}: {srr} is paired-end data, "
                    "but has only one link"
                )
                link = _first_containing(parts, ".fastq.gz")
                _download_ena_fastq(ctx, link)
            else:
                # 3+ links (e.g. orphan/barcode reads + _1 + _2). iseq mishandles
                # this (greps all and feeds wget a multiline URL); adaptiSeq fetches
                # every .fastq.gz part so the md5 check over all files passes.
                reporter.info(
                    f"{bright_yellow('Note')}: {srr} has {link_num} fastq links; "
                    "downloading all .fastq.gz parts"
                )
                for link in [p for p in parts if ".fastq.gz" in p]:
                    _download_ena_fastq(ctx, link)
        return

    # --- SRA file path ---
    forced_sra = ctx.database == "sra"
    if forced_sra or not sra_link:
        if ctx.database == "ena":
            reporter.info(
                f"{bright_yellow('Note')}: The SRA file of {srr} is not available "
                "in the ENA database, switch to the SRA database"
            )
        if opts.gzip and not opts.fastq and ctx.database != "sra":
            reporter.info(
                f"{bright_yellow('Note')}: {srr} FASTQ file is also not available "
                "in the ENA database, switch to download SRA file"
            )
        if opts.gzip and ctx.database == "sra":
            reporter.info(
                f"{green('Note')}: SRA database used, will download SRA file and "
                "convert to FASTQ file in gzip format"
            )
        if opts.aspera:
            reporter.info(
                f"{bright_yellow('Note')}: SRA database does not support Aspera "
                "download, switch to download SRA file by https"
            )
        link = _srapath(srr)
        if not link:
            raise DownloadError(
                f"The sequencing file of {srr} is not available in all databases"
            )
        size = wget_spider_size(link, ftp=False)
        reporter.info(f"File size: {size}\tDatabase: SRA\tMode: https")
        ctx.engine.fetch(link, srr)
    else:
        if opts.gzip and not opts.fastq:
            reporter.info(
                f"{bright_yellow('Note')}: {srr} FASTQ file is not available in "
                "the ENA database, switch to download SRA file"
            )
        if opts.aspera:
            size = wget_spider_size(f"ftp://{sra_link}", ftp=True)
            reporter.info(f"File size: {size}\tDatabase: ENA\tMode: Aspera")
            ctx.engine.fetch_aspera(sra_link, "ENA")
        elif opts.protocol == "https":
            size = wget_spider_size(f"https://{sra_link}", ftp=False)
            reporter.info(f"File size: {size}\tDatabase: ENA\tMode: https")
            ctx.engine.fetch(f"https://{sra_link}", srr)
        else:
            size = wget_spider_size(f"ftp://{sra_link}", ftp=True)
            reporter.info(f"File size: {size}\tDatabase: ENA\tMode: ftp")
            ctx.engine.fetch(f"ftp://{sra_link}", srr)


def _first_containing(parts: List[str], needle: str) -> str:
    for p in parts:
        if needle in p:
            return p
    return ""


# --- side-effect-free URL resolution (for the public `resolve()` API) -----------

def resolve_sra_urls(ctx: RunContext, srr: str) -> List[str]:
    """Return the URL(s) ``download_sra`` would fetch, without downloading.

    Mirrors the same branch selection (gzip fastq.gz vs ENA .sra vs srapath) and
    applies the protocol scheme, so callers see exactly what iseq would resolve.
    """
    opts = ctx.options
    tsv_text = ctx.metadata_tsv().read_text(errors="replace")
    matched = _lines_with(tsv_text, srr)
    toks = _tokens(matched)
    sra_links = _extract(toks, _RE_SRALINK, exclude="lite")
    fastq_links = _extract(toks, _RE_FASTQLINK)
    sra_link = sra_links[0] if sra_links else ""
    fastq_link = fastq_links[0] if fastq_links else ""

    scheme = "https://" if opts.protocol == "https" else "ftp://"
    gzip_direct = opts.gzip and fastq_link and ctx.database != "sra" and not opts.fastq

    if gzip_direct:
        layouts = ["paired" if "PAIRED" in ln else "single" for ln in matched]
        layout = (_uniq_adjacent(layouts) or ["single"])[0]
        parts = fastq_link.split(";")
        if layout == "single" and len(parts) == 1:
            return [scheme + _first_containing(parts, "fastq.gz")]
        if len(parts) == 2:
            return [
                scheme + _first_containing(parts, "_1.fastq.gz"),
                scheme + _first_containing(parts, "_2.fastq.gz"),
            ]
        if len(parts) == 1:
            return [scheme + _first_containing(parts, ".fastq.gz")]
        # 3+ links: fetch every .fastq.gz part (orphan/barcode + _1 + _2).
        return [scheme + p for p in parts if ".fastq.gz" in p]

    if ctx.database == "sra" or not sra_link:
        link = _srapath(srr)
        return [link] if link else []
    return [scheme + sra_link]


def resolve_gsa_urls(ctx: RunContext, crr: str) -> List[str]:
    """Return the GSA URL(s) ``download_gsa`` would fetch (Huawei > ftp), no I/O
    other than the read-only browse-page lookup."""
    opts = ctx.options
    csv_text = ctx.metadata_csv().read_text(errors="replace")
    cra_matches = _uniq_adjacent(
        [m for ln in _lines_with(csv_text, crr) for m in _RE_CRA.findall(ln)]
    )
    cra = cra_matches[0] if cra_matches else ""
    html = wget_capture(
        GSA_BROWSE_URL.format(cra=cra, crr=crr), user_agent=USER_AGENT_MOZILLA
    )
    all_links = sorted(set(_RE_GSA_LINK.findall(html)))
    huawei = [l for l in all_links if "huaweicloud" in l]
    ftp = [l for l in all_links if "ftp://download.big.ac.cn" in l]
    if huawei:
        return huawei
    return ftp


def _download_ena_fastq(ctx: RunContext, link: str) -> None:
    """One ENA ``.fastq.gz`` link: aspera / https / ftp per options (size + fetch)."""
    opts = ctx.options
    reporter = ctx.reporter
    save_name = link.rsplit("/", 1)[-1]
    if opts.aspera:
        size = wget_spider_size(f"ftp://{link}", ftp=True)
        reporter.info(f"File size: {size}\tDatabase: ENA\tMode: Aspera")
        ctx.engine.fetch_aspera(link, "ENA")
    elif opts.protocol == "https":
        size = wget_spider_size(f"https://{link}", ftp=False)
        reporter.info(f"File size: {size}\tDatabase: ENA\tMode: https")
        ctx.engine.fetch(f"https://{link}", save_name)
    else:
        size = wget_spider_size(f"ftp://{link}", ftp=True)
        reporter.info(f"File size: {size}\tDatabase: ENA\tMode: ftp")
        ctx.engine.fetch(f"ftp://{link}", save_name)


# ================================ downloadGSA ===================================

GSA_BROWSE_URL = "https://ngdc.cncb.ac.cn/gsa/browse/{cra}/{crr}"


def download_gsa(ctx: RunContext, crr: str) -> None:
    """``downloadGSA``: resolve and fetch all files of one Run."""
    reporter = ctx.reporter
    opts = ctx.options
    csv_text = ctx.metadata_csv().read_text(errors="replace")

    cra_matches = _uniq_adjacent(
        [m for ln in _lines_with(csv_text, crr) for m in _RE_CRA.findall(ln)]
    )
    cra = cra_matches[0] if cra_matches else ""

    html = wget_capture(
        GSA_BROWSE_URL.format(cra=cra, crr=crr), user_agent=USER_AGENT_MOZILLA
    )
    all_links = sorted(set(_RE_GSA_LINK.findall(html)))
    https_links = [l for l in all_links if "https://download.cncb.ac.cn" in l]
    ftp_links = [l for l in all_links if "ftp://download.big.ac.cn" in l]
    huawei_links = [l for l in all_links if "huaweicloud" in l]

    if huawei_links:
        if opts.aspera:
            reporter.info(
                f"{green('Note')}: HUAWEI Cloud is available, which is faster than "
                "Aspera, so HUAWEI Cloud will be used first, even if -a option is used"
            )
        for link in huawei_links:
            _gsa_one(ctx, link, crr, cra, mode="HUAWEI Cloud", ftp=False, aspera=False)
    elif opts.aspera:
        for link in ftp_links:
            _gsa_one(ctx, link, crr, cra, mode="Aspera", ftp=True, aspera=True)
    else:
        for link in ftp_links:
            _gsa_one(ctx, link, crr, cra, mode="ftp", ftp=True, aspera=False)


def _gsa_one(ctx, link, crr, cra, *, mode, ftp, aspera):
    """Download one GSA link with the per-file md5 retry loop (``checkGSA``)."""
    from .console import bright_green, bright_red, bright_yellow as _by, green as _g
    from .errors import AdaptiSeqError

    reporter = ctx.reporter
    opts = ctx.options
    save_name = link.rsplit("/", 1)[-1]

    if in_success(ctx.workdir, save_name):
        reporter.info(
            f"{_g('Note')}: {save_name} has been downloaded successfully, please "
            "check success.log for details. If you want to download it again, "
            f"please remove it from success.log (sed -i '/{save_name}/d' success.log)"
        )
        return

    count = 1
    while True:
        size = wget_spider_size(link, ftp=ftp, user_agent=USER_AGENT_MOZILLA)
        reporter.info(f"File size: {size}\tDatabase: GSA\tMode: {mode}")
        if aspera:
            ctx.engine.fetch_aspera(link, "GSA")
        else:
            ctx.engine.fetch(link, save_name)

        if opts.skip_md5:
            reporter.info(
                f"{_g('Note')}: Skip md5 check for {save_name}, as -k option is used"
            )
            return

        result = verify_gsa(ctx, save_name, cra)
        if result is None:
            # md5 unavailable / empty list: CheckFile then record success.
            fpath = ctx.path(save_name)
            if not fpath.is_file():
                raise AdaptiSeqError(
                    f"{save_name} is not exist",
                    f"Please check the accession in {save_name}",
                )
            if fpath.stat().st_size == 0:
                raise AdaptiSeqError(
                    f"{save_name} is empty",
                    f"Please check the content in {save_name}",
                )
            reporter.info(
                f"{_g('Note')}: Skip md5 check for {save_name}, as md5sum command "
                f"is not available or {cra}.md5sum.txt is empty"
            )
            reporter.info(
                bright_green(
                    f"{save_name} download successful, save {save_name} in success.log"
                )
            )
            mark_success(ctx.workdir, save_name)
            return
        if result is True:
            reporter.info(
                bright_green(
                    f"{save_name} download and md5 check successful, "
                    f"save {save_name} in success.log"
                )
            )
            mark_success(ctx.workdir, save_name)
            return
        # mismatch
        if count <= 1:
            reporter.info(
                f"{_by('Note')}: {save_name} validate failed, retry {count} times"
            )
            count += 1
            continue
        elif count <= 2:
            reporter.info(
                f"{_by('Note')}: {save_name} validate failed, remove the file and "
                f"retry {count} times"
            )
            if ctx.path(save_name).is_file():
                ctx.path(save_name).unlink()
            count += 1
            continue
        else:
            reporter.info(
                bright_red(
                    f"{save_name} md5 check failed after trying {count} times, "
                    f"save {save_name} in fail.log"
                )
            )
            mark_fail(ctx.workdir, save_name)
            ctx.failed = True
            return
