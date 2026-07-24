"""Typed exceptions for the library API.

Section 6 requires the public functions to "raise typed exceptions and return
values" rather than calling ``sys.exit`` or printing colour codes. The CLI layer
catches these and renders the matching coloured ``Error`` / ``How to solve?``
message before exiting with the appropriate status.
"""

from __future__ import annotations

from typing import Optional


class AdaptiSeqError(Exception):
    """Base class for all adaptiSeq errors.

    ``solution`` carries the "How to solve?" guidance printed alongside each
    error, so the CLI can render the two-line error format.
    """

    def __init__(self, message: str, solution: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.solution = solution


class InvalidAccessionError(AdaptiSeqError):
    """The accession does not match any supported format/regex."""


class MetadataError(AdaptiSeqError):
    """Metadata could not be fetched or was empty in all databases."""


class DownloadError(AdaptiSeqError):
    """A sequence file could not be resolved or downloaded."""


class IntegrityError(AdaptiSeqError):
    """A downloaded file failed its md5 / vdb-validate check after all retries."""


class MergeError(AdaptiSeqError):
    """A merge operation could not find an expected input file."""


class PreflightError(AdaptiSeqError):
    """A required external tool is missing from PATH."""


class EngineUnavailableError(AdaptiSeqError):
    """A requested download engine is not available in this build."""
