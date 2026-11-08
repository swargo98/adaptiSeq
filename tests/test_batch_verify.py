"""md5 checks inside the batch pool.

Full run rep 3 (54927009), panel 3b: both adaptiSeq arms ended 7/8 and took 2 to
3 h, against 24 to 42 min for kingfisher and iSeq -p 8. ENA served several
corrupt transfers, and adaptiSeq only noticed them in the per-Run check after the
batch, which re-downloads one file at a time on a few connections. Now each file
is checked against ENA's md5 as soon as it lands, and a bad one goes back on the
queue while the pool is still running. The per-Run check then reuses the digest
instead of hashing the file again.
"""

import asyncio
import hashlib
import os

from adaptiseq import batch, integrity
from adaptiseq.batch import BatchDownloader, DownloadTask
from adaptiseq.console import ListReporter
from adaptiseq.engine.seam import SegmentedEngine
from adaptiseq.options import Options, RunContext
from tests.servers import MultiFileRangeServer

MB = 1024 * 1024


def md5(b):
    return hashlib.md5(b).hexdigest()


def _run(srv, files, tmp_path, reporter=None, **kw):
    opts = Options(engine="segmented", segment_size=MB, max_segments=4, quiet=True,
                   adaptive=False, jobs=len(files), **kw)
    eng = SegmentedEngine(opts, str(tmp_path))
    tasks = [DownloadTask(srv.url(n), n, "ACC", md5=md5(b)) for n, b in files.items()]
    bd = BatchDownloader(eng, opts, tmp_path, reporter)
    failed = asyncio.run(bd.run(tasks))
    return bd, failed


def test_corrupt_transfer_is_fetched_again_inside_the_pool(tmp_path):
    files = {f"f{i}.fastq.gz": os.urandom(6 * MB) for i in range(3)}
    rep = ListReporter()
    with MultiFileRangeServer(files) as srv:
        srv.corrupt["f1.fastq.gz"] = 1
        bd, failed = _run(srv, files, tmp_path, rep)

    assert not failed
    for n, b in files.items():
        assert md5((tmp_path / n).read_bytes()) == md5(b)
    assert bd.md5_mismatches == 1
    assert any("MD5 mismatch for f1.fastq.gz" in m for m in rep.infos)
    assert sorted(os.path.basename(p) for p in bd.verified) == sorted(files)


def test_file_that_stays_corrupt_fails_after_three_downloads(tmp_path):
    files = {"good.fastq.gz": os.urandom(6 * MB), "bad.fastq.gz": os.urandom(6 * MB)}
    with MultiFileRangeServer(files) as srv:
        srv.corrupt["bad.fastq.gz"] = 100
        bd, failed = _run(srv, files, tmp_path)

    assert failed == {"bad.fastq.gz"}
    assert bd.md5_mismatches == 3
    # the bad bytes are not left behind for the per-Run check to resume from
    assert not any(p.name.startswith("bad.fastq.gz") for p in tmp_path.iterdir())
    assert md5((tmp_path / "good.fastq.gz").read_bytes()) == md5(files["good.fastq.gz"])


def test_task_without_md5_is_not_hashed(tmp_path, monkeypatch):
    files = {"x.sra": os.urandom(2 * MB)}
    monkeypatch.setattr(batch, "md5sum", lambda p: (_ for _ in ()).throw(AssertionError))
    with MultiFileRangeServer(files) as srv:
        opts = Options(engine="segmented", quiet=True, adaptive=False, jobs=1)
        bd = BatchDownloader(SegmentedEngine(opts, str(tmp_path)), opts, tmp_path)
        failed = asyncio.run(bd.run([DownloadTask(srv.url("x.sra"), "x.sra", "ACC")]))
    assert not failed and bd.verified == {}


def test_per_run_check_reuses_batch_digest_until_the_file_changes(tmp_path, monkeypatch):
    data = os.urandom(MB)
    f = tmp_path / "SRR1.fastq.gz"
    f.write_bytes(data)
    (tmp_path / "SRR1.metadata.tsv").write_text(
        "run_accession\tfastq_md5\tfastq_ftp\n"
        f"SRR1\t{md5(data)}\tftp.sra.ebi.ac.uk/x/SRR1.fastq.gz\n")
    ctx = RunContext(options=Options(quiet=True), workdir=tmp_path)
    ctx.accession = "SRR1"
    integrity.remember_md5(ctx, f, md5(data))

    calls = []
    real = integrity.md5sum
    monkeypatch.setattr(integrity, "md5sum", lambda p: calls.append(p) or real(p))
    assert integrity._gzip_md5_ok(ctx, ["SRR1.fastq.gz"]) == (True, None)
    assert calls == []

    # a changed file (new size and mtime) is hashed, and fails, as before
    f.write_bytes(data[:-1] + bytes([data[-1] ^ 1]) + b"x")
    assert integrity._gzip_md5_ok(ctx, ["SRR1.fastq.gz"]) == (False, "SRR1.fastq.gz")
    assert calls == [f]


def test_fastq_md5s_maps_each_file_to_its_md5():
    tsv = ("run_accession\tfastq_md5\tfastq_ftp\n"
           "SRR1\tAAA;bbb\tftp.x/SRR1_1.fastq.gz;ftp.x/SRR1_2.fastq.gz\n"
           "SRR2\tccc\tftp.x/SRR2.fastq.gz\n"
           "SRR3\t\t\n")
    assert integrity.fastq_md5s(tsv) == {
        "SRR1_1.fastq.gz": "aaa", "SRR1_2.fastq.gz": "bbb", "SRR2.fastq.gz": "ccc"}
    assert integrity.fastq_md5s("Run,ReleaseDate\nSRR1,2023\n") == {}


def test_resolver_attaches_ena_md5_unless_md5_is_skipped(tmp_path):
    acc = "SRR22904251"
    (tmp_path / f"{acc}.metadata.tsv").write_text(
        "study_accession\trun_accession\tlibrary_layout\tfastq_md5\tfastq_ftp\tsra_ftp\n"
        f"PRJNA1\t{acc}\tSINGLE\tabc\tftp.sra.ebi.ac.uk/vol1/fastq/SRR229/051/{acc}/{acc}.fastq.gz\t\n")
    opts = Options(gzip=True, protocol="ftp", quiet=True)
    assert [t.md5 for t in batch._resolve_one(acc, opts, tmp_path)] == ["abc"]
    opts = Options(gzip=True, protocol="ftp", quiet=True, skip_md5=True)
    assert [t.md5 for t in batch._resolve_one(acc, opts, tmp_path)] == [None]
