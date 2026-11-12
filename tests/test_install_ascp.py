"""``adaptiseq --install-ascp``: offline, with fake SDK archives and fake key data (the real ones are pinned
by sha256 in adaptiseq/ascp_install.py; the Linux x86_64 and macOS arm64 builds were run against ENA)."""
import hashlib
import io
import os
import ssl
import stat
import tarfile
import urllib.error
import zipfile

import pytest

from adaptiseq import ascp_install as ai
from adaptiseq import cli
from adaptiseq.engine import classic

FAKE_DER = bytes(range(200))
PLATS = ["linux-x86_64", "osx-arm64"]


def _members(version):
    return {
        "bin/ascp": f"#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo '{version}'; fi\nexit 0\n".encode(),
        "bin/async": b"not wanted",
        "etc/aspera-license": b"license",
        "etc/aspera.conf": b"conf",
        "api/go/example.go": b"sample",
    }


def _archive(plat, version="ascp version 4.4.8.2592 x", extra=None, omit=()):
    """A fake SDK archive for ``plat`` in the format IBM uses for it (tar.gz on Linux, zip on macOS)."""
    spec = ai.PLATFORMS[plat]
    members = _members(version)
    if plat == "linux-x86_64":
        members.update({"lib/libafwsfeed.so": b"lib1", "lib/libstdc++.so.6": ("symlink", "libstdc++.so.6.0.28"),
                        "lib/libstdc++.so.6.0.28": b"lib3"})
    else:
        members["lib/libafwsfeed.dylib"] = b"dylib"
    members.update(extra or {})
    buf = io.BytesIO()
    if spec["kind"] == "zip":
        with zipfile.ZipFile(buf, "w") as zf:
            for name, data in members.items():
                if name in omit:
                    continue
                full = name if (name.startswith("/") or "../" in name) else spec["prefix"] + name
                if isinstance(data, tuple):
                    info = zipfile.ZipInfo(full)
                    info.external_attr = (0o120777 << 16)
                    zf.writestr(info, data[1])
                else:
                    info = zipfile.ZipInfo(full)
                    info.external_attr = (0o755 << 16) if name == "bin/ascp" else (0o644 << 16)
                    zf.writestr(info, data)
    else:
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, data in members.items():
                if name in omit:
                    continue
                full = name if (name.startswith("/") or "../" in name) else spec["prefix"] + name
                info = tarfile.TarInfo(full)
                if isinstance(data, tuple):
                    info.type = tarfile.SYMTYPE
                    info.linkname = data[1]
                    tar.addfile(info)
                    continue
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture(params=PLATS)
def env(request, tmp_path, monkeypatch):
    plat = request.param
    sdk = tmp_path / "home" / ".aspera" / "sdk"
    monkeypatch.setattr(classic, "SDK_DIR", sdk)
    monkeypatch.setattr(ai, "platform_key", lambda: plat)
    classic._ascp_versions.clear()

    def pin(arch=None, key=FAKE_DER):
        arch = arch if arch is not None else _archive(plat)
        monkeypatch.setitem(ai.PLATFORMS[plat], "sha256", hashlib.sha256(arch).hexdigest())
        monkeypatch.setattr(ai, "KEY_DATA_SHA256", hashlib.sha256(key).hexdigest())
    archive = _archive(plat)
    pin(archive)
    return dict(sdk=sdk, archive=archive, pin=pin, plat=plat, spec=ai.PLATFORMS[plat])


def _install(env, **kw):
    msgs = []
    path = ai.install_ascp(sdk_dir=env["sdk"], sdk_bytes=kw.pop("sdk_bytes", env["archive"]),
                           key_bytes=kw.pop("key_bytes", FAKE_DER), say=msgs.append, **kw)
    return path, msgs


def test_install_writes_the_flat_layout_with_a_private_key(env):
    path, msgs = _install(env, assume_yes=True)
    sdk = env["sdk"]
    expected = set(env["spec"]["wanted"].values()) | {ai.KEY_FILE}
    assert path == sdk / "ascp"
    assert {p.name for p in sdk.iterdir()} == expected
    assert os.access(path, os.X_OK)
    assert stat.S_IMODE((sdk / ai.KEY_FILE).stat().st_mode) == 0o600
    assert stat.S_IMODE(sdk.stat().st_mode) == 0o755
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


def test_notice_names_the_platform_source_checksums_and_terms(env):
    _, msgs = _install(env, assume_yes=True)
    text = msgs[0]
    assert env["spec"]["url"] in text and env["spec"]["label"] in text and ai.KEY_URL in text and str(env["sdk"]) in text
    assert "IBM's terms" in text and "does not redistribute" in text and "sha256" in text


def test_a_checksum_mismatch_installs_nothing(env):
    other = _archive(env["plat"], extra={"etc/aspera.conf": b"tampered"})
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
    old = _archive(env["plat"], version="ascp version 4.4.2.550 x")
    env["pin"](old)
    with pytest.raises(ai.AscpInstallError, match="reports 4.4.2.550"):
        _install(env, assume_yes=True, sdk_bytes=old)
    assert not env["sdk"].exists()


def test_an_archive_without_ascp_or_license_is_refused(env):
    bad = _archive(env["plat"], omit=("etc/aspera-license",))
    env["pin"](bad)
    with pytest.raises(ai.AscpInstallError, match="no aspera-license"):
        _install(env, assume_yes=True, sdk_bytes=bad)


