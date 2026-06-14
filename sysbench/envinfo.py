"""Environment capture for reproducibility (Part 7 §D).

Records exact tool versions + hardware/OS into ``env.json`` so every benchmark run is
attributable. Pure best-effort: a missing tool is recorded as ``null`` rather than
failing. Run standalone (``python -m sysbench.envinfo``) or via ``run_bench`` (writes
``<out>/env.json`` once at the start).
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import psutil

# (tool, argv, regex to pull a version-ish string from combined stdout+stderr)
_VERSION_PROBES = [
    ("adaptiseq", ["adaptiseq", "--version"], r"([\d.]+)"),
    ("iseq", ["iseq", "--version"], r"([\d.]+)"),
    ("prefetch", ["prefetch", "--version"], r"([\d.]+)"),
    ("fasterq-dump", ["fasterq-dump", "--version"], r"([\d.]+)"),
    ("vdb-validate", ["vdb-validate", "--version"], r"([\d.]+)"),
    ("pysradb", ["pysradb", "--version"], r"([\d.]+)"),
    ("edgeturbo", ["edgeturbo", "help"], r"version:\s*([\d.]+)"),
    ("ascp", ["ascp", "--version"], r"ascp version ([\d.]+)"),
    ("wget", ["wget", "--version"], r"Wget ([\d.]+)"),
    ("axel", ["axel", "--version"], r"([\d.]+)"),
    ("pigz", ["pigz", "--version"], r"([\d.]+)"),
    ("aria2c", ["aria2c", "--version"], r"version ([\d.]+)"),
    ("curl", ["curl", "--version"], r"curl ([\d.]+)"),
    ("kingfisher", ["kingfisher", "--version"], r"([\d.]+)"),
]


def _probe(argv, rx):
    if shutil.which(argv[0]) is None:
        return None
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        blob = (p.stdout or "") + (p.stderr or "")
    except Exception:
        return None
    m = re.search(rx, blob)
    return m.group(1) if m else (blob.strip().splitlines()[:1] or [None])[0]


def _py_libs():
    libs = {}
    for mod in ("aiohttp", "aioftp", "numpy", "psutil", "matplotlib", "pandas"):
        try:
            libs[mod] = __import__(mod).__version__
        except Exception:
            libs[mod] = None
    return libs


def collect() -> dict:
    vm = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage("/")
        disk_total_gb = round(disk.total / 1e9, 1)
    except Exception:
        disk_total_gb = None
    return {
        "tools": {name: _probe(argv, rx) for name, argv, rx in _VERSION_PROBES},
        "python": sys.version.split()[0],
        "python_libs": _py_libs(),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or platform.machine(),
            "cpu_logical": psutil.cpu_count(logical=True),
            "cpu_physical": psutil.cpu_count(logical=False),
            "mem_total_gb": round(vm.total / 1e9, 1),
            "disk_total_gb": disk_total_gb,
        },
    }


def write(out: Path) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "env.json"
    dest.write_text(json.dumps(collect(), indent=2))
    return dest


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("sysbench/runs"))
    args = ap.parse_args(argv)
    print(json.dumps(collect(), indent=2))
    print(f"\n[envinfo] -> {write(args.out)}")


if __name__ == "__main__":
    main()
