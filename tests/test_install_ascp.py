"""``adaptiseq --install-ascp``: offline, with a fake SDK archive and fake key data (the real ones are
pinned by sha256 in adaptiseq/ascp_install.py and were verified against IBM's download and ascli's key)."""
import hashlib
import io
import os
import stat
import tarfile

import pytest

from adaptiseq import ascp_install as ai
from adaptiseq import cli
from adaptiseq.engine import classic

PREFIX = ai._ARCHIVE_PREFIX
FAKE_DER = bytes(range(200))


def _archive(version="ascp version 4.4.8.2592 x", extra=None, omit=()):
    members = {
        "bin/ascp": f"#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo '{version}'; fi\nexit 0\n".encode(),
        "bin/async": b"not wanted",
        "etc/aspera-license": b"license",
        "etc/aspera.conf": b"conf",
        "lib/libafwsfeed.so": b"lib1",
        "lib/libstdc++.so.6": ("symlink", "libstdc++.so.6.0.28"),
        "lib/libstdc++.so.6.0.28": b"lib3",
        "api/go/example.go": b"sample",
    }
    members.update(extra or {})
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            if name in omit:
                continue
            info = tarfile.TarInfo(PREFIX + name if not name.startswith("/") and "../" not in name else name)
            if isinstance(data, tuple):                              # ("symlink", target)
                info.type = tarfile.SYMTYPE
                info.linkname = data[1]
                tar.addfile(info)
                continue
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    sdk = tmp_path / "home" / ".aspera" / "sdk"
    monkeypatch.setattr(classic, "SDK_DIR", sdk)
    monkeypatch.setattr(ai, "platform_key", lambda: ai.PLATFORM)
    classic._ascp_versions.clear()
    archive = _archive()

    def pin(arch=archive, key=FAKE_DER):
        monkeypatch.setattr(ai, "SDK_SHA256", hashlib.sha256(arch).hexdigest())
        monkeypatch.setattr(ai, "KEY_DATA_SHA256", hashlib.sha256(key).hexdigest())
    pin()
    return dict(sdk=sdk, archive=archive, pin=pin, say=[].append)


def _install(env, **kw):
    msgs = []
    path = ai.install_ascp(sdk_dir=env["sdk"], sdk_bytes=kw.pop("sdk_bytes", env["archive"]),
                           key_bytes=kw.pop("key_bytes", FAKE_DER), say=msgs.append, **kw)
    return path, msgs


def test_install_writes_the_flat_layout_with_a_private_key(env):
    path, msgs = _install(env, assume_yes=True)
    sdk = env["sdk"]
    assert path == sdk / "ascp"
    assert sorted(p.name for p in sdk.iterdir()) == sorted(
        ["ascp", "aspera-license", "aspera.conf", ai.KEY_FILE, "libafwsfeed.so", "libstdc++.so.6", "libstdc++.so.6.0.28"])
    assert os.access(path, os.X_OK)
    assert stat.S_IMODE((sdk / ai.KEY_FILE).stat().st_mode) == 0o600
    pem = (sdk / ai.KEY_FILE).read_text()
    assert pem.startswith("-----BEGIN RSA PRIVATE KEY-----\n") and pem.endswith("-----END RSA PRIVATE KEY-----\n")
    assert max(len(l) for l in pem.splitlines()[1:-1]) <= 64
    assert any("Installed ascp 4.4.8.2592" in m for m in msgs)
    assert not [p for p in sdk.parent.iterdir() if p.name.startswith(".sdk-install-")]      # no staging left


def test_installed_ascp_is_then_the_one_adaptiseq_runs_and_its_key_is_found(env, monkeypatch):
    _install(env, assume_yes=True)
    monkeypatch.setattr(classic, "_which", lambda name: None)
    assert classic.ascp_path() == str(env["sdk"] / "ascp")
    assert classic.find_ena_aspera_key().resolve() == (env["sdk"] / ai.KEY_FILE).resolve()


def test_notice_names_the_source_the_checksums_and_the_terms(env):
    _, msgs = _install(env, assume_yes=True)
    text = msgs[0]
    assert ai.SDK_URL in text and ai.KEY_URL in text and str(env["sdk"]) in text
    assert "IBM's terms" in text and "does not redistribute" in text and "sha256" in text


def test_a_checksum_mismatch_installs_nothing(env):
    other = _archive(extra={"etc/aspera.conf": b"tampered"})
    with pytest.raises(ai.AscpInstallError, match="does not match the pinned checksum"):
        _install(env, assume_yes=True, sdk_bytes=other)
    assert not env["sdk"].exists()
    with pytest.raises(ai.AscpInstallError, match="key data"):
        _install(env, assume_yes=True, key_bytes=b"tampered key")
    assert not env["sdk"].exists()


def test_confirmation_is_required(env):
    with pytest.raises(ai.AscpInstallError, match="not confirmed"):
        _install(env, confirm=lambda q: False)
    assert not env["sdk"].exists()
    _install(env, confirm=lambda q: True)
    assert (env["sdk"] / "ascp").is_file()


