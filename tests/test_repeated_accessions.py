"""A list that names the same accession twice (lists from several projects overlap): each accession
is processed once. Before, two threads resolved the same accession at once and wrote the same
SRR....metadata.tsv; the loser read a half-written table, printed 'The sequencing file of
run_accession is not available', and wrote the Run to fail.log although it had downloaded and
verified (exit status 1)."""
from adaptiseq import core
from adaptiseq.options import Options


class Rec:
    def __init__(self): self.lines = []
    def info(self, msg): self.lines.append(msg)
    def __getattr__(self, name): return lambda *a, **k: None


def test_each_accession_is_processed_once_in_order(tmp_path, monkeypatch):
    seen, batch = [], []
    monkeypatch.setattr(core, "process_accession", lambda ctx, acc: seen.append(acc))
    monkeypatch.setattr(core, "_batch_download_phase", lambda ctx, accs: batch.append(list(accs)))
    rec = Rec()
    core.run(["SRR1", "SRR2", "SRR1", "SRR3", "SRR2", "SRR1"], Options(), rec, tmp_path)
    assert seen == ["SRR1", "SRR2", "SRR3"]
    assert batch == [["SRR1", "SRR2", "SRR3"]]                 # the parallel phase gets the list once each
    assert sum("repeated accession" in m for m in rec.lines) == 1
    assert any("3 repeated accession" in m for m in rec.lines)


def test_a_list_without_repeats_is_unchanged_and_silent(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(core, "process_accession", lambda ctx, acc: seen.append(acc))
    monkeypatch.setattr(core, "_batch_download_phase", lambda ctx, accs: None)
    rec = Rec()
    core.run(["SRR1", "SRR2"], Options(), rec, tmp_path)
    assert seen == ["SRR1", "SRR2"]
    assert not any("repeated" in m for m in rec.lines)


def test_a_single_accession_named_twice_takes_the_single_accession_path(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(core, "process_accession", lambda ctx, acc: seen.append(acc))
    monkeypatch.setattr(core, "_batch_download_phase", lambda ctx, accs: None)
    core.run(["SRR1", "SRR1"], Options(), Rec(), tmp_path)
    assert seen == ["SRR1"]
