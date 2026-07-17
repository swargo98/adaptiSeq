"""The per-accession process loop — port of iseq's main body (lines ~981-1114).

This ties the modules together in the same order iseq does: metadata first, then
the file-list preview, then per-Run download + integrity + convert, then merge.
It is shared by the CLI and the library API (:func:`adaptiseq.fetch`). It never
prints colour directly — all output goes through ``ctx.reporter`` — and raises
typed exceptions instead of exiting (Section 6).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from . import metadata as meta
from . import resolve, integrity, convert, merge
from ._async import run_sync
from .accession import is_gsa
from .console import green
from .errors import AdaptiSeqError
from .engine import get_engine
from .logs import ensure_success_log, in_success
from .net import file_nonempty
from .options import Options, RunContext


def _check_file(path: Path) -> None:
    """Port of ``CheckFile``: error if missing or empty."""
    if not path.is_file():
        raise AdaptiSeqError(
            f"{path.name} is not exist", f"Please check the accession in {path.name}"
        )
    if path.stat().st_size == 0:
        raise AdaptiSeqError(
            f"{path.name} is empty", f"Please check the content in {path.name}"
        )


def process_accession(ctx: RunContext, accession: str) -> None:
    """Process a single accession end-to-end (GSA branch or SRA/ENA branch)."""
    ctx.accession = accession
    ctx.database = ctx.options.database  # reset per accession (ENA→SRA is per-run)
    if is_gsa(accession):
        _process_gsa(ctx, accession)
    else:
        _process_sra(ctx, accession)
    _finished_banner(ctx, accession)


# ================================ GSA branch ====================================

def _process_gsa(ctx: RunContext, accession: str) -> None:
    reporter = ctx.reporter
    opts = ctx.options
    csv = ctx.metadata_csv(accession)

    if file_nonempty(csv):
        reporter.info(
            f"{green('Note')}: {csv.name} exists, skip downloading metadata "
            f"for {accession}"
        )
    else:
        meta.get_gsa_metadata(ctx, accession)
        _check_file(csv)

    if opts.metadata:
        reporter.info(
            f"{green('Note')}: You choose to skip downloading GSA files (-m used), "
            f"only retrieve the metadata for each accession, see {csv.name}"
        )
        return

    _print_gsa_filelist(ctx, csv)
    reporter.info(
        f"{green('Note')}: Above Run will be downloaded. You can see the details "
        f"in {csv.name}"
    )

    csv_text = csv.read_text(errors="replace")
    csv_lines = csv_text.splitlines()
    crrs = sorted({_csv_field(ln, 1) for ln in csv_lines[1:] if _csv_field(ln, 1)})
    cra_list = resolve._uniq_adjacent(resolve._RE_CRA.findall(csv_text))

    for crr in crrs:
        ensure_success_log(ctx.workdir)
        filenames: List[str] = []
        for ln in csv_lines[1:]:
            if _csv_field(ln, 1) == crr:
                filenames.extend(
                    p for p in _csv_field(ln, 5).split("|") if p
                )
        all_present = all(in_success(ctx.workdir, f) for f in filenames) and filenames
        if all_present:
            reporter.info(
                f"{green('Note')}: {crr} has been downloaded successfully, please "
                "check success.log for details. If you want to download it again, "
                f"please remove it from success.log (sed -i '/{crr}/d' success.log)"
            )
        else:
            resolve.download_gsa(ctx, crr)

    for cra in cra_list:
        md5 = ctx.path(f"{cra}.md5sum.txt")
        if md5.exists():
            md5.unlink()

    if opts.merge is not None:
        reporter.info(
            f"{green('Note')}: All Runs have been downloaded, start to merge them"
        )
        merge.merge_gsa_run(ctx, csv)


# ================================ SRA branch ====================================

def _run_files_present(ctx: RunContext, srr: str) -> bool:
    """True when this run's expected files are already on disk, so Phase B can
    verify them in place instead of re-resolving and re-fetching over the network.

    The gzip/ENA path saves ``SRR[_n].fastq.gz`` parts, so the bare-``SRR`` file
    check only ever matched the ``.sra`` path — leaving batch-prefetched fastq
    runs to pay a full per-accession network resolution they did not need.
    """
    opts = ctx.options
    gzip_mode = opts.gzip and not opts.fastq and ctx.database != "sra"
    if gzip_mode:
        files = integrity._gzip_fastq_files(ctx, srr)
        return bool(files) and all(ctx.path(f).is_file() for f in files)
    return ctx.path(srr).is_file()


def _process_sra(ctx: RunContext, accession: str) -> None:
    reporter = ctx.reporter
    opts = ctx.options
    tsv = ctx.metadata_tsv(accession)

    if file_nonempty(tsv):
        reporter.info(
            f"{green('Note')}: {tsv.name} exists, skip downloading metadata "
            f"for {accession}"
        )
    else:
        meta.get_sra_metadata(ctx, accession)
        _check_file(tsv)

    if opts.metadata:
        reporter.info(
            f"{green('Note')}: You choose to skip downloading SRA files (-m used), "
            f"only retrieve the metadata for each accession, see {tsv.name}"
        )
        return

    _print_sra_filelist(ctx, tsv)
    reporter.info(
        f"{green('Note')}: Above Run will be downloaded. You can see the details "
        f"in {tsv.name}"
    )

    tsv_lines = tsv.read_text(errors="replace").splitlines()
    srrs = [ln.split("\t")[0] for ln in tsv_lines[1:] if ln.split("\t")[0]]

    for srr in srrs:
        ensure_success_log(ctx.workdir)
        if in_success(ctx.workdir, srr):
            reporter.info(
                f"{green('Note')}: {srr} has been downloaded successfully, please "
                "check success.log for details. If you want to download it again, "
                f"please remove it from success.log (sed -i '/{srr}/d' success.log)"
            )
        elif _run_files_present(ctx, srr):
            # Files already on disk — e.g. pre-fetched by the parallel batch phase,
            # or a resumed run. Verify (md5) without re-resolving/re-downloading;
            # check_sra's retry closure still re-downloads if a present file is bad.
            if not opts.skip_md5:
                integrity.check_sra(ctx, srr, lambda s=srr: resolve.download_sra(ctx, s))
            else:
                reporter.info(
                    f"{green('Note')}: Skip md5 check for {srr}, as -k option is used"
                )
        else:
            resolve.download_sra(ctx, srr)
            if not opts.skip_md5:
                integrity.check_sra(ctx, srr, lambda s=srr: resolve.download_sra(ctx, s))
            else:
                reporter.info(
                    f"{green('Note')}: Skip md5 check for {srr}, as -k option is used"
                )

        convert.maybe_convert(ctx, srr)

    if opts.merge is not None:
        reporter.info(
            f"{green('Note')}: All Runs have been downloaded, start to merge them"
        )
        merge.merge_sra_run(ctx, tsv)


# ================================ file-list previews ============================

def _csv_field(line: str, n: int) -> str:
    parts = line.split(",")
    return parts[n - 1] if len(parts) >= n else ""


def _to_float(value: str) -> float:
    """awk-style numeric coercion (non-numeric → 0)."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _print_gsa_filelist(ctx: RunContext, csv: Path) -> None:
    """Port of the GSA awk preview (field 5 = filenames, field 6 = sizes)."""
    lines = csv.read_text(errors="replace").splitlines()
    for ln in lines[1:]:
        filenames = _csv_field(ln, 5).split("|")
        sizes = _csv_field(ln, 6).split("|")
        out = ""
        for i, fname in enumerate(filenames):
            size = _to_float(sizes[i]) / (1024 * 1024 * 1024) if i < len(sizes) else 0.0
            out += f"      {fname} {size:.2f}G \t "
        ctx.reporter.info(out)


