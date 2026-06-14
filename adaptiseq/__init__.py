"""adaptiSeq — a tested, importable Python port of the iseq sequencing downloader.

Part 1 is a behaviour-preserving port on the classic ``wget``/``axel`` engine.
The segmented and adaptive engines arrive in Parts 2 and 3.

Public library API (Section 6) — none of these print colour codes or call
``sys.exit``; they return values and raise the typed exceptions in
:mod:`adaptiseq.errors`::

    from adaptiseq import fetch, resolve, get_metadata

    records = get_metadata("SRR7706354")                 # parsed metadata rows
    urls    = resolve("SRR7706354", database="ena")      # resolved download URLs
    result  = fetch("SRR7706354", outdir="data/", gzip=True)   # download + verify
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import core
from . import metadata as _meta
from . import resolve as _resolve
from .accession import is_gsa
from .console import NullReporter, Reporter
from .engine import get_engine
from .errors import (
    AdaptiSeqError,
    DownloadError,
    EngineUnavailableError,
    IntegrityError,
    InvalidAccessionError,
    MergeError,
    MetadataError,
    PreflightError,
)
from .logs import FAIL_LOG, SUCCESS_LOG
from .options import Options, RunContext, resolve_output_dir

__version__ = "0.1.0"
__all__ = [
    "fetch",
    "resolve",
    "get_metadata",
    "FetchResult",
    "Options",
    "AdaptiSeqError",
    "InvalidAccessionError",
    "MetadataError",
    "DownloadError",
    "IntegrityError",
    "MergeError",
    "PreflightError",
    "EngineUnavailableError",
    "__version__",
]


@dataclass
class FetchResult:
    """Outcome of a :func:`fetch` call."""

    accession: str
    outdir: Path
    failed: bool
    success_ids: List[str] = field(default_factory=list)
    fail_ids: List[str] = field(default_factory=list)


def _log_ids(path: Path) -> List[str]:
    if not path.exists():
        return []
    ids = []
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1]:
            ids.append(parts[1])
    return ids


def get_metadata(
    accession: str,
    *,
    database: str = "auto",
    outdir: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Fetch and parse metadata for ``accession``.

    Returns a list of row dicts (TSV columns for ENA/SRA, CSV columns for GSA).
    Writes the same ``.metadata.*`` files iseq writes; when ``outdir`` is omitted
    a temporary directory is used and cleaned up. Raises :class:`MetadataError`
    / :class:`InvalidAccessionError` on failure.
    """
    if outdir is not None:
        workdir = resolve_output_dir(outdir)
        return _get_metadata_in(accession, database, workdir)
    with tempfile.TemporaryDirectory(prefix="adaptiseq-meta-") as tmp:
        return _get_metadata_in(accession, database, Path(tmp))


def _get_metadata_in(accession: str, database: str, workdir: Path) -> List[Dict]:
    ctx = RunContext(
        options=Options(database=database, metadata=True),
        reporter=NullReporter(),
        workdir=workdir,
    )
    if is_gsa(accession):
        path = _meta.get_gsa_metadata(ctx, accession)
        return _meta.parse_csv(path)
    path = _meta.get_sra_metadata(ctx, accession)
    return _meta.parse_tsv(path)


def resolve(
    accession: str,
    *,
    database: str = "auto",
    gzip: bool = False,
    fastq: bool = False,
    aspera: bool = False,
    protocol: str = "ftp",
    outdir: Optional[str] = None,
) -> List[str]:
    """Resolve the download URL(s) for every Run under ``accession``.

    Fetches metadata (same as iseq), then returns the URLs the classic engine
    would fetch — without downloading. Raises the same typed exceptions as
    :func:`get_metadata`.
    """
    opts = Options(
        database=database, gzip=gzip, fastq=fastq, aspera=aspera, protocol=protocol
    )
    if outdir is not None:
        workdir = resolve_output_dir(outdir)
        return _resolve_in(accession, opts, workdir)
    with tempfile.TemporaryDirectory(prefix="adaptiseq-resolve-") as tmp:
        return _resolve_in(accession, opts, Path(tmp))


def _resolve_in(accession: str, opts: Options, workdir: Path) -> List[str]:
    ctx = RunContext(options=opts, reporter=NullReporter(), workdir=workdir)
    ctx.engine = get_engine(opts, workdir, ctx.reporter)
    ctx.accession = accession
    urls: List[str] = []
    if is_gsa(accession):
        csv = _meta.get_gsa_metadata(ctx, accession)
        lines = csv.read_text(errors="replace").splitlines()
        crrs = sorted({ln.split(",")[0] for ln in lines[1:] if ln.split(",")[0]})
        for crr in crrs:
            urls.extend(_resolve.resolve_gsa_urls(ctx, crr))
    else:
        tsv = _meta.get_sra_metadata(ctx, accession)
        lines = tsv.read_text(errors="replace").splitlines()
        for ln in lines[1:]:
            run = ln.split("\t")[0]
            if run:
                urls.extend(_resolve.resolve_sra_urls(ctx, run))
    return [u for u in urls if u]


def fetch(
    accession: str,
    *,
    outdir: Optional[str] = None,
    metadata: bool = False,
    gzip: bool = False,
    fastq: bool = False,
    threads: int = 8,
    merge: Optional[str] = None,
    database: str = "auto",
    parallel: int = 0,
    aspera: bool = False,
    speed: int = 1000,
    skip_md5: bool = False,
    protocol: str = "auto",
    quiet: bool = True,
    engine: str = "segmented",
    segment_size_mb: int = 512,
    max_segments: int = 8,
    max_conns_per_host: int = 8,
    jobs: int = 20,
    adaptive: bool = True,
    probe_window: int = 5,
    cc_penalty: float = 1.01,
    meta_jobs: int = 3,
    aspera_efficiency: float = 0.70,
    reporter: Optional[Reporter] = None,
) -> FetchResult:
    """Download and verify ``accession``.

    Part 2 default engine is ``segmented`` (resumable HTTP(S)/FTP); pass
    ``engine='classic'`` for the Part 1 ``wget``/``axel`` path. Thin wrapper over
    :func:`adaptiseq.core.run`. Returns a :class:`FetchResult` summarising
    success/fail IDs read back from ``success.log``/``fail.log``. Does not print
    colour or exit; pass a :class:`Reporter` to capture progress.
    """
    if engine not in ("classic", "segmented"):
        raise EngineUnavailableError(f"Unknown engine: {engine}")

    options = Options(
        metadata=metadata,
        gzip=gzip,
        fastq=fastq,
        threads=threads,
        merge=merge,
        database=database,
        parallel=parallel,
        aspera=aspera,
        speed=speed,
        skip_md5=skip_md5,
        protocol=protocol,
        quiet=quiet,
        output=outdir,
        engine=engine,
        segment_size=segment_size_mb * 1024 * 1024,
        max_segments=max_segments,
        max_conns_per_host=max_conns_per_host,
        jobs=jobs,
        adaptive=adaptive,
        probe_window=probe_window,
        cc_penalty=cc_penalty,
        meta_jobs=meta_jobs,
        aspera_efficiency=aspera_efficiency,
    )
    workdir = resolve_output_dir(outdir)
    ctx = core.run(
        [accession], options, reporter=reporter or NullReporter(), workdir=workdir
    )
    return FetchResult(
        accession=accession,
        outdir=workdir,
        failed=ctx.failed,
        success_ids=_log_ids(workdir / SUCCESS_LOG),
        fail_ids=_log_ids(workdir / FAIL_LOG),
    )