def test_no_terminal_and_no_yes_refuses(env, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))            # not a tty
    with pytest.raises(ai.AscpInstallError, match="Not a terminal") as exc:
        _install(env)
    assert "--install-ascp --yes" in exc.value.solution
    assert not env["sdk"].exists()


def test_other_platforms_are_refused(env, monkeypatch):
    monkeypatch.setattr(ai, "platform_key", lambda: None)
    with pytest.raises(ai.AscpInstallError, match="linux-x86_64 only"):
        _install(env, assume_yes=True)


def test_an_install_that_is_already_new_enough_is_left_alone(env):
    _install(env, assume_yes=True)
    (env["sdk"] / "marker").write_text("x")
    path, msgs = _install(env, assume_yes=True, sdk_bytes=b"would fail the checksum")
    assert (env["sdk"] / "marker").exists() and "already installed" in msgs[0]


def test_force_reinstalls_and_keeps_the_old_directory(env):
    _install(env, assume_yes=True)
    (env["sdk"] / "marker").write_text("x")
    _, msgs = _install(env, assume_yes=True, force=True)
    olds = [p for p in env["sdk"].parent.iterdir() if ".old." in p.name]
    assert len(olds) == 1 and (olds[0] / "marker").exists() and not (env["sdk"] / "marker").exists()
    assert any("was kept as" in m for m in msgs)


def test_an_older_ascp_in_the_directory_is_replaced_and_kept(env):
    env["sdk"].mkdir(parents=True)
    old = env["sdk"] / "ascp"
    old.write_text("#!/bin/sh\necho 'ascp version 4.4.2.550 x'\n")
    old.chmod(0o755)
    _install(env, assume_yes=True)
    assert classic.ascp_version(str(env["sdk"] / "ascp"))[:3] == (4, 4, 8)
    assert len([p for p in env["sdk"].parent.iterdir() if ".old." in p.name]) == 1


def test_an_archive_that_installs_an_old_ascp_is_refused(env):
    old = _archive(version="ascp version 4.4.2.550 x")
    env["pin"](old)
    with pytest.raises(ai.AscpInstallError, match="reports 4.4.2.550"):
        _install(env, assume_yes=True, sdk_bytes=old)
    assert not env["sdk"].exists()


def test_an_archive_without_ascp_or_license_is_refused(env):
    bad = _archive(omit=("etc/aspera-license",))
    env["pin"](bad)
    with pytest.raises(ai.AscpInstallError, match="no aspera-license"):
        _install(env, assume_yes=True, sdk_bytes=bad)


def test_only_named_members_are_written_and_path_tricks_are_ignored(env, tmp_path):
    evil = _archive(extra={"../../escaped.txt": b"x", "/abs/escaped2.txt": b"y"})
    env["pin"](evil)
    _install(env, assume_yes=True, sdk_bytes=evil)
    assert not (tmp_path / "escaped.txt").exists() and not (tmp_path.parent / "escaped.txt").exists()
    assert "async" not in [p.name for p in env["sdk"].iterdir()]


def test_der_to_pem_roundtrip():
    import base64
    pem = ai.der_to_pem(FAKE_DER)
    body = "".join(pem.splitlines()[1:-1])
    assert base64.b64decode(body) == FAKE_DER


def test_cli_install_ascp_yes(env, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(ai, "install_ascp", lambda **kw: calls.append(kw) or env["sdk"] / "ascp")
    assert cli.main(["--install-ascp", "--yes"]) == 0
    assert calls and calls[0]["assume_yes"] is True


def test_cli_install_ascp_reports_a_refusal_with_exit_1(env, monkeypatch, capsys):
    def refuse(**kw):
        raise ai.AscpInstallError("Not a terminal", "Run it with --yes")
    monkeypatch.setattr(ai, "install_ascp", refuse)
    assert cli.main(["--install-ascp"]) == 1
    out = capsys.readouterr()
    assert "Not a terminal" in (out.out + out.err) and "--yes" in (out.out + out.err)


def test_a_library_alias_symlink_is_recreated_and_an_escaping_one_is_not(env):
    _install(env, assume_yes=True)
    link = env["sdk"] / "libstdc++.so.6"
    assert link.is_symlink() and os.readlink(link) == "libstdc++.so.6.0.28" and link.read_bytes() == b"lib3"
    evil = _archive(extra={"lib/libstdc++.so.6": ("symlink", "../../../etc/passwd")})
    env["pin"](evil)
    other = env["sdk"].parent / "sdk2"
    ai.install_ascp(sdk_dir=other, sdk_bytes=evil, key_bytes=FAKE_DER, assume_yes=True, say=lambda m: None)
    assert not (other / "libstdc++.so.6").exists() and not (other / "libstdc++.so.6").is_symlink()


def test_install_directory_is_not_private_to_the_temp_name(env):
    _install(env, assume_yes=True)
    assert stat.S_IMODE(env["sdk"].stat().st_mode) == 0o755
