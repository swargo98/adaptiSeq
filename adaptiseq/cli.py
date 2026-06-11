"""Command-line interface — a thin wrapper over the library API.

Mirrors iseq's flags, help, and version. All real work is delegated to
:mod:`adaptiseq.core`; this layer only parses arguments, runs the tool preflight,
installs the coloured :class:`AnsiReporter`, and maps typed exceptions onto the
exact ``Error`` / ``How to solve?`` two-line format with exit code 1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import core
from .console import (
    AnsiReporter,
    blue_bold,
    green_bold,
    red_bold,
    yellow_bold,
)
from .errors import AdaptiSeqError, PreflightError
from .options import Options, resolve_output_dir
from .preflight import check_software, render_preflight_error
from .routing import check_merge_guard

VERSION = "adaptiSeq 0.1.0"

USAGE = """\
Usage:
  adaptiseq -i accession [options]

Accepted accession formats:
    1.    Projects: PRJEB, PRJNA, PRJDB, PRJC, GSE
    2.     Studies: ERP, DRP, SRP, CRA
    3.  BioSamples: SAMD, SAME, SAMN, SAMC
    4.     Samples: ERS, DRS, SRS, GSM
    5. Experiments: ERX, DRX, SRX, CRX
    6.        Runs: ERR, DRR, SRR, CRR
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="adaptiseq",
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "adaptiSeq: download sequencing data and metadata for each Run from "
            "[GSA, SRA, ENA or DDBJ] databases.\n\n" + USAGE
        ),
    )
    g = p.add_argument_group("options")
    g.add_argument("-i", "--input", metavar="[text|file]",
                   help="Single accession or a file containing multiple accessions "
                        "(one per line).")
    g.add_argument("-m", "--metadata", action="store_true",
                   help="Skip the sequencing data downloads and only fetch metadata.")
    g.add_argument("-g", "--gzip", action="store_true",
                   help="Download FASTQ files in gzip format directly (*.fastq.gz).")
    g.add_argument("-q", "--fastq", action="store_true",
                   help="Convert SRA files to FASTQ format.")
    g.add_argument("-t", "--threads", metavar="int", default="8",
                   help="Threads for SRA->FASTQ / compression (default: 8).")
    g.add_argument("-e", "--merge", metavar="[ex|sa|st]",
                   help="Merge fastq files per Experiment/Sample/Study.")
    g.add_argument("-d", "--database", metavar="[ena|sra]",
                   help="Force database for SRA data (default: auto-detect).")
    g.add_argument("-p", "--parallel", metavar="int",
                   help="axel connection count for parallel download, e.g. -p 10.")
    g.add_argument("-a", "--aspera", action="store_true",
                   help="Use Aspera (ascp); GSA/ENA only.")
    g.add_argument("-s", "--speed", metavar="int", default="1000",
                   help="Download speed limit in MB/s (default: 1000).")
    g.add_argument("-k", "--skip-md5", action="store_true", dest="skip_md5",
                   help="Skip the md5 check for downloaded files.")
    g.add_argument("-r", "--protocol", metavar="[ftp|https]",
                   help="ENA protocol selection (default: ftp).")
    g.add_argument("-Q", "--quiet", action="store_true",
                   help="Suppress download progress bars.")
    g.add_argument("-o", "--output", metavar="text",
                   help="Output directory (created if missing; default: cwd).")
    g.add_argument("--engine", metavar="[segmented|classic]", default="classic",
                   help="Download engine (Part 1: only 'classic'; default classic).")
    g.add_argument("-h", "--help", action="store_true",
                   help="Show the help information.")
    g.add_argument("-v", "--version", action="store_true",
                   help="Show the program version.")
    return p


def _emit_error(reporter: AnsiReporter, message: str, solution: Optional[str]) -> None:
    reporter.error(f"{red_bold('Error')}: {message}")
    if solution:
        reporter.error(f"{green_bold('How to solve?')} {solution}")


def _read_input(value: str) -> List[str]:
    """Single accession vs file-of-accessions (NOTES.md divergence #3)."""
    path = Path(value)
    if path.is_file():
        text = path.read_text(errors="replace")
        return [line.rstrip("\r") for line in text.splitlines() if line.strip() != ""]
    return [value]


