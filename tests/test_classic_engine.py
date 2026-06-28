from adaptiseq.console import ListReporter
from adaptiseq.engine.classic import ClassicEngine
from adaptiseq.options import Options


def test_axel_parallel_download_logs_connection_count(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, cwd=None, stdout=None, stderr=None):
        calls.append((cmd, cwd, stdout, stderr))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("adaptiseq.engine.classic.subprocess.run", fake_run)
    reporter = ListReporter()
    opts = Options(engine="classic", parallel=4, speed=7)
    engine = ClassicEngine(opts, tmp_path, reporter)

    assert engine.fetch("ftp://example.test/file.fastq.gz", "file.fastq.gz")

    cmd = calls[0][0]
    assert cmd[:3] == ["axel", "-n", "4"]
    assert "-c" in cmd
    assert "-s" in cmd
    assert "7340032" in cmd
    joined = "\n".join(reporter.infos)
    assert "Classic engine using axel parallel download with 4 connection(s)" in joined
    assert "Axel may reuse connection numbers" in joined
    assert "Axel process completed for file.fastq.gz" in joined


def test_quiet_axel_discards_output_and_suppresses_notes(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, cwd=None, stdout=None, stderr=None):
        calls.append((cmd, stdout, stderr))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("adaptiseq.engine.classic.subprocess.run", fake_run)
    reporter = ListReporter()
    opts = Options(engine="classic", parallel=2, quiet=True)
    engine = ClassicEngine(opts, tmp_path, reporter)

    assert engine.fetch("ftp://example.test/file.fastq.gz", "file.fastq.gz")

    assert calls[0][1] is not None
    assert calls[0][2] is not None
    assert reporter.infos == []
