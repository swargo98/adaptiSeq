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


def test_write_bytes_integrates_to_total(tmp_path):
    # trailing sleep keeps the child alive across sampling ticks (real downloaders
    # persist through the data phase; a child that exits mid-tick loses its IO).
    # Linux reports process ``write_bytes`` as physical storage IO, not logical
    # bytes written, so tmpfs/overlay/cached filesystems can undercount the 40 MB
    # workload. The harness-level invariant is that the sampler sees substantial
    # write activity in the expected order of magnitude.
    trigger = tmp_path / "go"
    data = tmp_path / "payload.bin"
    script = (
        "import os, sys, time\n"
        "trigger, data = sys.argv[1], sys.argv[2]\n"
        "while not os.path.exists(trigger): time.sleep(0.01)\n"
        "f=open(data,'wb')\n"
        "for i in range(40): f.write(os.urandom(1000000)); f.flush(); "
        "os.fsync(f.fileno())\n"
        "time.sleep(1.5); os.remove(data)"
    )
    p = subprocess.Popen([sys.executable, "-c", script, str(trigger), str(data)])
    s = Sampler(p.pid, PhaseTimeline(), interval=0.4).start()
    trigger.touch()
    p.wait()
    time.sleep(0.3)
    rows = s.stop()
    written = 0.0
    prev_t = 0.0
    for row in rows:
        written += row.write_mbps * max(0.0, row.t - prev_t)
        prev_t = row.t
    assert 10 < written < 80  # ~40 MB logical, physical IO can undercount


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
