"""Phase B must not re-resolve/re-download files the batch phase already fetched.

The per-accession loop (``process_accession``) is the authority that verifies
(md5), converts, merges, and logs. When the parallel batch phase has already put
the run's files on disk, Phase B should verify them in place — not pay a full
per-accession network resolution (``wget --spider`` + transport probe) that
re-does work already done. Regression guard for the ~15s/accession tail that
made 3a take ~50 min of Phase B on top of a ~4 min batch download.
"""

import hashlib

from adaptiseq import core
from adaptiseq.console import ListReporter
from adaptiseq.logs import in_success
from adaptiseq.options import Options, RunContext


def _md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def _write_single_end(tmp_path, srr="SRR1"):
    data = b"pretend fastq.gz payload for " + srr.encode()
    (tmp_path / f"{srr}.fastq.gz").write_bytes(data)
    base = f"ftp.sra.ebi.ac.uk/vol1/fastq/SRR000/001/{srr}"
    (tmp_path / f"{srr}.metadata.tsv").write_text(
        "run_accession\tlibrary_layout\tfastq_ftp\tfastq_md5\n"
        f"{srr}\tSINGLE\t{base}/{srr}.fastq.gz\t{_md5(data)}\n"
    )


def _ctx(tmp_path, **opts):
    base = dict(gzip=True, database="ena", protocol="ftp", quiet=True)
    base.update(opts)
    return RunContext(options=Options(**base), reporter=ListReporter(),
                      workdir=tmp_path)


def test_phaseb_verifies_present_gzip_run_without_redownloading(tmp_path, monkeypatch):
    _write_single_end(tmp_path)
    ctx = _ctx(tmp_path)

    called = []
    monkeypatch.setattr(core.resolve, "download_sra", lambda c, s: called.append(s))

    core.process_accession(ctx, "SRR1")

    assert called == []                    # no network re-resolution/-download
    assert in_success(tmp_path, "SRR1")    # but md5 still ran and logged success


def test_phaseb_redownloads_when_gzip_file_missing(tmp_path, monkeypatch):
    # No file on disk -> the present-file fast path must NOT trigger; Phase B
    # falls through to the real download. Guards against over-eager skipping.
    base = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR000/002/SRR2"
    (tmp_path / "SRR2.metadata.tsv").write_text(
        "run_accession\tlibrary_layout\tfastq_ftp\tfastq_md5\n"
        f"SRR2\tSINGLE\t{base}/SRR2.fastq.gz\tdeadbeef\n"
    )
    ctx = _ctx(tmp_path)

    called = []
    monkeypatch.setattr(core.resolve, "download_sra", lambda c, s: called.append(s))
    # md5 will "fail" (no real file), but with skip_md5 we isolate the download call.
    ctx.options.skip_md5 = True

    core.process_accession(ctx, "SRR2")

    assert called == ["SRR2"]              # missing file -> real download happens


def test_run_files_present_requires_every_part_of_a_paired_run(tmp_path):
    # A 3-file / paired run: present-check must be all-or-nothing, or a half-present
    # run would skip the download of its missing mate (the paired-end invariant).
    base = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR000/003/SRR3"
    fastq = f"{base}/SRR3_1.fastq.gz;{base}/SRR3_2.fastq.gz"
    (tmp_path / "SRR3.metadata.tsv").write_text(
        "run_accession\tlibrary_layout\tfastq_ftp\n"
        f"SRR3\tPAIRED\t{fastq}\n"
    )
    ctx = _ctx(tmp_path)
    ctx.accession = "SRR3"

    (tmp_path / "SRR3_1.fastq.gz").write_bytes(b"one")
    assert core._run_files_present(ctx, "SRR3") is False   # _2 still missing

    (tmp_path / "SRR3_2.fastq.gz").write_bytes(b"two")
    assert core._run_files_present(ctx, "SRR3") is True     # both present


def test_run_files_present_uses_bare_name_on_sra_path(tmp_path):
    # Non-gzip / SRA path keeps the original bare-SRR check.
    (tmp_path / "SRR4.metadata.tsv").write_text(
        "run_accession\tlibrary_layout\nSRR4\tSINGLE\n"
    )
    ctx = _ctx(tmp_path, gzip=False)
    ctx.accession = "SRR4"

    assert core._run_files_present(ctx, "SRR4") is False
    (tmp_path / "SRR4").write_bytes(b"sra")
    assert core._run_files_present(ctx, "SRR4") is True
