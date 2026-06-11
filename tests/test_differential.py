"""Differential testing against iseq, with golden fixtures (Section 8.1).

Two modes, both required:

* **Fixture mode (default, runs in CI offline, never skips):** diff adaptiSeq's
  parsing/resolution against the frozen golden summaries under ``fixtures/``.
* **Live mode (skips gracefully when offline / iseq absent):** fetch metadata
  live via adaptiSeq and compare the stable Run/md5 sets to the golden; and, when
  the ``iseq`` binary is present, run stock ``iseq -m`` and ``adaptiseq -m`` into
  two directories and diff the metadata files.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import importlib

import adaptiseq
from adaptiseq.console import NullReporter

# `adaptiseq.resolve` (the attribute) is the public API function; reach the
# submodule explicitly.
R = importlib.import_module("adaptiseq.resolve")
from adaptiseq.options import Options, RunContext
from tests import harness

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SRA_TSV = FIXTURES / "SRR7706354" / "SRR7706354.metadata.tsv"
SRA_GOLD = json.loads((FIXTURES / "SRR7706354" / "expected.json").read_text())
GSA_CSV = FIXTURES / "CRR311377" / "CRR311377.metadata.csv"
GSA_GOLD = json.loads((FIXTURES / "CRR311377" / "expected.json").read_text())


# ============================== FIXTURE MODE (default) =========================

def test_fixture_sra_summary_matches_golden():
    summary = harness.summarize_sra(SRA_TSV)
    problems = harness.diff_dicts(
        {k: SRA_GOLD[k] for k in summary}, summary
    )
    assert not problems, "SRA fixture drift:\n" + "\n".join(problems)


def test_fixture_gsa_summary_matches_golden():
    summary = harness.summarize_gsa(GSA_CSV)
    problems = harness.diff_dicts(
        {k: GSA_GOLD[k] for k in summary}, summary
    )
    assert not problems, "GSA fixture drift:\n" + "\n".join(problems)


def test_fixture_sra_gzip_resolution_matches_golden(tmp_path):
    (tmp_path / "SRR7706354.metadata.tsv").write_bytes(SRA_TSV.read_bytes())
    ctx = RunContext(
        options=Options(gzip=True, database="ena", protocol="ftp"),
        reporter=NullReporter(),
        workdir=tmp_path,
    )
    ctx.accession = "SRR7706354"
    ctx.database = "ena"
    urls = R.resolve_sra_urls(ctx, "SRR7706354")
    assert urls == SRA_GOLD["resolved_gzip_ftp"]


# ================================== LIVE MODE ==================================

def test_live_sra_metadata_matches_golden(online):
    if not online:
        pytest.skip("offline: live differential test skipped (fixture mode covers CI)")
    records = adaptiseq.get_metadata("SRR7706354")
    runs = sorted({r["run_accession"] for r in records})
    assert runs == SRA_GOLD["runs"]
    md5s = sorted(
        {m for r in records for m in (r.get("fastq_md5", "") or "").split(";") if m}
    )
    assert md5s == SRA_GOLD["fastq_md5"]


def test_live_gsa_metadata_matches_golden(online):
    if not online:
        pytest.skip("offline: live differential test skipped")
    records = adaptiseq.get_metadata("CRR311377")
    runs = sorted({r["Run"] for r in records})
    assert runs == GSA_GOLD["runs"]
    names = sorted({n for r in records for n in r["FileName"].split("|") if n})
    assert names == GSA_GOLD["filenames"]


def test_live_against_stock_iseq_if_present(online, tmp_path):
    if not online:
        pytest.skip("offline: cannot diff against live iseq")
    if shutil.which("iseq") is None:
        pytest.skip("iseq not installed: live cross-check skipped (fixtures cover CI)")

    iseq_dir = tmp_path / "iseq"
    aseq_dir = tmp_path / "aseq"
    iseq_dir.mkdir()
    aseq_dir.mkdir()
    subprocess.run(["iseq", "-i", "SRR7706354", "-m", "-o", str(iseq_dir)], check=False)
    subprocess.run(
        [sys.executable, "-m", "adaptiseq.cli", "-i", "SRR7706354", "-m",
         "-o", str(aseq_dir)],
        cwd=str(harness.REPO_ROOT), check=False,
    )
    a = (iseq_dir / "SRR7706354.metadata.tsv").read_text().splitlines()
    b = (aseq_dir / "SRR7706354.metadata.tsv").read_text().splitlines()
    assert sorted(a) == sorted(b), "adaptiseq and iseq metadata differ"