def test_only_named_members_are_written_and_path_tricks_are_ignored(env, tmp_path):
    evil = _archive(env["plat"], extra={"../../escaped.txt": b"x", "/abs/escaped2.txt": b"y"})
    env["pin"](evil)
    _install(env, assume_yes=True, sdk_bytes=evil)
    assert not (tmp_path / "escaped.txt").exists() and not (tmp_path.parent / "escaped.txt").exists()
    assert "async" not in [p.name for p in env["sdk"].iterdir()]


def test_a_symlink_in_the_archive_is_never_followed_out_of_the_directory(env):
    evil = _archive(env["plat"], extra={"lib/libafwsfeed.so": ("symlink", "../../../etc/passwd"),
                                        "lib/libafwsfeed.dylib": ("symlink", "../../../etc/passwd"),
                                        "etc/aspera.conf": ("symlink", "/etc/passwd")})
    env["pin"](evil)
    _install(env, assume_yes=True, sdk_bytes=evil)
    for p in env["sdk"].iterdir():
        assert not p.is_symlink() or os.readlink(p) in env["spec"]["wanted"].values()


def test_linux_library_alias_is_recreated(env):
    if env["plat"] != "linux-x86_64":
        pytest.skip("Linux archive only")
    _install(env, assume_yes=True)
    link = env["sdk"] / "libstdc++.so.6"
    assert link.is_symlink() and os.readlink(link) == "libstdc++.so.6.0.28" and link.read_bytes() == b"lib3"


def test_der_to_pem_roundtrip():
    import base64
    pem = ai.der_to_pem(FAKE_DER)
    assert base64.b64decode("".join(pem.splitlines()[1:-1])) == FAKE_DER


# ------------------------------- platforms --------------------------------------

@pytest.mark.parametrize("system,machine,key", [
    ("linux", "x86_64", "linux-x86_64"), ("linux", "AMD64", "linux-x86_64"), ("darwin", "arm64", "osx-arm64"),
    ("darwin", "x86_64", None), ("linux", "aarch64", None), ("win32", "AMD64", None)])
def test_platform_detection(system, machine, key, monkeypatch):
    monkeypatch.setattr("sys.platform", system)
    monkeypatch.setattr(ai.platform, "machine", lambda: machine)
    assert ai.platform_key() == key


def test_intel_mac_is_refused_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(ai.platform, "machine", lambda: "x86_64")
    with pytest.raises(ai.AscpInstallError, match="Intel Macs are not supported") as exc:
        ai.install_ascp(sdk_dir=tmp_path / "sdk", assume_yes=True)
    assert "Aspera Connect" in exc.value.solution
    assert not (tmp_path / "sdk").exists()


def test_other_platforms_are_refused_and_named(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(ai.platform, "machine", lambda: "AMD64")
    with pytest.raises(ai.AscpInstallError, match="Linux x86_64, macOS Apple silicon"):
        ai.install_ascp(sdk_dir=tmp_path / "sdk", assume_yes=True)


def test_every_platform_entry_is_complete_and_https():
    for key, spec in ai.PLATFORMS.items():
        assert spec["url"].startswith("https://") and len(spec["sha256"]) == 64 and spec["kind"] in ("tar.gz", "zip")
        assert spec["url"].endswith(".zip" if spec["kind"] == "zip" else ".tar.gz")
        assert spec["prefix"].endswith("/") and {"ascp", "aspera-license"} <= set(spec["wanted"].values())


# ------------------------------- downloading ------------------------------------

def test_a_certificate_failure_says_how_to_fix_it_and_never_falls_back_to_unverified(monkeypatch):
    def boom(req, timeout=None, context=None):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get local issuer certificate"))
    monkeypatch.setattr(ai.urllib.request, "urlopen", boom)
    monkeypatch.setitem(__import__("sys").modules, "certifi", None)          # certifi not installed
    with pytest.raises(ai.AscpInstallError) as exc:
        ai._download("https://example.invalid/x", "0" * 64, 100, "SDK archive")
    assert "Install Certificates.command" in str(exc.value) and "certifi" in str(exc.value)


def test_certifi_is_used_when_the_default_certificates_fail(monkeypatch):
    calls = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n): return b"payload"

    def fake(req, timeout=None, context=None):
        calls.append(context)
        if context is None:
            raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get local issuer certificate"))
        return Resp()
    monkeypatch.setattr(ai.urllib.request, "urlopen", fake)
    fake_certifi = type("C", (), {"where": staticmethod(lambda: ssl.get_default_verify_paths().cafile or "/nonexistent")})
    monkeypatch.setitem(__import__("sys").modules, "certifi", fake_certifi)
    monkeypatch.setattr(ai.ssl, "create_default_context", lambda cafile=None: ("ctx", cafile))
    assert ai._open("https://example.invalid/x", 100) == b"payload"
    assert calls[0] is None and calls[1][0] == "ctx"


def test_other_network_errors_are_reported_without_retrying(monkeypatch):
    def boom(req, timeout=None, context=None):
        raise urllib.error.URLError("Name or service not known")
    monkeypatch.setattr(ai.urllib.request, "urlopen", boom)
    with pytest.raises(ai.AscpInstallError, match="Could not download"):
        ai._download("https://example.invalid/x", "0" * 64, 100, "SDK archive")


# ------------------------------------ CLI ---------------------------------------

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
