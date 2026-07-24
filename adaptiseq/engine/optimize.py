"""Gradient adaptive concurrency controller.

Implements the ``gradient_opt_fast`` + ``run_probe`` algorithm (the step, the
``cc_change_limit`` clamp, the best-seen reset), with the three bookkeeping defects
called out in spec §2.1 fixed (see ``NOTES.md`` §P3.2). There is no skopt/scipy
``base_optimizer`` path.

The optimizer controls the number of active **workers**, never a connection
count (spec §0). The black-box it minimises is the negated, worker-cost-penalised
throughput score ``-(throughput / K**workers)``; the probe that produces it is
wired to the live throughput meter in :mod:`adaptiseq.batch`.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Callable, List, Optional

import numpy as np

log = logging.getLogger("adaptiseq.engine.optimize")

# Controller constants.
EXIT_SIGNAL = 10 ** 10
CC_CHANGE_LIMIT = 5
CACHE_LIMIT = 20


def run_probe(
    worker_count: int,
    count: int,
    black_box: Callable[[int], float],
    logger: Optional[logging.Logger] = None,
    verbose: bool = True,
) -> float:
    """``run_probe``: evaluate the black box once and log."""
    logger = logger or log
    import time

    if verbose:
        logger.debug("Iteration %s Starts ...", count)
    t1 = time.time()
    value = black_box(worker_count)
    t2 = time.time()
    if verbose:
        logger.debug(
            "Iteration %s Ends, Took %ss. Score: %s.",
            count, round(t2 - t1, 2), value,
        )
    return value


def gradient_opt_fast(
    max_cc: int,
    black_box: Callable[[int], float],
    logger: Optional[logging.Logger] = None,
    *,
    cc_change_limit: int = CC_CHANGE_LIMIT,
    verbose: bool = True,
    max_iterations: Optional[int] = None,
) -> List[int]:
    """Gradient descent over the active-worker count (spec §2, with §2.1 fixes).

    Returns the full trajectory of probed worker counts (``ccs``); the caller uses
    the last element. ``black_box(w)`` returns a value to *minimise* (the negated
    penalised throughput score), or :data:`EXIT_SIGNAL` when the transfer is done.

    Fixes vs ``search.py`` (NOTES §P3.2): the best-seen cache is keyed by worker
    count (not ``abs(score)``); the degenerate-gradient fallback is explicit,
    logged, and does **not** move (``gradient = 0``); cache eviction drops the
    **oldest** entry, not the freshest.
    """
    logger = logger or log
    max_cc = max(1, int(max_cc))
    count = 0
    # Fix #1: key the cache on worker count -> score (no abs-score collisions).
    cache: "OrderedDict[int, float]" = OrderedDict()
    values: List[float] = []
    ccs: List[int] = [1]

    while True:
        count += 1
        soft_limit = max_cc

        w = ccs[-1]
        value = run_probe(w, count, black_box, logger, verbose)
        values.append(value)
        cache[w] = value          # Fix #1
        cache.move_to_end(w)      # keep recency order for the oldest-eviction policy

        # Best-seen reset every 10 probes: best = worker count with the lowest
        # (most negative) value, i.e. the highest throughput-per-worker score.
        if count % 10 == 0 and cache:
            best_worker = min(cache, key=lambda k: cache[k])
            soft_limit = min(best_worker, max_cc)

        # Fix #3: evict the OLDEST observation, not the freshest.
        if len(cache) > CACHE_LIMIT:
            cache.popitem(last=False)

        if value == EXIT_SIGNAL:
            logger.info("Optimizer exits (transfer complete).")
            break
        if max_iterations is not None and count >= max_iterations:
            break

        if len(ccs) == 1:
            ccs.append(min(2, max_cc))
            continue

        difference = ccs[-1] - ccs[-2]
        prev, curr = values[-2], values[-1]
        if difference != 0 and prev != 0:
            gradient = (curr - prev) / (difference * prev)
        elif prev != 0:
            gradient = (curr - prev) / prev
        else:
            # Fix #2: explicit, logged degenerate case -> do not move.
            logger.warning(
                "Degenerate probe (prev score == 0); holding worker count steady."
            )
            gradient = 0.0

        update_cc = ccs[-1] * gradient
        if update_cc > 0:
            update_cc = min(max(1, int(np.round(update_cc))), cc_change_limit)
        elif update_cc < 0:
            update_cc = max(min(-1, int(np.round(update_cc))), -cc_change_limit)
        else:
            update_cc = 0

        next_cc = min(max(ccs[-1] + update_cc, 1), soft_limit)
        ccs.append(next_cc)
        logger.debug("Gradient: %s  ->  workers %s -> %s", gradient, ccs[-2], ccs[-1])

    return ccs
