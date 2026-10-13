"""Instrumented single benchmark run for one accession list.

Usage: python bench/_run_one.py <adaptive|fixed> <list_path> <outdir>

Runs the adaptiSeq CLI (so the live progress bar + the adaptive "worker
trajectory" note are emitted), with INFO logging on the batch controller so each
adaptive probe (workers=N throughput=X) is visible. Prints a RESULT line with
wall-time and throughput.
"""
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# the controller lives here — keep it at INFO; quiet the per-segment retry chatter
logging.getLogger("adaptiseq.batch").setLevel(logging.INFO)
logging.getLogger("adaptiseq.engine.segmented").setLevel(logging.ERROR)

mode, listpath, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
argv = ["-i", listpath, "-g", "-k", "-o", outdir]
if mode == "fixed":
    argv.append("--no-adaptive")

from adaptiseq.cli import main  # noqa: E402

t0 = time.monotonic()
rc = main(argv)
dt = time.monotonic() - t0

nbytes = sum(p.stat().st_size for p in Path(outdir).rglob("*")
             if p.is_file() and not p.name.endswith((".log", ".tsv")))
mbps = (nbytes * 8) / (dt * 1e6) if dt > 0 else 0.0
print(f"\n=== RESULT mode={mode} elapsed={dt:.1f}s "
      f"data={nbytes/1e6:.0f}MB throughput={mbps:.0f}Mbps rc={rc}")