def _validate_choice(label: str, flag: str, value: str, allowed, hints, reporter) -> str:
    low = value.lower()
    if low not in allowed:
        _emit_error(
            reporter,
            f"Invalid {label}: {value}",
            f'Please use {hints} for the "{flag}" option',
        )
        sys.exit(1)
    return low


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    reporter = AnsiReporter()

    args, unknown = parser.parse_known_args(argv)

    if args.help:
        parser.print_help()
        return 0
    if args.version:
        print(VERSION)
        return 0
    if unknown:
        _emit_error(
            reporter, f"Invalid option: {unknown[0]}",
            f"Please remove {unknown[0]} option",
        )
        return 1

    # --- -i required ---
    if not args.input:
        _emit_error(reporter, "No input provided",
                    'Please provide the input by "-i" option')
        return 1

    # --- engine handling (Part 1: only classic) ---
    engine = args.engine.lower()
    if engine == "segmented":
        reporter.info(
            f"{yellow_bold('Note')}: the segmented engine is not yet available in "
            "this build (Part 1), falling back to the classic engine"
        )
        engine = "classic"
    elif engine != "classic":
        _emit_error(reporter, f"Invalid engine: {args.engine}",
                    'Please use "classic" (Part 1) for the "--engine" option')
        return 1

    # --- value validation, mirroring iseq messages ---
    database = "auto"
    if args.database is not None:
        database = _validate_choice(
            "database", "-d", args.database, ("ena", "sra"),
            '"ena" or "sra"', reporter)
    protocol = "ftp"
    if args.protocol is not None:
        protocol = _validate_choice(
            "protocol", "-r", args.protocol, ("ftp", "https"),
            '"ftp" or "https"', reporter)
    merge = None
    if args.merge is not None:
        merge = _validate_choice(
            "merge", "-e", args.merge, ("ex", "sa", "st"),
            '"ex", "sa", or "st"', reporter)

    def _posint(label: str, flag: str, value: str, default: int, hint: str) -> int:
        if value is None:
            return default
        if not value.isdigit() or int(value) <= 0:
            _emit_error(reporter, f"Invalid {label}: {value}", hint)
            sys.exit(1)
        return int(value)

    # iseq does not validate -t as a positive int (it passes it straight through);
    # we coerce leniently, defaulting to 8 on a non-integer.
    threads = int(args.threads) if str(args.threads).isdigit() else 8
    speed = _posint(
        "speed", "-s", args.speed, 1000,
        'Please use a positive integer for the "-s" option, such as "-s 1000" '
        "means 1000 MB/s")
    parallel = 0
    if args.parallel is not None:
        parallel = _posint(
            "parallel", "-p", args.parallel, 0,
            'Please use a positive integer for the "-p" option')

    accessions = _read_input(args.input)

    # --- merge accession-type guards ---
    if merge is not None:
        try:
            check_merge_guard(merge, accessions)
        except AdaptiSeqError as exc:
            _emit_error(reporter, exc.message, exc.solution)
            return 1

    # --- aspera/parallel interaction notes (mirrors iseq) ---
    if args.aspera and parallel > 0:
        reporter.info(
            f"{yellow_bold('Note')}: -a and -p options were used at the same time, "
            "-a will be used first"
        )
    if args.aspera and database == "sra":
        _emit_error(reporter, "SRA database does not support Aspera download",
                    'Please remove -a option or switch to the ENA database by "-d ena"')
        return 1

    # --- preflight (needs-based; see NOTES.md divergence #4) ---
    try:
        _cli_preflight(args.metadata, args.fastq, merge, parallel)
    except PreflightError as exc:
        reporter.error(render_preflight_error(exc))
        return 1

    # --- build options & output dir ---
    try:
        options = Options(
            metadata=args.metadata,
            gzip=args.gzip,
            fastq=args.fastq,
            threads=threads,
            merge=merge,
            database=database,
            parallel=parallel,
            aspera=args.aspera,
            speed=speed,
            skip_md5=args.skip_md5,
            protocol=protocol,
            quiet=args.quiet,
            output=args.output,
            engine="classic",
        )
        workdir = resolve_output_dir(args.output)
    except AdaptiSeqError as exc:
        _emit_error(reporter, exc.message, exc.solution)
        return 1
    except ValueError as exc:
        _emit_error(reporter, str(exc), None)
        return 1

    # --- run ---
    try:
        ctx = core.run(accessions, options, reporter=reporter, workdir=workdir)
    except AdaptiSeqError as exc:
        _emit_error(reporter, exc.message, exc.solution)
        return 1

    if ctx.failed:
        reporter.error(
            f"{red_bold('Error')}: Download failures detected. Please check "
            "\033[4mfail.log\033[0m for details."
        )
        reporter.error(
            f"{yellow_bold('Note:')} You can re-run the script to retry failed items."
        )
        return 1
    return 0


def _cli_preflight(metadata_only: bool, fastq: bool, merge, parallel: int) -> None:
    """Tool preflight. Metadata-only needs just wget; downloads need the full set."""
    check_software("wget", "wget")
    if metadata_only:
        return
    check_software("axel", "axel")
    check_software("pigz", "pigz")
    check_software("ascp", "aspera-cli=4.14.0")
    check_software("md5sum", "coreutils")
    check_software("srapath", "sra-tools>=2.11.0")
    check_software("vdb-validate", "sra-tools")
    if fastq or merge is not None:
        check_software("fasterq-dump", "sra-tools")
    if parallel > 0:
        check_software("axel", "axel")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
