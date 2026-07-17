"""Self-validation for the sysbench harness (run with: pytest sysbench/tests).

These keep the *measurement instrument* trustworthy — they assert the sampler
reports CPU/IO/phase correctly against synthetic workloads with known behaviour.
Not part of the adaptiseq package test suite.
"""
import os
import subprocess
import sys
import time

import pytest

from sysbench.sampler import Sampler
from sysbench.phases import PhaseTimeline, phase


def test_start_blocks_until_baselines_are_primed(monkeypatch):
    # start() must not return before _run has captured its IO/net baselines,
    # otherwise the caller's workload races ahead of the reference point and its
    # first bytes are invisible. Make priming observably slow and assert start()
    # actually waited for it.
    import sysbench.sampler as sampler_mod

    real_counters = sampler_mod.psutil.net_io_counters
    primed_at = []

    def slow_prime():
        time.sleep(0.5)
        primed_at.append(time.monotonic())
        return real_counters()

    monkeypatch.setattr(sampler_mod.psutil, "net_io_counters", slow_prime)

    s = Sampler(os.getpid(), PhaseTimeline(), interval=5.0)
    t0 = time.monotonic()
    s.start()
    returned_at = time.monotonic()
    s.stop()

    assert primed_at, "baselines were never primed"
    assert returned_at - t0 >= 0.5      # start() waited
    assert returned_at >= primed_at[0]  # ...specifically, until priming finished


@pytest.mark.filterwarnings(
    "ignore::pytest.PytestUnhandledThreadExceptionWarning"
)
def test_start_does_not_hang_when_priming_fails(monkeypatch):
    # A priming failure kills the sampler thread (the raise is deliberate — it
    # surfaces a broken instrument); start() must still return promptly rather
    # than block forever on _ready.
    import sysbench.sampler as sampler_mod

    def boom():
        raise RuntimeError("net counters unavailable")

    monkeypatch.setattr(sampler_mod.psutil, "net_io_counters", boom)
    s = Sampler(os.getpid(), PhaseTimeline(), interval=0.2)
    t0 = time.monotonic()
    s.start()
    elapsed = time.monotonic() - t0
    s.stop()
    assert elapsed < 2.0


def test_cpu_busy_child_reads_full_core():
    script = "import time\nt=time.time()\nx=0\nwhile time.time()-t<3: x+=1"
    p = subprocess.Popen([sys.executable, "-c", script])
    s = Sampler(p.pid, PhaseTimeline(), interval=0.5).start()
    p.wait()
    time.sleep(0.3)
    rows = s.stop()
    assert max((r.cpu_pct for r in rows), default=0) > 70  # ~100 for one core


def test_write_bytes_integrates_to_total():
    # trailing sleep keeps the child alive across sampling ticks (real downloaders
    # persist through the data phase; a child that exits mid-tick loses its IO).
    script = ("import os, time\nf=open('/tmp/_sb_pytest.bin','wb')\n"
              "for i in range(40): f.write(os.urandom(1000000)); f.flush(); "
              "os.fsync(f.fileno())\n"
              "time.sleep(1.5); os.remove('/tmp/_sb_pytest.bin')")
    p = subprocess.Popen([sys.executable, "-c", script])
    s = Sampler(p.pid, PhaseTimeline(), interval=0.4).start()
    p.wait()
    time.sleep(0.3)
    rows = s.stop()
    written = sum(r.write_mbps * 0.4 for r in rows)
    assert 25 < written < 60  # ~40 MB, with sampling slack


def test_phase_tagging_follows_marks():
    tl = PhaseTimeline()
    script = "import time; time.sleep(1.2)"
    with phase(tl, "metadata"):
        p = subprocess.Popen([sys.executable, "-c", script])
        s = Sampler(p.pid, tl, interval=0.3).start()
        time.sleep(0.6)
        tl.mark("data")
        p.wait()
    rows = s.stop()
    phases = {r.phase for r in rows}
    assert "metadata" in phases or "data" in phases
    d = tl.durations()
    assert d.get("metadata", 0) > 0
    assert d.get("data", 0) > 0


def test_tree_counts_children():
    script = "import time; time.sleep(1.5)"
    p = subprocess.Popen([sys.executable, "-c", script])
    s = Sampler(p.pid, PhaseTimeline(), interval=0.3).start()
    p.wait()
    rows = s.stop()
    assert max((r.nprocs for r in rows), default=0) >= 1
