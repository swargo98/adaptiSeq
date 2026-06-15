"""SRA→FASTQ conversion and compression — ``fasterq-dump`` + ``pigz`` wrappers.

Faithful port of the conversion block in the SRA branch of iseq's process loop
(lines ~1076-1096). External tools are shelled out, never reimplemented
(Section 3.6).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .console import green
from .options import RunContext

_RE_SRX = re.compile(r"[EDS]RX[0-9]+")


def _experiment_for(ctx: RunContext, srr: str) -> str:
    """``grep $SRR tsv | grep -oe "[EDS]RX[0-9]+" | sort | uniq`` (first value)."""
    tsv = ctx.metadata_tsv()
    matches = []
    for line in tsv.read_text(errors="replace").splitlines():
        if srr in line:
            matches.extend(_RE_SRX.findall(line))
    uniq = sorted(set(matches))
    return uniq[0] if uniq else ""


def _has_any_fastq_gz(ctx: RunContext, srr: str, srx: str) -> bool:
    for stem in (srr, srx):
        for suffix in ("_1.fastq.gz", "_2.fastq.gz", ".fastq.gz"):
            if ctx.path(f"{stem}{suffix}").is_file():
                return True
    return False


def maybe_convert(ctx: RunContext, srr: str) -> None:
    """Convert ``SRR`` to FASTQ (and compress if ``-g``), matching iseq's guard.

    Runs only when ``-q``/``-e``/``-g`` is set, the ``.sra`` file exists, and no
    ``.fastq.gz`` already exists for the Run or its Experiment.
    """
    opts = ctx.options
    reporter = ctx.reporter
    trigger = opts.fastq or opts.merge is not None or opts.gzip
    sra_file = ctx.path(srr)
    if not (trigger and sra_file.is_file()):
        return
    srx = _experiment_for(ctx, srr)
    if _has_any_fastq_gz(ctx, srr, srx):
        return

    # We are about to actually convert a .sra file. fasterq-dump is only needed
    # here — a -g run that got its bytes as direct ENA .fastq.gz never reaches
    # this point (no .sra file), so needs-based preflight does not require it
    # upfront. Surface a clean "install sra-tools" message instead of letting the
    # subprocess raise a bare FileNotFoundError.
    from .preflight import check_software

    check_software("fasterq-dump", "sra-tools")

    reporter.info(
        f"{green('Note')}: Converting {srr} to fastq files using {opts.threads} threads"
    )
    srr_path = str(Path(os.path.realpath(str(sra_file))).parent)
    cmd = [
        "fasterq-dump", "-p", "-S", "--include-technical",
        "-e", str(opts.threads), "-O", srr_path, f"{srr_path}/{srr}",
    ]
    if opts.quiet:
        subprocess.run(
            cmd, cwd=str(ctx.workdir),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(cmd, cwd=str(ctx.workdir))

    # rm -rf fasterq.tmp*
    for tmp in ctx.workdir.glob("fasterq.tmp*"):
        if tmp.is_dir():
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)
        else:
            tmp.unlink()

    if opts.gzip and sra_file.is_file():
        for fastq in sorted(ctx.workdir.glob(f"{srr}*fastq")):
            reporter.info(
                f"{green('Note')}: Compressing {fastq.name} to {fastq.name}.gz "
                f"using {opts.threads} threads, may take a while"
            )
            subprocess.run(
                ["pigz", "-p", str(opts.threads), fastq.name], cwd=str(ctx.workdir)
            )
