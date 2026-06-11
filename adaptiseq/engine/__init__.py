"""Download engines.

Part 1 ships only the classic ``wget``/``axel`` engine plus an ``ascp`` aspera
path. The seam (Section 5.1) is a single method, :meth:`ClassicEngine.fetch`,
"download one resolved URL to one output path, return success or failure". Every
sequence-data byte flows through it; resolution, integrity, logging, and merge
never call ``wget``/``axel`` inline. Part 2 drops in ``SegmentedEngine`` behind
the same seam; Part 3 adds the adaptive controller.
"""

from .classic import ClassicEngine, get_engine

__all__ = ["ClassicEngine", "get_engine", "SegmentedEngine"]


def __getattr__(name):  # lazy to avoid importing aiohttp unless needed
    if name == "SegmentedEngine":
        from .seam import SegmentedEngine

        return SegmentedEngine
    raise AttributeError(name)
