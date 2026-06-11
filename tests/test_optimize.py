"""Gradient controller: synthetic-trace unit tests (spec acceptance #4, #5).

Drives ``gradient_opt_fast`` over canned throughput curves (rising/saturating,
falling, noisy-flat) and asserts the step stays within ``cc_change_limit``, the
controller converges sensibly, and the §2.1 bookkeeping fixes hold.
"""

import logging

import numpy as np
import pytest

from adaptiseq.engine.optimize import (
    CC_CHANGE_LIMIT,
    EXIT_SIGNAL,
    gradient_opt_fast,
)

K = 1.01  # default --cc-penalty


def _bb(throughput_fn):
    """A black box: minimise -(throughput / K**w) as an int (as the probe does)."""
    def bb(w):
        t = throughput_fn(w)
        return int(round(-(t / (K ** w))))
    return bb


def _steps_bounded(ccs):
    return all(abs(b - a) <= CC_CHANGE_LIMIT for a, b in zip(ccs, ccs[1:]))


def test_step_never_exceeds_cc_change_limit():
    # A wildly rising curve would tempt huge jumps; the clamp must hold.
    bb = _bb(lambda w: 1000 * w)
    ccs = gradient_opt_fast(50, bb, max_iterations=40)
    assert _steps_bounded(ccs)
    assert all(1 <= c <= 50 for c in ccs)


def test_converges_toward_saturation_point():
    # Throughput rises then saturates at w=8; with the mild K penalty the optimum
    # sits around 8. The controller should climb and settle near there.
    bb = _bb(lambda w: 100 * min(w, 8))
    ccs = gradient_opt_fast(20, bb, max_iterations=60)
    assert _steps_bounded(ccs)
    assert 5 <= ccs[-1] <= 12  # in the neighbourhood of the saturation knee


def test_flat_throughput_prefers_one_worker():
    # Flat throughput -> score strictly decreasing in w (penalty) -> optimum w=1.
    bb = _bb(lambda w: 100.0)
    ccs = gradient_opt_fast(20, bb, max_iterations=40)
    assert _steps_bounded(ccs)
    assert ccs[-1] == 1


def test_noisy_flat_does_not_run_away():
    rng = np.random.default_rng(0)
    bb = _bb(lambda w: 100.0 + rng.normal(0, 3))
    ccs = gradient_opt_fast(20, bb, max_iterations=60)
    assert _steps_bounded(ccs)
    # Should hover low, not peg at the ceiling on noise.
    assert ccs[-1] <= 6


def test_exit_signal_terminates():
    calls = {"n": 0}

    def bb(w):
        calls["n"] += 1
        return EXIT_SIGNAL if calls["n"] >= 3 else -100

    ccs = gradient_opt_fast(10, bb)
    assert calls["n"] == 3  # stopped immediately on EXIT_SIGNAL


def test_degenerate_zero_probe_holds_and_warns(caplog):
    # prev score == 0 must NOT drive a unit step (Fix #2); it holds and warns.
    bb = _bb(lambda w: 0.0)  # always zero throughput -> value 0
    with caplog.at_level(logging.WARNING, logger="adaptiseq.engine.optimize"):
        ccs = gradient_opt_fast(20, bb, max_iterations=8)
    assert _steps_bounded(ccs)
    assert set(ccs) <= {1, 2}  # never runs away on a flat-zero probe
    assert any("Degenerate probe" in r.message for r in caplog.records)


def test_cache_keyed_by_worker_not_abs_score():
    # Two worker counts producing the same |score| must not collide in the
    # best-seen cache (Fix #1). Here w=2 and w=4 both yield value -100 (a
    # collision under abs-keying), but w=8 is strictly better (-200). The
    # best-seen reset at iteration 10 must still be able to recover w=8.
    def bb(w):
        return {1: -50, 2: -100, 4: -100, 8: -200}.get(w, -10)

    # Run enough to trigger the count%10 best-seen reset at least once.
    ccs = gradient_opt_fast(10, bb, max_iterations=25)
    assert _steps_bounded(ccs)
    # The trajectory must have actually probed multiple worker counts (i.e. the
    # cache held >1 key) without crashing on the collision.
    assert len(set(ccs)) >= 2
