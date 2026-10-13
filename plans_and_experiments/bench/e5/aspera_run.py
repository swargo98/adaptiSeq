#!/usr/bin/env python3
"""Run the adaptiSeq CLI with the Aspera controller's per-probe trajectory logged.

The HTTP controller logs each probe (`aseq_run.py` scrapes those), but the Aspera
`HysteresisController` only logs a single "settled at N" line -- the per-probe
`(workers, throughput, efficiency)` sequence that Fig 5a plots lives in
`controller.trajectory` and is never emitted. This wrapper monkey-patches the pure
`adaptiseq.aspera.hysteresis_search` so that, once the additive-increase search
returns, every probe is logged as one INFO line:

    aspera probe: workers=W throughput=T efficiency=E
    aspera settled: workers=N efficiency>=X

The controller calls `hysteresis_search` by its module-global name, so replacing the
module attribute is picked up at call time. This changes verbosity, not behaviour --
no flags injected, the identical `core.run` path executes (same device as
`bench/e3/aseq_run.py`).

Usage (drop-in for `adaptiseq`):
    python bench/e5/aspera_run.py -a -i LIST --adaptive -j 8 --aspera-efficiency 0.7 -o .
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logging.getLogger("adaptiseq.aspera").setLevel(logging.INFO)
logging.getLogger("adaptiseq.engine.segmented").setLevel(logging.ERROR)

import adaptiseq.aspera as _asp  # noqa: E402

_log = logging.getLogger("adaptiseq.aspera")
_orig_search = _asp.hysteresis_search


def _logged_search(jobs, measure, efficiency, **kw):
    active, traj = _orig_search(jobs, measure, efficiency, **kw)
    for (w, t, e) in traj:
        # throughput units are whatever DirGrowthMeter.recent_average returns
        # (bytes/s); the driver normalises. Log raw so nothing is lost.
        _log.info("aspera probe: workers=%d throughput=%.3f efficiency=%.3f", w, t, e)
    _log.info("aspera settled: workers=%d efficiency>=%.2f", active, efficiency)
    return active, traj


_asp.hysteresis_search = _logged_search  # type: ignore[assignment]

from adaptiseq.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
