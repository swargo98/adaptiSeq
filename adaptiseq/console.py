"""Coloured message output that mirrors iseq's exact escape sequences.

The Bash original embeds ANSI codes directly in every ``echo -e``. To preserve
byte-for-byte console parity (Section 3: "match the Bash output exactly,
including the coloured Note / Error / How to solve? message style") this module
reproduces those exact codes.

Crucially, the *library* API must not print colour codes or call ``sys.exit``
(Section 6). So all user-facing output goes through a :class:`Reporter`. The CLI
installs :class:`AnsiReporter` (writes to stdout with colour); library callers
get :class:`NullReporter` by default. The colour helpers below produce the same
strings either way, so a caller that wants the coloured text can still capture it.
"""

from __future__ import annotations

import sys
from typing import Optional, TextIO

# --- Raw ANSI codes, matched verbatim to the codes used in iSeq-main/bin/iseq ---
RESET = "\033[0m"
RED_BOLD = "\033[1;31m"       # "Error"
GREEN_BOLD = "\033[1;32m"     # software names, "How to solve?" (some sites)
BLUE_BOLD = "\033[1;34m"      # "How to solve?" (CheckSoftware)
YELLOW_BOLD = "\033[1;33m"    # "Note" (the -a/-p simultaneous warning)
GREEN = "\033[32m"           # "Note" (informational, green)
BRIGHT_YELLOW = "\033[93m"    # "Note" (warning, bright yellow)
BRIGHT_GREEN = "\033[92m"     # success messages
BRIGHT_RED = "\033[91m"       # md5 mismatch / failure messages
PALE_YELLOW = "\033[33m"      # rarely used


def red_bold(text: str) -> str:
    return f"{RED_BOLD}{text}{RESET}"


def green_bold(text: str) -> str:
    return f"{GREEN_BOLD}{text}{RESET}"


def blue_bold(text: str) -> str:
    return f"{BLUE_BOLD}{text}{RESET}"


def yellow_bold(text: str) -> str:
    return f"{YELLOW_BOLD}{text}{RESET}"


def green(text: str) -> str:
    return f"{GREEN}{text}{RESET}"


def bright_yellow(text: str) -> str:
    return f"{BRIGHT_YELLOW}{text}{RESET}"


def bright_green(text: str) -> str:
    return f"{BRIGHT_GREEN}{text}{RESET}"


def bright_red(text: str) -> str:
    return f"{BRIGHT_RED}{text}{RESET}"


class Reporter:
    """Sink for user-facing progress/status lines.

    Subclasses decide whether/where to emit. ``info`` is for stdout-style lines;
    ``error`` is for stderr-style lines (the Bash sends some errors to ``>&2``).
    """

    def info(self, message: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def error(self, message: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class AnsiReporter(Reporter):
    """Writes coloured lines exactly like the Bash ``echo -e`` calls."""

    def __init__(self, out: Optional[TextIO] = None, err: Optional[TextIO] = None):
        self._out = out if out is not None else sys.stdout
        self._err = err if err is not None else sys.stderr

    def info(self, message: str) -> None:
        print(message, file=self._out)

    def error(self, message: str) -> None:
        print(message, file=self._err)


class NullReporter(Reporter):
    """Discards everything. Default for the library API (Section 6)."""

    def info(self, message: str) -> None:
        return None

    def error(self, message: str) -> None:
        return None


class ListReporter(Reporter):
    """Collects messages for tests/introspection without printing."""

    def __init__(self) -> None:
        self.infos: list[str] = []
        self.errors: list[str] = []

    def info(self, message: str) -> None:
        self.infos.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)
