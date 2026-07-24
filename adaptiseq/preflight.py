"""``CheckSoftware`` — the external-tool preflight.

Checks ``wget axel pigz ascp md5sum srapath vdb-validate`` (and conditionally
``fasterq-dump`` for ``-q``/``-e`` and ``axel`` for ``-p``). On a missing tool it
prints a three-line coloured guidance block and exits 1.

The library API never calls this (Section 6). The CLI calls :func:`preflight`
after argparse has already handled ``--help``/``--version`` — see NOTES.md
decision #1 for why the order is what it is.
"""

from __future__ import annotations

import shutil
from typing import List, Optional, Tuple

from .console import blue_bold, green_bold, red_bold
from .errors import PreflightError

# (binary, conda-package-hint).
BASE_TOOLS: List[Tuple[str, str]] = [
    ("wget", "wget"),
    ("axel", "axel"),
    ("pigz", "pigz"),
    ("ascp", "aspera-cli=4.14.0"),
    ("md5sum", "coreutils"),
    ("srapath", "sra-tools>=2.11.0"),
    ("vdb-validate", "sra-tools"),
]


def check_software(software1: str, software2: str) -> None:
    """Raise :class:`PreflightError` if ``software1`` is not on PATH.

    The error carries the exact ``How to solve?`` guidance lines iseq prints.
    """
    if shutil.which(software1) is not None:
        return
    solution = (
        f"Please install {green_bold(software2)} by conda (e.g. "
        f"{green_bold('conda install -c conda-forge -c bioconda ' + software2 + ' -y')}) "
        "or other ways and add it to the PATH environment variable.\n"
        f"All required software:{green_bold(' wget, sra-tools, axel, aspera, pigz ')}"
    )
    raise PreflightError(
        f"{green_bold(software1)} can not be found in your PATH environment variable.",
        solution,
    )


def preflight(*, need_fasterq_dump: bool = False, need_axel: bool = False) -> None:
    """Run the full startup check. Raises on the first missing tool.

    ``need_fasterq_dump`` adds the conditional ``CheckSoftware fasterq-dump``
    when ``-q``/``-e`` is used; ``need_axel`` covers the ``-p`` case (axel is in
    the base set too).
    """
    for binary, hint in BASE_TOOLS:
        check_software(binary, hint)
    if need_fasterq_dump:
        check_software("fasterq-dump", "sra-tools")
    if need_axel:
        check_software("axel", "axel")


def render_preflight_error(err: PreflightError) -> str:
    """Render a :class:`PreflightError` as the 2-3 line guidance block."""
    lines = [f"{red_bold('Error')}: {err.message}"]
    if err.solution:
        # The first solution line is prefixed with the blue "How to solve?" label.
        first, _, rest = err.solution.partition("\n")
        lines.append(f"{blue_bold('How to solve?')} {first}")
        if rest:
            lines.append(rest)
    return "\n".join(lines)
