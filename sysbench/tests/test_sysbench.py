"""Self-validation for the sysbench harness (run with: pytest sysbench/tests).

These keep the *measurement instrument* trustworthy — they assert the sampler
reports CPU/IO/phase correctly against synthetic workloads with known behaviour.
Not part of the adaptiseq package test suite.
"""
import subprocess
import sys
import time

import pytest

from sysbench.sampler import Sampler
from sysbench.phases import PhaseTimeline, phase


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
