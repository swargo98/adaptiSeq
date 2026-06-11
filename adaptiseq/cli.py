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
    g.add_argument("--engine", metavar="[segmented|classic]", default="segmented",
                   help="Download engine (default: segmented). 'classic' is the "
                        "Part 1 wget/axel path; segmented falls back to it per-host "
                        "when a host cannot serve ranges.")
    g.add_argument("--segment-size", metavar="int", default="512", dest="segment_size",
                   help="Segmented engine: target segment size in MB (default: 512).")
    g.add_argument("--max-segments", metavar="int", default="8", dest="max_segments",
                   help="Segmented engine: max connections per file (default: 8).")
    g.add_argument("--max-conns-per-host", metavar="int", default="8",
                   dest="max_conns_per_host",
                   help="Global cap on concurrent connections to any one host "
                        "(default: 8).")
    g.add_argument("-j", "--jobs", metavar="int", default="20",
                   help="Max worker-pool size for batch download (default: 20). "
                        "With --adaptive, the gradient optimizer chooses how many "
                        "of these are active at once.")
    g.add_argument("--adaptive", dest="adaptive", action="store_true", default=True,
                   help="Enable the gradient adaptive concurrency controller "
                        "(default: on).")
    g.add_argument("--no-adaptive", dest="adaptive", action="store_false",
                   help="Disable adaptivity: run all -j workers with no probing.")
    g.add_argument("--probe-window", metavar="int", default="5", dest="probe_window",
                   help="Adaptive optimizer probe window in seconds (default: 5).")
    g.add_argument("--cc-penalty", metavar="float", default="1.01", dest="cc_penalty",
                   help="Worker-cost penalty K in score=throughput/K**workers "
                        "(default: 1.01).")
    g.add_argument("--meta-jobs", metavar="int", default="3", dest="meta_jobs",
                   help="Parallelism for metadata/URL resolution (default: 3), "
                        "bounded by per-endpoint rate limits.")
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

    # --- engine handling (Part 2: segmented default, classic fallback) ---
    engine = args.engine.lower()
    if engine not in ("classic", "segmented"):
        _emit_error(reporter, f"Invalid engine: {args.engine}",
                    'Please use "segmented" or "classic" for the "--engine" option')
        return 1

    # --- value validation, mirroring iseq messages ---
    database = "auto"
    if args.database is not None:
        database = _validate_choice(
            "database", "-d", args.database, ("ena", "sra"),
            '"ena" or "sra"', reporter)
    # -r accepts ftp|https; when unspecified the engine auto-selects (HTTPS-first).
    protocol = "auto"
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

    # Part 2 segmented-engine knobs.
    segment_size_mb = _posint(
        "segment-size", "--segment-size", args.segment_size, 512,
        'Please use a positive integer (MB) for the "--segment-size" option')
    max_segments = _posint(
        "max-segments", "--max-segments", args.max_segments, 8,
        'Please use a positive integer for the "--max-segments" option')
    max_conns_per_host = _posint(
        "max-conns-per-host", "--max-conns-per-host", args.max_conns_per_host, 8,
        'Please use a positive integer for the "--max-conns-per-host" option')

    # -p, --parallel becomes an alias that sets --max-segments on the segmented
    # engine (spec §7), keeping its original axel meaning on --engine classic.
    if parallel > 0 and engine == "segmented":
        max_segments = parallel
        reporter.info(
            f"{yellow_bold('Note')}: -p {parallel} on the segmented engine sets "
            f"--max-segments {parallel} (segment count), not axel connections"
        )

    # Part 3 adaptive/batch knobs.
    jobs = _posint("jobs", "-j", args.jobs, 20,
                   'Please use a positive integer for the "-j" option')
    probe_window = _posint("probe-window", "--probe-window", args.probe_window, 5,
                           'Please use an integer >= 2 for the "--probe-window" option')
    if probe_window < 2:
        probe_window = 2
    meta_jobs = _posint("meta-jobs", "--meta-jobs", args.meta_jobs, 3,
                        'Please use a positive integer for the "--meta-jobs" option')
    try:
        cc_penalty = float(args.cc_penalty)
        if cc_penalty < 1.0:
            raise ValueError
    except ValueError:
        _emit_error(reporter, f"Invalid cc-penalty: {args.cc_penalty}",
                    'Please use a float >= 1.0 for the "--cc-penalty" option')
        return 1

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

    # --- preflight (needs-based; see NOTES.md divergence #4 / #P2.3) ---
    try:
        _cli_preflight(
            args.metadata, args.fastq, merge, parallel, engine,
            args.aspera, args.gzip, args.skip_md5,
        )
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
            engine=engine,
            segment_size=segment_size_mb * 1024 * 1024,
            max_segments=max_segments,
            max_conns_per_host=max_conns_per_host,
            jobs=jobs,
            adaptive=args.adaptive,
            probe_window=probe_window,
            cc_penalty=cc_penalty,
            meta_jobs=meta_jobs,
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


def _cli_preflight(
    metadata_only: bool,
    fastq: bool,
    merge,
    parallel: int,
    engine: str,
    aspera: bool,
    gzip: bool,
    skip_md5: bool,
) -> None:
    """Needs-based tool preflight (NOTES.md divergence #4, refined in §P2.3).

    The segmented engine fetches bytes itself (aiohttp/aioftp) and only needs
    ``wget`` for its classic fallback, so ``axel`` is required only on
    ``--engine classic`` with ``-p``. Integrity/convert tools are required only
    when the run will actually use them.
    """
    check_software("wget", "wget")
    if metadata_only:
        return
    # SRA integrity tools (skipped entirely with -k).
    if not skip_md5:
        check_software("md5sum", "coreutils")
        check_software("srapath", "sra-tools>=2.11.0")
        check_software("vdb-validate", "sra-tools")
    if gzip:
        check_software("pigz", "pigz")
    if aspera:
        check_software("ascp", "aspera-cli=4.14.0")
    if fastq or merge is not None:
        check_software("fasterq-dump", "sra-tools")
    if engine == "classic" and parallel > 0:
        check_software("axel", "axel")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