def _print_sra_filelist(ctx: RunContext, tsv: Path) -> None:
    """Port of the SRA awk preview, including the gzip vs sra column math."""
    opts = ctx.options
    text = tsv.read_text(errors="replace")
    lines = text.splitlines()
    fastq_link_present = bool(
        resolve._RE_FASTQLINK.search(text) and ".fastq.gz" in text
    )
    if opts.gzip and fastq_link_present and not opts.fastq:
        for ln in lines[1:]:
            cols = ln.split("\t")
            filenames = (cols[29] if len(cols) > 29 else "").split(";")
            sizes = (cols[27] if len(cols) > 27 else "").split(";")
            out = ""
            for i, fn in enumerate(filenames):
                ext = fn.split("/")[-1]
                size = _to_float(sizes[i]) / (1024 ** 3) if i < len(sizes) else 0.0
                out += f"      {ext} {size:.2f}G \t "
            ctx.reporter.info(out)
    else:
        for ln in lines[1:]:
            cols = ln.split("\t")
            col1 = cols[0] if cols else ""
            size7 = _to_float(cols[6]) / 1024 if len(cols) > 6 else 0.0
            size8 = _to_float(cols[7]) / 1024 if len(cols) > 7 else 0.0
            size39 = _to_float(cols[38]) / (1024 ** 3) if len(cols) > 38 else 0.0
            if size7 == 0 and size8 != 0:
                if "lite" in ln:
                    ctx.reporter.info(f"      {col1}\t>{size39:.2f}G")
                else:
                    ctx.reporter.info(f"      {col1}\t{size39:.2f}G")
            else:
                ctx.reporter.info(f"      {col1}\t{size8:.2f}G")


def _finished_banner(ctx: RunContext, accession: str) -> None:
    cols = shutil.get_terminal_size((80, 24)).columns
    total = (cols - len(accession) - 22) // 2
    eq = "=" * total if total > 0 else "="
    ctx.reporter.info(f"{eq}{accession} download finished{eq}")


# ================================ batch runner ==================================

