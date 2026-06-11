"""Run-time options and context.

The Bash script keeps state in shell globals (``gzip``, ``fastq``, ``database``,
``parallel`` ...). This module collects them into an explicit, typed
:class:`Options` object plus a :class:`RunContext` that carries the per-accession
mutable state (the current ``accession`` whose metadata file is being read, the
retry counter, the engine, the reporter, and the fail flag).

``database`` is deliberately mutable on the context: iseq flips it from ``auto``/
``ena`` to ``sra`` inside ``getSRAMetadata`` when ENA returns nothing, and the
download logic keys off that.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .console import NullReporter, Reporter


@dataclass
class Options:
    """Immutable user-supplied options, one per CLI/library invocation."""

    metadata: bool = False          # -m
    gzip: bool = False              # -g
    fastq: bool = False             # -q
    threads: int = 8               # -t
    merge: Optional[str] = None     # -e ex|sa|st  (None == off, matches Bash 0)
    database: str = "auto"         # -d ena|sra (auto-detect default)
    parallel: int = 0              # -p (0 == use wget, >0 == axel -n parallel)
    aspera: bool = False            # -a
    speed: int = 1000              # -s MB/s
    skip_md5: bool = False          # -k
    protocol: str = "ftp"          # -r ftp|https
    quiet: bool = False             # -Q
    output: Optional[str] = None    # -o
    engine: str = "classic"        # --engine classic|segmented (Part 1: classic)

    def __post_init__(self) -> None:
        if self.merge in (0, "0", ""):
            self.merge = None
        if self.merge is not None and self.merge not in ("ex", "sa", "st"):
            raise ValueError(f"Invalid merge: {self.merge}")
        if self.database not in ("auto", "ena", "sra"):
            raise ValueError(f"Invalid database: {self.database}")
        if self.protocol not in ("ftp", "https"):
            raise ValueError(f"Invalid protocol: {self.protocol}")
        if self.parallel < 0:
            raise ValueError(f"Invalid parallel: {self.parallel}")
        if self.speed <= 0:
            raise ValueError(f"Invalid speed: {self.speed}")


@dataclass
class RunContext:
    """Per-run mutable execution state, threaded through the port."""

    options: Options
    reporter: Reporter = field(default_factory=NullReporter)
    workdir: Path = field(default_factory=Path.cwd)

    # The accession whose metadata file the download/merge logic reads. In the
    # Bash this is the loop variable ``$accession`` that ``${accession}.metadata.*``
    # interpolates against.
    accession: str = ""

    # iseq mutates ``database`` to "sra" when ENA returns no rows. We keep the
    # user's choice in options and the effective value here.
    database: str = "auto"

    # ``count`` in the Bash. Reset per Run (see NOTES.md divergence #2).
    retry_count: int = 1

    # Set when any Run ultimately fails (the Bash ``.has_failed.flag``).
    failed: bool = False

    engine: object = None  # set to a ClassicEngine; typed loosely to avoid cycles

    def __post_init__(self) -> None:
        self.database = self.options.database

    def path(self, name: str) -> Path:
        """Resolve a filename relative to the working directory."""
        return self.workdir / name

    def metadata_tsv(self, accession: Optional[str] = None) -> Path:
        return self.path(f"{accession or self.accession}.metadata.tsv")

    def metadata_csv(self, accession: Optional[str] = None) -> Path:
        return self.path(f"{accession or self.accession}.metadata.csv")


def resolve_output_dir(output: Optional[str]) -> Path:
    """Mirror the ``-o`` handling: create if missing, must be writable, cd into it."""
    if output is None:
        return Path.cwd()
    out = Path(output)
    if not out.is_dir():
        out.mkdir(parents=True, exist_ok=True)
    if not os.access(out, os.W_OK):
        from .errors import AdaptiSeqError

        raise AdaptiSeqError(
            "The output directory is not writable",
            "Please check the write permission of the output directory",
        )
    return out
