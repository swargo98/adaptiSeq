"""Segmented, resumable HTTP(S)/FTP download engine — STUB (filled in Part 2).

Part 2 implements this as a drop-in replacement for :class:`ClassicEngine` behind
the same seam (``fetch(url, save_path) -> bool``), with fixed (non-adaptive)
concurrency. Part 1 only reserves the name so the CLI surface and engine factory
are stable across parts.
"""

from __future__ import annotations

from ..errors import EngineUnavailableError


class SegmentedEngine:  # pragma: no cover - stub
    name = "segmented"

    def __init__(self, *args, **kwargs):
        raise EngineUnavailableError(
            "The segmented engine is not yet available in this build (Part 1).",
            "Use the default --engine classic; the segmented engine arrives in Part 2.",
        )

    def fetch(self, url: str, save_path: str) -> bool:
        raise EngineUnavailableError(
            "The segmented engine is not yet available in this build (Part 1)."
        )
