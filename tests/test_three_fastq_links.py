"""iSeq issue #68: an ENA run can have more than two FASTQ links (ERR3493824 has ERR….fastq.gz,
ERR…_1.fastq.gz and ERR…_2.fastq.gz). iSeq assumed two and stopped; every link must be
fetched-and-verified here."""
import hashlib

from adaptiseq import integrity, logs
from adaptiseq.console import NullReporter
from adaptiseq.options import Options, RunContext

RUN = "ERR3493824"
NAMES = [f"{RUN}.fastq.gz", f"{RUN}_1.fastq.gz", f"{RUN}_2.fastq.gz"]


def _setup(tmp_path, bodies):
    md5 = [hashlib.md5(b).hexdigest() for b in bodies]
    ftp = ";".join(f"ftp.sra.ebi.ac.uk/vol1/fastq/ERR349/004/{RUN}/{n}" for n in NAMES)
    (tmp_path / f"{RUN}.metadata.tsv").write_text(
        "run_accession\tfastq_md5\tfastq_ftp\n" f"{RUN}\t{';'.join(md5)}\t{ftp}\n")
    ctx = RunContext(options=Options(gzip=True, database="ena"), reporter=NullReporter(), workdir=tmp_path)
    ctx.accession = RUN
    ctx.database = "ena"
    return ctx


def test_all_three_links_are_enumerated_and_verified(tmp_path):
    bodies = [b"unpaired", b"read one", b"read two"]
    for n, b in zip(NAMES, bodies):
        (tmp_path / n).write_bytes(b)
    ctx = _setup(tmp_path, bodies)
    assert integrity._gzip_fastq_files(ctx, RUN) == NAMES
    assert integrity.check_sra(ctx, RUN, lambda: None) is True
    assert logs.in_success(tmp_path, RUN)


def test_one_bad_file_among_three_fails_the_run(tmp_path):
    bodies = [b"unpaired", b"read one", b"read two"]
    for n, b in zip(NAMES, bodies):
        (tmp_path / n).write_bytes(b)
    (tmp_path / NAMES[1]).write_bytes(b"corrupt")          # the middle one is damaged
    ctx = _setup(tmp_path, bodies)
    assert integrity.check_sra(ctx, RUN, lambda: None) is False
    assert not logs.in_success(tmp_path, RUN)
    assert RUN in (tmp_path / "fail.log").read_text()
