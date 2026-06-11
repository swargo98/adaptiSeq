"""Merge logic parity — synthetic inputs exercising rename/concat (Section 3.7)."""

from pathlib import Path

from adaptiseq import merge
from adaptiseq.console import NullReporter
from adaptiseq.options import Options, RunContext


def _ctx(tmp_path, **opts):
    ctx = RunContext(options=Options(**opts), reporter=NullReporter(), workdir=tmp_path)
    return ctx


def _write(p: Path, data: bytes):
    p.write_bytes(data)


# --------------------------------- SRA -----------------------------------------

def test_sra_single_end_concat(tmp_path):
    tsv = tmp_path / "meta.tsv"
    tsv.write_text(
        "run_accession\texperiment_accession\tlibrary_layout\n"
        "SRR0000001\tSRX0000009\tSINGLE\n"
        "SRR0000002\tSRX0000009\tSINGLE\n"
    )
    _write(tmp_path / "SRR0000001.fastq.gz", b"AAA")
    _write(tmp_path / "SRR0000002.fastq.gz", b"BBB")
    ctx = _ctx(tmp_path, gzip=True, merge="ex")
    merge.merge_sra_run(ctx, tsv)
    out = tmp_path / "SRX0000009.fastq.gz"
    assert out.is_file()
    assert out.read_bytes() == b"AAABBB"


def test_sra_single_run_paired_rename_symlinks(tmp_path):
    tsv = tmp_path / "meta.tsv"
    tsv.write_text(
        "run_accession\texperiment_accession\tlibrary_layout\n"
        "SRR0000003\tSRX0000010\tPAIRED\n"
    )
    _write(tmp_path / "SRR0000003_1.fastq.gz", b"R1")
    _write(tmp_path / "SRR0000003_2.fastq.gz", b"R2")
    ctx = _ctx(tmp_path, gzip=True, merge="ex")
    merge.merge_sra_run(ctx, tsv)
    l1 = tmp_path / "SRX0000010_1.fastq.gz"
    l2 = tmp_path / "SRX0000010_2.fastq.gz"
    assert l1.is_symlink() and l2.is_symlink()
    assert l1.read_bytes() == b"R1"
    assert l2.read_bytes() == b"R2"


def test_sra_merge_skips_when_already_merged(tmp_path):
    tsv = tmp_path / "meta.tsv"
    tsv.write_text(
        "run_accession\texperiment_accession\tlibrary_layout\n"
        "SRR0000001\tSRX0000009\tSINGLE\n"
        "SRR0000002\tSRX0000009\tSINGLE\n"
    )
    _write(tmp_path / "SRR0000001.fastq.gz", b"AAA")
    _write(tmp_path / "SRR0000002.fastq.gz", b"BBB")
    _write(tmp_path / "SRX0000009.fastq.gz", b"PRE-EXISTING")
    ctx = _ctx(tmp_path, gzip=True, merge="ex")
    merge.merge_sra_run(ctx, tsv)
    # Must not overwrite an already-merged output.
    assert (tmp_path / "SRX0000009.fastq.gz").read_bytes() == b"PRE-EXISTING"


# --------------------------------- GSA -----------------------------------------

_GSA_HEADER = (
    "Run,Center,ReleaseDate,FileType,FileName,FileSize,Download_path,Experiment\n"
)


def test_gsa_single_run_same_prefix_rename(tmp_path):
    csv = tmp_path / "meta.csv"
    csv.write_text(
        _GSA_HEADER
        + "CRR0000001,C,2024,fastq,CRR0000001.fq.gz,100,"
        "ftp://download.big.ac.cn/gsa/CRA000001/CRR0000001/CRR0000001.fq.gz,CRX0000001\n"
    )
    _write(tmp_path / "CRR0000001.fq.gz", b"GSA")
    ctx = _ctx(tmp_path, merge="ex")
    merge.merge_gsa_run(ctx, csv)
    out = tmp_path / "CRX0000001.fq.gz"
    assert out.is_symlink()
    assert out.read_bytes() == b"GSA"


def test_gsa_single_run_different_prefix_rename(tmp_path):
    # CRR != file prefix -> rename to ${experiment}_${filename}
    csv = tmp_path / "meta.csv"
    csv.write_text(
        _GSA_HEADER
        + "CRR0000002,C,2024,fastq,CRD015671.gz,100,"
        "ftp://download.big.ac.cn/gsa/CRA000002/CRR0000002/CRD015671.gz,CRX0000002\n"
    )
    _write(tmp_path / "CRD015671.gz", b"DATA")
    ctx = _ctx(tmp_path, merge="ex")
    merge.merge_gsa_run(ctx, csv)
    out = tmp_path / "CRX0000002_CRD015671.gz"
    assert out.is_symlink()
    assert out.read_bytes() == b"DATA"
