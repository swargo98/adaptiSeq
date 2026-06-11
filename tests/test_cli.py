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


def test_segmented_engine_is_accepted(tmp_path):
    # Part 2: segmented is the default and a real engine — the flag is accepted
    # (a bad accession yields the normal accession error, proving no engine error
    # and no "not available" message). -m needs only wget.
    rc, out, err = _run("-i", "BADACCESSION", "--engine", "segmented", "-m",
                        "-o", str(tmp_path))
    combined = out + err
    assert "not yet available" not in combined
    assert "Invalid engine" not in combined
    assert "not a valid" in combined  # the accession error, i.e. engine flag was fine


def test_invalid_engine_message(tmp_path):
    rc, out, err = _run("-i", "SRR7706354", "--engine", "bogus", "-m",
                        "-o", str(tmp_path))
    assert rc == 1
    assert "Invalid engine: bogus" in (out + err)


def test_help_lists_part2_flags():
    rc, out, err = _run("--help")
    for flag in ["--segment-size", "--max-segments", "--max-conns-per-host"]:
        assert flag in out, f"missing {flag} in --help"


def test_help_lists_part3_flags():
    rc, out, err = _run("--help")
    for flag in ["--jobs", "--adaptive", "--no-adaptive", "--probe-window",
                 "--cc-penalty", "--meta-jobs"]:
        assert flag in out, f"missing {flag} in --help"
    assert "default: 20" in out  # jobs


def test_invalid_jobs_message():
    rc, out, err = _run("-i", "SRR7706354", "-j", "0", "-m")
    assert rc == 1
    assert "Invalid jobs: 0" in (out + err)


def test_invalid_cc_penalty_message():
    rc, out, err = _run("-i", "SRR7706354", "--cc-penalty", "0.5", "-m")
    assert rc == 1
    assert "Invalid cc-penalty" in (out + err)


def test_no_adaptive_accepted(tmp_path):
    rc, out, err = _run("-i", "BADACCESSION", "--no-adaptive", "-m",
                        "-o", str(tmp_path))
    assert "Invalid" not in (out + err)
    assert "not a valid" in (out + err)  # reached resolution, flag accepted
