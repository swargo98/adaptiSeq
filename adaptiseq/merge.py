"""FASTQ merging — faithful ports of ``mergeSRArun`` / ``mergeGSArun``.

Reproduces the symlink/rename/concatenate logic (Section 3.7), including the
single-run rename case and the GSA differing-prefix case. Like iseq, merging
creates symlinks for the single-run case (so original Runs are not re-downloaded)
and concatenates in run order for the multi-run case.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

from .console import bright_yellow, green
from .errors import MergeError
from .options import RunContext

_RE_SRX = re.compile(r"[EDS]RX[0-9]+")
_RE_SAM = re.compile(r"SAM[EDN][A-Z]*[0-9]+")
_RE_PRJ = re.compile(r"PRJ[EDN][A-Z][0-9]+")
_RE_CRX = re.compile(r"CRX[0-9]+")
_RE_SAMC = re.compile(r"SAMC[0-9]+")
_RE_PRJC = re.compile(r"PRJC[A-Z][0-9]+")
_RE_FQGZ = re.compile(r"[fastq|fq].gz")  # verbatim sloppy class from the Bash


def _sorted_uniq(values: List[str]) -> List[str]:
    return sorted(set(values))


def _ln_s(ctx: RunContext, src: str, dst: str) -> None:
    """``ln -s src dst`` in the working directory (no-op if dst already exists)."""
    dst_path = ctx.path(dst)
    if dst_path.exists() or dst_path.is_symlink():
        return
    os.symlink(src, dst_path)


def _cat(ctx: RunContext, inputs: List[str], output: str) -> None:
    """``cat inputs > output`` (binary concatenation in order)."""
    with open(ctx.path(output), "wb") as out:
        for name in inputs:
            with open(ctx.path(name), "rb") as fh:
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)


# ================================ mergeSRArun ===================================

def merge_sra_run(ctx: RunContext, metadata_path: Path) -> None:
    """Port of ``mergeSRArun``."""
    opts = ctx.options
    reporter = ctx.reporter
    merge = opts.merge
    text = Path(metadata_path).read_text(errors="replace")
    lines = text.splitlines()

    if merge == "ex":
        experiments = _sorted_uniq(_RE_SRX.findall(text))
    elif merge == "sa":
        experiments = _sorted_uniq(_RE_SAM.findall(text))
    else:  # st
        experiments = _sorted_uniq(_RE_PRJ.findall(text))

    for experiment in experiments:
        run_list = [
            ln.split("\t")[0]
            for i, ln in enumerate(lines)
            if i > 0 and experiment in ln
        ]
        matched = [ln for ln in lines if experiment in ln]
        layouts = ["paired" if "PAIRED" in ln else "single" for ln in matched]
        layout = (_uniq_adjacent(layouts) or ["single"])[0]
        if not run_list:
            continue
        srr = run_list[0]

        gz_exists = any(
            ctx.path(f"{srr}{s}").is_file()
            for s in ("_1.fastq.gz", "_2.fastq.gz", ".fastq.gz")
        )
        plain_exists = any(
            ctx.path(f"{srr}{s}").is_file()
            for s in (".fastq", "_1.fastq", "_2.fastq")
        )

        if opts.gzip and gz_exists:
            if ctx.path(f"{experiment}.fastq.gz").is_file() or ctx.path(
                f"{experiment}_1.fastq.gz"
            ).is_file():
                reporter.info(f"{green('Note')}: {experiment} has been merged, skip")
                continue
            if len(run_list) == 1:
                if layout == "single":
                    reporter.info(
                        f"{green('Note')}: {experiment} only has one run, rename "
                        f"{run_list[0]} to {experiment}.fastq.gz"
                    )
                    _ln_s(ctx, f"{run_list[0]}.fastq.gz", f"{experiment}.fastq.gz")
                else:
                    reporter.info(
                        f"{green('Note')}: {experiment} only has one run, rename "
                        f"{run_list[0]} to {experiment}_1.fastq.gz and "
                        f"{experiment}_2.fastq.gz"
                    )
                    _ln_s(ctx, f"{run_list[0]}_1.fastq.gz", f"{experiment}_1.fastq.gz")
                    _ln_s(ctx, f"{run_list[0]}_2.fastq.gz", f"{experiment}_2.fastq.gz")
            else:
                if layout == "single":
                    files = [f"{r}.fastq.gz" for r in run_list]
                    _note_merge(reporter, files, f"{experiment}.fastq.gz")
                    _cat(ctx, files, f"{experiment}.fastq.gz")
                else:
                    f1 = [f"{r}_1.fastq.gz" for r in run_list]
                    _note_merge(reporter, f1, f"{experiment}_1.fastq.gz")
                    _cat(ctx, f1, f"{experiment}_1.fastq.gz")
                    f2 = [f"{r}_2.fastq.gz" for r in run_list]
                    _note_merge(reporter, f2, f"{experiment}_2.fastq.gz")
                    _cat(ctx, f2, f"{experiment}_2.fastq.gz")
        elif plain_exists:
            if ctx.path(f"{experiment}.fastq").is_file() or ctx.path(
                f"{experiment}_1.fastq"
            ).is_file():
                reporter.info(f"{green('Note')}: {experiment} has been merged, skip")
                continue
            if len(run_list) == 1:
                if layout == "single":
                    if "_1.fastq" in run_list[0]:
                        reporter.info(
                            f"{green('Note')}: {experiment} only has one run, rename "
                            f"{run_list[0]} to {experiment}_1.fastq"
                        )
                        _ln_s(ctx, f"{run_list[0]}_1.fastq", f"{experiment}_1.fastq")
                    else:
                        reporter.info(
                            f"{green('Note')}: {experiment} only has one run, rename "
                            f"{run_list[0]} to {experiment}.fastq"
                        )
                        _ln_s(ctx, f"{run_list[0]}.fastq", f"{experiment}.fastq")
                else:
                    reporter.info(
                        f"{green('Note')}: {experiment} only has one run, rename "
                        f"{run_list[0]} to {experiment}_1.fastq and {experiment}_2.fastq"
                    )
                    _ln_s(ctx, f"{run_list[0]}_1.fastq", f"{experiment}_1.fastq")
                    _ln_s(ctx, f"{run_list[0]}_2.fastq", f"{experiment}_2.fastq")
            else:
                if layout == "single":
                    files = [f"{r}.fastq" for r in run_list]
                    _note_merge(reporter, files, f"{experiment}.fastq")
                    _cat(ctx, files, f"{experiment}.fastq")
                else:
                    f1 = [f"{r}_1.fastq" for r in run_list]
                    _note_merge(reporter, f1, f"{experiment}_1.fastq")
                    _cat(ctx, f1, f"{experiment}_1.fastq")
                    f2 = [f"{r}_2.fastq" for r in run_list]
                    _note_merge(reporter, f2, f"{experiment}_2.fastq")
                    _cat(ctx, f2, f"{experiment}_2.fastq")
        else:
            raise MergeError(f"{srr} can't be found when merge {experiment}")


def _note_merge(reporter, files: List[str], output: str) -> None:
    listing = "\n".join(files)
    reporter.info(
        f"{green('Note')}: Those runs: \n{listing} \nwill be merged into "
        f"{output}, may take a while"
    )


# ================================ mergeGSArun ===================================

def merge_gsa_run(ctx: RunContext, metadata_path: Path) -> None:
    """Port of ``mergeGSArun``."""
    opts = ctx.options
    reporter = ctx.reporter
    merge = opts.merge
    text = Path(metadata_path).read_text(errors="replace")
    lines = text.splitlines()

    if merge == "ex":
        experiments = _sorted_uniq(_RE_CRX.findall(text))
    elif merge == "sa":
        experiments = _sorted_uniq(_RE_SAMC.findall(text))
    else:  # st
        experiments = _sorted_uniq(_RE_PRJC.findall(text))

    for experiment in experiments:
        matched = [ln for ln in lines if experiment in ln]
        # colNum = number of "|"-separated entries in field 7 (uniq)
        col_counts = _uniq_adjacent(
            [str(len(_field(ln, 7).split("|"))) for ln in matched]
        )
        col_num = int(col_counts[0]) if col_counts else 0
        row_num = len(matched)

        if row_num == 1:
            _merge_gsa_single_row(ctx, matched[0], experiment)
        else:
            _merge_gsa_multi_row(ctx, lines, matched, experiment, col_num)


def _field(line: str, n: int) -> str:
    """``cut -d, -f n`` (1-indexed, naive comma split, matching the Bash)."""
    parts = line.split(",")
    return parts[n - 1] if len(parts) >= n else ""


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _prefix(name: str) -> str:
    """``awk -F'[._]' '{print $1}'`` — token before the first '.' or '_'."""
    return re.split(r"[._]", name)[0]


def _merge_gsa_single_row(ctx: RunContext, row: str, experiment: str) -> None:
    reporter = ctx.reporter
    crr = _field(row, 1)
    entries = [e for e in _field(row, 7).split("|")]
    filenames = [_basename(e) for e in entries]
    prefixes = _uniq_adjacent([_prefix(f) for f in filenames])
    prefix = prefixes[0] if prefixes else ""

    if crr == prefix:
        for filename in filenames:
            renamed = filename.replace(crr, experiment, 1)
            if ctx.path(renamed).is_file() and not ctx.path(filename).is_file():
                reporter.info(
                    f"{green('Note')}: {renamed} has been merged (here renamed), skip"
                )
            else:
                reporter.info(
                    f"{green('Note')}: {experiment} only has one run {crr}, rename "
                    f"{filename} to {renamed}"
                )
                _ln_s(ctx, filename, renamed)
    else:
        joined = " ".join(prefixes)
        reporter.info(
            f"{green('Note')}: {experiment} only has one run ({crr}), however, the "
            f"prefix ({joined}) of the files are different, rename them:"
        )
        for filename in filenames:
            renamed = f"{experiment}_{filename}"
            if ctx.path(renamed).is_file() and not ctx.path(filename).is_file():
                reporter.info(
                    f"{green('Note')}: {renamed} has been merged (here renamed), skip"
                )
            else:
                reporter.info(f"{green('Note')}: Rename {filename} to {renamed}")
                _ln_s(ctx, filename, renamed)


def _merge_gsa_multi_row(ctx, lines, matched, experiment, col_num) -> None:
    reporter = ctx.reporter
    for i in range(1, col_num + 1):
        files = [
            _basename(_field(ln, 7).split("|")[i - 1])
            for ln in matched
            if len(_field(ln, 7).split("|")) >= i
        ]
        prefixes = _uniq_adjacent([_prefix(f) for f in files])
        prefix = prefixes[0] if prefixes else ""
        # CRR = grep $prefix metadata | cut -f1 | uniq
        crr_list = _uniq_adjacent(
            [_field(ln, 1) for ln in lines if prefix and prefix in ln]
        )
        crr = crr_list[0] if crr_list else ""
        example_file = files[0] if files else ""

        if _RE_FQGZ.search(example_file):
            if crr == prefix:
                target = example_file.replace(prefix, experiment, 1)
                if ctx.path(target).is_file():
                    reporter.info(
                        f"{green('Note')}: {target} has been merged, skip"
                    )
                else:
                    _note_merge_files(reporter, files, target)
                    _cat(ctx, files, target)
            else:
                target = f"{experiment}_{example_file}"
                if ctx.path(target).is_file():
                    reporter.info(
                        f"{green('Note')}: {target} has been merged, skip"
                    )
                else:
                    _note_merge_files(reporter, files, target)
                    _cat(ctx, files, target)
        else:
            listing = "\n".join(files)
            reporter.info(
                f"{bright_yellow('Note')}: Those files: \n{listing} \nwill not be "
                "merged, as they are not end with [fastq|fq].gz"
            )


def _note_merge_files(reporter, files: List[str], output: str) -> None:
    listing = "\n".join(files)
    reporter.info(
        f"{green('Note')}: Those files: \n{listing} \nwill be merged into "
        f"{output}, may take a while"
    )


# local import to avoid a cycle with accession at module load
from .accession import _uniq_adjacent  # noqa: E402
