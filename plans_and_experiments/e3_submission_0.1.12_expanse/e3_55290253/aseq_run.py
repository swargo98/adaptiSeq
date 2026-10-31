#!/usr/bin/env python3
"""Run the adaptiSeq CLI with the batch controller's INFO logging turned on.

The bare CLI cannot emit the adaptive controller's per-probe decisions: those are
`log.info("adaptive probe: workers=%d throughput=%.1fMbps ...")` in
`batch.AdaptiveController._probe`, and nothing configures logging to INFO. The
end-of-run "adaptive worker trajectory" Note lists the (workers, Mbps) pairs but
carries no timestamps, so it cannot be put on a time axis.

This wrapper only calls `logging.basicConfig` and then hands off to
`cli.main(argv)` -- the identical code path (`core.run`) the bare CLI takes. It
changes verbosity, not behaviour: no flags are injected, no download logic is
touched. Same device as the existing `bench/_run_one.py`.

Pairs with sample_concurrency.py:
  * this file  -> INTENT   (gate.active the controller chose, timestamped)
  * sampler    -> ACTUAL   (established sockets, same clock, every arm)
Plotting both is what makes E4's Fig 4 a claim about the controller rather than
an assertion.

Usage (drop-in for `adaptiseq`):
    python bench/e3/aseq_run.py -i LIST -g --adaptive -j 20 -Q -o .
"""

from __future__ import annotations

import logging
import os
import sys
import time

# ---------------------------------------------------------------------------
# Worker-count trace (ASEQ_WORKER_TRACE=<path>)
#
# WORKERS != CONNECTIONS. The external sampler counts TCP sockets; this counts
# the pool's active workers (files in flight). For adaptiSeq the two differ by
# the per-file segment count, which is size-dependent --
# `min(max_segments, max(1, size // segment_size))`:
#     D1 (~22 MB)  -> 1 conn/worker      D2 (~1.6 GB) -> 3 conns/worker
#     D3 (~11.5 GB)-> 8 conns/worker
# so connections cannot stand in for workers, and the ratio changes per panel.
#
# `batch._repaint` already calls ProgressBar.draw(mbps, gate.active) every 0.4 s
# and draw() early-returns when disabled -- so the number exists and is thrown
# away under -Q / non-TTY. Wrapping the method recovers it at ~2.5 Hz for BOTH
# fixed and adaptive arms (the controller's own probe log covers adaptive only,
# and only at probe boundaries). Patching the class method works regardless of
# when batch.py imports the class.
# ---------------------------------------------------------------------------
_trace_path = os.environ.get("ASEQ_WORKER_TRACE")
if _trace_path:
    from adaptiseq.progress import ProgressBar

    _fh = open(_trace_path, "w", buffering=1)
    _fh.write("t_rel_s\tworkers\tmbps\n")
    _t0 = time.monotonic()
    _orig_draw = ProgressBar.draw

    def _traced_draw(self, mbps: float, workers: int) -> None:
        try:
            _fh.write(f"{time.monotonic() - _t0:.2f}\t{workers}\t{mbps:.2f}\n")
        except Exception:
            pass  # never let instrumentation break the arm
        return _orig_draw(self, mbps, workers)

    ProgressBar.draw = _traced_draw  # type: ignore[method-assign]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
# The controller lives here. Keep the per-segment retry chatter quiet so the
# probe lines stay greppable and the log stays small over a 10-rep panel.
logging.getLogger("adaptiseq.batch").setLevel(logging.INFO)
logging.getLogger("adaptiseq.engine.segmented").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)

from adaptiseq.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