def run(
    accessions: List[str],
    options: Options,
    reporter=None,
    workdir: Path = None,
) -> RunContext:
    """Run the full pipeline over a list of accessions. Returns the RunContext
    (``ctx.failed`` indicates whether any Run ultimately failed).

    Part 3: when the segmented engine is in use and we are actually downloading
    (not ``-m``), the SRA/ENA download is routed through the adaptive batch pool
    (parallel resolution + worker pool + gradient controller). Integrity,
    conversion, merge, and logs are then applied by the unchanged per-accession
    Part 1 loop over the already-downloaded files — so adaptivity changes only
    scheduling, never which bytes are written. GSA accessions and the classic
    engine use the sequential path unchanged.
    """
    from .console import NullReporter

    workdir = Path(workdir) if workdir is not None else Path.cwd()
    ctx = RunContext(
        options=options,
        reporter=reporter or NullReporter(),
        workdir=workdir,
    )
    ctx.engine = get_engine(options, workdir, ctx.reporter)

    if options.aspera and not options.metadata:
        # Part 5: parallel adaptive Aspera for ENA/SRA (GSA aspera, with its
        # Huawei-wins rule, stays on the sequential path).
        sra_accs = [a for a in accessions if not is_gsa(a)]
        if sra_accs:
            _aspera_download_phase(ctx, sra_accs)
    elif options.engine == "segmented" and not options.metadata:
        sra_accs = [a for a in accessions if not is_gsa(a)]
        if sra_accs:
            _batch_download_phase(ctx, sra_accs)

    for accession in accessions:
        ctx.retry_count = 1
        process_accession(ctx, accession)
    return ctx


def _strip_scheme(url: str) -> str:
    for s in ("https://", "http://", "ftp://"):
        if url.startswith(s):
            return url[len(s):]
    return url


def _worker_cap_label(jobs: int, n_tasks: int) -> str:
    """Describe the worker pool the run will actually build, since -j is only a
    ceiling and the pool is capped at one worker per file."""
    effective = min(jobs, n_tasks)
    if effective == jobs:
        return f"{effective} worker(s)"
    return f"{effective} worker(s) (configured max {jobs})"


def _aspera_download_phase(ctx: RunContext, sra_accs: List[str]) -> None:
    """Phase A for ``-a``: parallel-resolve and download ENA/SRA files with the
    adaptive Aspera pool (additive-increase + efficiency hysteresis). Phase B (the
    per-accession loop) then verifies/converts/merges; ``ascp`` resume makes its
    aspera re-touch of completed files a near no-op."""
    import asyncio

    from .aspera import AsperaBatchDownloader
    from .batch import resolve_all

    opts = ctx.options
    reporter = ctx.reporter
    tasks, unresolved = resolve_all(sra_accs, opts, ctx.workdir, meta_jobs=opts.meta_jobs)
    for acc in unresolved:
        reporter.error(f"{green('Note')}: could not resolve {acc} for aspera")
    # Convert resolved URLs into ascp tasks (host/path form + db).
    for t in tasks:
        t.url = _strip_scheme(t.url)
        t.aspera_db = "ENA"
    if not tasks:
        return
    reporter.info(
        f"{green('Note')}: Aspera batch downloading {len(tasks)} file(s) with up to "
        f"{_worker_cap_label(opts.jobs, len(tasks))} "
        f"({'adaptive hysteresis' if opts.adaptive else 'fixed'} concurrency)"
    )

    def download_fn(task):
        return ctx.engine.fetch_aspera(task.url, task.aspera_db or "ENA")

    bd = AsperaBatchDownloader(download_fn, opts, ctx.workdir, reporter)
    run_sync(bd.run(tasks))
    controller = getattr(bd, "_controller", None)
    if controller is not None and controller.trajectory:
        traj = ", ".join(f"{w}w@{t:.0f}Mbps(eff{e:.2f})"
                         for w, t, e in controller.trajectory)
        reporter.info(f"{green('Note')}: aspera worker trajectory: {traj}")


def _batch_download_phase(ctx: RunContext, sra_accs: List[str]) -> None:
    """Phase A: parallel-resolve SRA/ENA accessions and adaptively batch-download
    their files. Phase B (integrity/convert/merge/logs) is the normal per-accession
    loop, which finds the files already present."""
    import asyncio

    from .batch import BatchDownloader, resolve_all

    opts = ctx.options
    reporter = ctx.reporter
    tasks, unresolved = resolve_all(
        sra_accs, opts, ctx.workdir, meta_jobs=opts.meta_jobs
    )
    for acc in unresolved:
        reporter.error(
            f"{green('Note')}: could not resolve {acc}; it will be retried "
            "sequentially"
        )
    if not tasks:
        return
    reporter.info(
        f"{green('Note')}: batch downloading {len(tasks)} file(s) across "
        f"{len(sra_accs)} accession(s) with up to "
        f"{_worker_cap_label(opts.jobs, len(tasks))} "
        f"({'adaptive' if opts.adaptive else 'fixed'} concurrency)"
    )
    bd = BatchDownloader(ctx.engine, opts, ctx.workdir, reporter)
    run_sync(bd.run(tasks))
    controller = getattr(bd, "_controller", None)
    if controller is not None:
        summary = controller.summary()
        if summary:
            reporter.info(f"{green('Note')}: adaptive worker summary: {summary}")
