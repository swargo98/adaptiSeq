"""Human-readable per-file segment progress logging.

The batch progress bar reports file workers. This helper reports the internal
per-file segment connections used by the segmented HTTP(S)/FTP transports.
"""

from __future__ import annotations

import os
import time
from typing import Dict, List, Tuple

from ..console import green
from ..options import DEFAULT_SEGMENT_LOG_INTERVAL


def _human_bytes(n: int) -> str:
    value = float(max(0, int(n)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)}B"
            return f"{value:.2f}{unit}"
        value /= 1024
    return f"{value:.2f}TB"


class SegmentProgressLogger:
    """Throttled reporter callback for downloader segment snapshots."""

    def __init__(
        self,
        reporter,
        save_path: str,
        transport: str,
        interval: float = DEFAULT_SEGMENT_LOG_INTERVAL,
    ):
        self.reporter = reporter
        self.save_name = os.path.basename(save_path)
        self.transport = transport
        self.interval = max(0.5, float(interval))
        self._last_progress = 0.0
        self._planned = False

    def __call__(self, event: str, state: Dict) -> None:
        if event == "planned":
            self._planned = True
            self.reporter.info(
                f"{green('Note')}: Segment plan for {self.save_name}: "
                f"{self.transport}, {self._segment_count(state)} segment(s), "
                f"{self._active_count(state)} active connection(s), "
                f"{_human_bytes(state.get('file_size', 0))} total"
            )
            return

        if event == "progress":
            now = time.monotonic()
            if now - self._last_progress < self.interval:
                return
            self._last_progress = now

        if event in ("progress", "complete", "paused", "failed"):
            if not self._planned and event == "progress":
                return
            label = {
                "progress": "Segment meter",
                "complete": "Segment meter",
                "paused": "Segment paused",
                "failed": "Segment failed",
            }[event]
            self.reporter.info(
                f"{green('Note')}: {label} for {self.save_name}: "
                f"{self._completed_count(state)}/{self._segment_count(state)} "
                f"complete | active {self._active_count(state)} | "
                f"{self._total_percent(state):.1f}% | {self._segment_breakdown(state)}"
            )

    @staticmethod
    def _segments(state: Dict) -> List[Tuple[int, int]]:
        return [tuple(seg) for seg in state.get("segments", [])]

    def _segment_count(self, state: Dict) -> int:
        return len(self._segments(state)) or 1

    @staticmethod
    def _completed_indices(state: Dict) -> set:
        return {int(i) for i in state.get("completed", set())}

    @staticmethod
    def _progress_offsets(state: Dict) -> Dict[int, int]:
        return {int(k): int(v) for k, v in state.get("progress_offsets", {}).items()}

    def _completed_count(self, state: Dict) -> int:
        if state.get("event") == "complete":
            return self._segment_count(state)
        segments = self._segments(state)
        completed = self._completed_indices(state)
        offsets = self._progress_offsets(state)
        count = 0
        for idx, (_start, end) in enumerate(segments):
            if idx in completed or offsets.get(idx, 0) >= end + 1:
                count += 1
        return count

    def _active_count(self, state: Dict) -> int:
        if state.get("event") == "complete":
            return 0
        segments = self._segments(state)
        completed = self._completed_indices(state)
        offsets = self._progress_offsets(state)
        active = 0
        for idx, (start, end) in enumerate(segments):
            off = offsets.get(idx, start)
            if idx not in completed and off < end + 1:
                active += 1
        return active

    def _total_percent(self, state: Dict) -> float:
        segments = self._segments(state)
        if not segments:
            return 100.0 if state.get("event") == "complete" else 0.0
        offsets = self._progress_offsets(state)
        total = 0
        done = 0
        for idx, (start, end) in enumerate(segments):
            size = end - start + 1
            total += max(0, size)
            if state.get("event") == "complete":
                done += max(0, size)
                continue
            off = max(start, min(offsets.get(idx, start), end + 1))
            done += max(0, off - start)
        return (done * 100.0 / total) if total else 0.0

    def _segment_breakdown(self, state: Dict) -> str:
        parts = []
        offsets = self._progress_offsets(state)
        for idx, (start, end) in enumerate(self._segments(state)):
            size = max(1, end - start + 1)
            if state.get("event") == "complete":
                pct = 100.0
            else:
                off = max(start, min(offsets.get(idx, start), end + 1))
                pct = (off - start) * 100.0 / size
            parts.append(f"s{idx + 1}={pct:.0f}%")
        return ", ".join(parts) if parts else "s1=0%"
