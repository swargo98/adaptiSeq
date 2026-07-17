from adaptiseq.console import ListReporter
from adaptiseq.engine.classic import ClassicEngine, ena_aspera_link, find_ena_aspera_key
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


def test_find_ena_aspera_key_when_ascp_and_key_share_conda_etc_dir(tmp_path, monkeypatch):
    aspera_dir = tmp_path / "env" / "etc" / "aspera"
    aspera_dir.mkdir(parents=True)
    ascp = aspera_dir / "ascp"
    key = aspera_dir / "aspera_bypass_rsa.pem"
    ascp.write_text("")
    key.write_text("key")

    monkeypatch.setattr("adaptiseq.engine.classic._which", lambda name: str(ascp))

    assert find_ena_aspera_key() == key


def test_find_ena_aspera_key_when_ascp_is_in_conda_bin(tmp_path, monkeypatch):
    env = tmp_path / "env"
    bin_dir = env / "bin"
    aspera_dir = env / "etc" / "aspera"
    bin_dir.mkdir(parents=True)
    aspera_dir.mkdir(parents=True)
    ascp = bin_dir / "ascp"
    key = aspera_dir / "aspera_bypass_rsa.pem"
    ascp.write_text("")
    key.write_text("key")

    monkeypatch.setattr("adaptiseq.engine.classic._which", lambda name: str(ascp))

    assert find_ena_aspera_key() == key


def test_ena_aspera_link_normalizes_ena_fastq_aspera_metadata_form():
    assert (
        ena_aspera_link("fasp.sra.ebi.ac.uk:/vol1/fastq/SRR/a.fastq.gz")
        == "era-fasp@fasp.sra.ebi.ac.uk:/vol1/fastq/SRR/a.fastq.gz"
    )


def test_ena_aspera_link_normalizes_ena_ftp_metadata_form():
    assert (
        ena_aspera_link("ftp.sra.ebi.ac.uk/vol1/fastq/SRR/a.fastq.gz")
        == "era-fasp@fasp.sra.ebi.ac.uk:/vol1/fastq/SRR/a.fastq.gz"
    )


def test_ena_aspera_link_keeps_authenticated_target_form():
    assert (
        ena_aspera_link("era-fasp@fasp.sra.ebi.ac.uk:/vol1/fastq/SRR/a.fastq.gz")
        == "era-fasp@fasp.sra.ebi.ac.uk:/vol1/fastq/SRR/a.fastq.gz"
    )


def test_fetch_aspera_uses_authenticated_ena_target(tmp_path, monkeypatch):
    calls = []
    key = tmp_path / "aspera_bypass_rsa.pem"
    key.write_text("key")

    def fake_run(cmd, cwd=None, stdout=None, stderr=None):
        calls.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("adaptiseq.engine.classic.find_ena_aspera_key", lambda: key)
    monkeypatch.setattr("adaptiseq.engine.classic.subprocess.run", fake_run)
    engine = ClassicEngine(Options(aspera=True), tmp_path)

    assert engine.fetch_aspera(
        "fasp.sra.ebi.ac.uk:/vol1/fastq/SRR/a.fastq.gz", "ENA"
    )

    assert "era-fasp@fasp.sra.ebi.ac.uk:/vol1/fastq/SRR/a.fastq.gz" in calls[0]
