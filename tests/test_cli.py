"""CLI surface parity (Section 7 acceptance criteria 1 & 2), via subprocess."""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\033\[[0-9;]*m")


def _run(*args):
    proc = subprocess.run(
        [sys.executable, "-m", "adaptiseq.cli", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, ANSI.sub("", proc.stdout), ANSI.sub("", proc.stderr)


def test_version_exact_string():
    rc, out, err = _run("--version")
    assert rc == 0
    assert out.strip() == "adaptiSeq 0.1.0"


def test_help_lists_every_flag_with_defaults():
    rc, out, err = _run("--help")
    assert rc == 0
    for flag in ["--input", "--metadata", "--gzip", "--fastq", "--threads",
                 "--merge", "--database", "--parallel", "--aspera", "--speed",
                 "--skip-md5", "--protocol", "--quiet", "--output", "--engine",
                 "--help", "--version"]:
        assert flag in out, f"missing {flag} in --help"
    assert "default: 8" in out          # threads
    assert "default: 1000" in out       # speed


def test_no_input_errors():
    rc, out, err = _run("-m")
    assert rc == 1
    assert "No input provided" in (out + err)


def test_invalid_option_errors():
    rc, out, err = _run("-i", "SRR7706354", "--bogus")
    assert rc == 1
    assert "Invalid option" in (out + err)


def test_invalid_database_message():
    rc, out, err = _run("-i", "SRR7706354", "-d", "xyz")
    assert rc == 1
    assert "Invalid database: xyz" in (out + err)


def test_merge_guard_rejects_run():
    rc, out, err = _run("-i", "SRR123456", "-e", "ex")
    assert rc == 1
    assert "is a Run ID" in (out + err)


def test_segmented_engine_falls_back(tmp_path):
    # --engine segmented must not be available in Part 1; it should note + fall back
    # to classic. We use -m so the run needs only wget (needs-based preflight).
    rc, out, err = _run("-i", "BADACCESSION", "--engine", "segmented", "-m",
                        "-o", str(tmp_path))
    combined = out + err
    assert "segmented engine is not yet available" in combined
