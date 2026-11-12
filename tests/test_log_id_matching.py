"""Issue #2: success.log / fail.log matched IDs by substring, so SRR123 was skipped after
SRR1234 succeeded and SRR1234's fail.log line was erased when SRR123 succeeded."""
import threading

import pytest

from adaptiseq import logs


def test_prefix_id_is_not_found_by_a_longer_logged_id(tmp_path):
    logs.mark_success(tmp_path, "SRR1234")
    assert logs.in_success(tmp_path, "SRR1234")
    assert not logs.in_success(tmp_path, "SRR123")
    assert not logs.in_success(tmp_path, "SRR12345")


def test_success_of_a_prefix_id_keeps_the_longer_ids_fail_line(tmp_path):
    logs.mark_fail(tmp_path, "SRR1234")
    logs.mark_success(tmp_path, "SRR123")
    assert "SRR1234" in (tmp_path / "fail.log").read_text()
    logs.mark_success(tmp_path, "SRR1234")
    assert not (tmp_path / "fail.log").read_text().strip()


def test_run_id_is_found_through_its_file_names(tmp_path):
    # the resolve step logs file names, the integrity step the bare Run ID; both mean "this Run is done"
    logs.mark_success(tmp_path, "SRR123_1.fastq.gz")
    logs.mark_success(tmp_path, "CRR9_f1.fq.gz")
    logs.mark_success(tmp_path, "DRR7.sra")
    assert logs.in_success(tmp_path, "SRR123")
    assert logs.in_success(tmp_path, "SRR123_1.fastq.gz")
    assert logs.in_success(tmp_path, "CRR9")
    assert logs.in_success(tmp_path, "DRR7")
    assert not logs.in_success(tmp_path, "SRR12")
    assert not logs.in_success(tmp_path, "SRR123_2.fastq.gz")
    assert not logs.in_success(tmp_path, "CRR")


def test_file_name_of_another_run_does_not_collide(tmp_path):
    logs.mark_success(tmp_path, "SRR1234_1.fastq.gz")
    assert not logs.in_success(tmp_path, "SRR123_1.fastq.gz")
    assert not logs.in_success(tmp_path, "SRR123")


def test_success_removes_the_runs_file_names_from_fail_log_only(tmp_path):
    for tok in ("SRR123_1.fastq.gz", "SRR123_2.fastq.gz", "SRR1234_1.fastq.gz", "SRR123", "SRR1234"):
        logs.mark_fail(tmp_path, tok)
    logs.mark_success(tmp_path, "SRR123")
    left = [ln.split("\t")[1] for ln in (tmp_path / "fail.log").read_text().splitlines()]
    assert left == ["SRR1234_1.fastq.gz", "SRR1234"]


def test_lines_without_a_tab_and_crlf_are_read(tmp_path):
    (tmp_path / "success.log").write_bytes(b"SRR55\r\nTue Jun 10 00:00:00 UTC 2026\tSRR66\r\n\n")
    assert logs.in_success(tmp_path, "SRR55")
    assert logs.in_success(tmp_path, "SRR66")
    assert not logs.in_success(tmp_path, "SRR5")
    assert not logs.in_success(tmp_path, "")


def test_missing_log_and_blank_token(tmp_path):
    assert not logs.in_success(tmp_path, "SRR1")
    logs.ensure_success_log(tmp_path)
    assert not logs.in_success(tmp_path, "SRR1")


def test_changes_made_outside_this_process_are_seen(tmp_path):
    logs.mark_success(tmp_path, "SRR1")
    assert logs.in_success(tmp_path, "SRR1")
    assert not logs.in_success(tmp_path, "SRR2")
    with open(tmp_path / "success.log", "a") as fh:          # another process (or the user) appends
        fh.write("date\tSRR2\n")
    assert logs.in_success(tmp_path, "SRR2")
    (tmp_path / "success.log").write_text("date\tSRR3\n")     # the user removes a line by hand
    assert not logs.in_success(tmp_path, "SRR1")
    assert logs.in_success(tmp_path, "SRR3")
    (tmp_path / "success.log").unlink()
    assert not logs.in_success(tmp_path, "SRR3")


def test_a_batch_reads_the_log_once(tmp_path, monkeypatch):
    reads = []
    real = logs._read_keys
    monkeypatch.setattr(logs, "_read_keys", lambda p: reads.append(p) or real(p))
    logs._cache.clear()
    logs.ensure_success_log(tmp_path)
    for i in range(300):
        assert not logs.in_success(tmp_path, f"SRR{i}")
        logs.mark_success(tmp_path, f"SRR{i}")
        assert logs.in_success(tmp_path, f"SRR{i}")
    assert len(reads) == 1


def test_concurrent_marks_are_all_found(tmp_path):
    logs.ensure_success_log(tmp_path)
    def work(k):
        for i in range(40):
            logs.mark_success(tmp_path, f"SRR{k}{i:03d}")
    ts = [threading.Thread(target=work, args=(k,)) for k in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len((tmp_path / "success.log").read_text().splitlines()) == 320
    assert all(logs.in_success(tmp_path, f"SRR{k}{i:03d}") for k in range(8) for i in range(40))
    assert not logs.in_success(tmp_path, "SRR")
