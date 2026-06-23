"""Regression: a segmented download must finalize/fail cleanly even when the
``.part`` file is missing — it must never raise ``FileNotFoundError`` from an
unguarded ``rename('.part' -> final)``. Seen on Colab when every segment's
connection was refused: stale resume metadata claimed completion but no ``.part``
existed on disk.
"""

from __future__ import annotations

import asyncio

from adaptiseq.engine.segmented import SegmentedDownloader


def test_finalize_with_stale_metadata_and_missing_part(tmp_path) -> None:
    local = str(tmp_path / "SRR_x.fastq.gz")
    file_size = 4096

    d = SegmentedDownloader(session=None, url="https://h/x", local_path=local)
    segments = d.calculate_segments(file_size)
    # metadata claims every segment is already complete...
    d.write_metadata(file_size, segments, set(range(len(segments))), {})
    # ...but neither the .part nor the final file exists on disk (the bug trigger).

    ok, paused, _ = asyncio.run(d.download_segmented(file_size))

    assert ok is False and paused is False        # clean failure, not a crash
    assert not (tmp_path / "SRR_x.fastq.gz.part.meta").exists()  # stale meta cleared
