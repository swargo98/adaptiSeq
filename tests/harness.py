"""Differential-test helpers.

These compute compact, comparable *summaries* of a metadata file — the column
set, the row (Run) set, the public md5 set, and the resolved download targets —
so the harness can diff adaptiSeq's behaviour against frozen golden fixtures
offline, and against live ``iseq`` output when available (Section 8.1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --- SRA/ENA (.metadata.tsv) ----------------------------------------------------

def sra_columns(path: Path) -> List[str]:
    lines = Path(path).read_text(errors="replace").splitlines()
    return lines[0].split("\t") if lines else []


def sra_run_set(path: Path) -> List[str]:
    lines = Path(path).read_text(errors="replace").splitlines()
    runs = [ln.split("\t")[0] for ln in lines[1:] if ln.split("\t")[0]]
    return sorted(set(runs))


def sra_fastq_md5_set(path: Path) -> List[str]:
    """The public fastq md5 set adaptiSeq validates against (``fastq_md5`` column)."""
    lines = Path(path).read_text(errors="replace").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    try:
        idx = header.index("fastq_md5")
    except ValueError:
        return []
    md5s: List[str] = []
    for ln in lines[1:]:
        cols = ln.split("\t")
        if idx < len(cols) and cols[idx]:
            md5s.extend(m for m in cols[idx].split(";") if m)
    return sorted(set(md5s))


def summarize_sra(path: Path) -> Dict:
    return {
        "columns": sra_columns(path),
        "runs": sra_run_set(path),
        "fastq_md5": sra_fastq_md5_set(path),
    }


# --- GSA (.metadata.csv) --------------------------------------------------------

def gsa_columns(path: Path) -> List[str]:
    lines = Path(path).read_text(errors="replace").splitlines()
    return lines[0].split(",") if lines else []


def gsa_run_set(path: Path) -> List[str]:
    lines = Path(path).read_text(errors="replace").splitlines()
    runs = [ln.split(",")[0] for ln in lines[1:] if ln.split(",")[0]]
    return sorted(set(runs))


def gsa_filenames(path: Path) -> List[str]:
    lines = Path(path).read_text(errors="replace").splitlines()
    names: List[str] = []
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) >= 5 and parts[4]:
            names.extend(n for n in parts[4].split("|") if n)
    return sorted(set(names))


def summarize_gsa(path: Path) -> Dict:
    return {
        "columns": gsa_columns(path),
        "runs": gsa_run_set(path),
        "filenames": gsa_filenames(path),
    }


def diff_dicts(expected: Dict, actual: Dict) -> List[str]:
    """Return a readable list of mismatches between two summary dicts."""
    problems: List[str] = []
    for key in sorted(set(expected) | set(actual)):
        e = expected.get(key)
        a = actual.get(key)
        if e != a:
            problems.append(f"- {key}:\n    expected: {e}\n    actual:   {a}")
    return problems
