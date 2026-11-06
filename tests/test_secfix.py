"""Privacy-review fixes: private temp files, trusted ./constellation.json, overlapping secrets, 0700 cache, ready check."""

import os
import stat

from constellation import scanfile
from constellation.redact import REDACTED, redact
from constellation.report import write_private


def test_overlapping_known_secrets_leave_no_tail():
    assert redact("xxsecret1234567", ["xxsecret1", "secret1234567"]) == REDACTED
    assert redact("a secret1234567 b", ["secret12", "ret1234567"]) == f"a {REDACTED} b"
    assert redact("abcdefgh and abcdefgh", ["abcdefgh"]) == f"{REDACTED} and {REDACTED}"
    assert redact("abcdefghXYZ12345", ["abcdefgh", "XYZ12345"]) == REDACTED * 2


def test_atomic_write_ignores_a_planted_link_at_the_old_temp_name(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    out = tmp_path / "constellation.json"
    (tmp_path / "constellation.json.tmp").symlink_to(victim)
    scanfile.write_atomic(out, "new")
    write_private(out, "newer")
    assert victim.read_text() == "keep" and out.read_text() == "newer"
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["constellation.json", "constellation.json.tmp", "victim.txt"]


def test_write_failure_removes_its_temp_file(tmp_path):
    out = tmp_path / "dir"
    out.mkdir()  # os.replace of a file onto a directory fails
    try:
        scanfile.write_atomic(out, "x")
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError")
    assert [p.name for p in tmp_path.iterdir()] == ["dir"]


def test_remember_does_not_follow_a_planted_pointer_link(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    pointer = scanfile._pointer()
    pointer.parent.mkdir(parents=True)
    pointer.symlink_to(victim)
    scanfile.remember(tmp_path / "scan.json")
    assert victim.read_text() == "keep"


def test_remember_writes_a_private_pointer_in_a_private_folder(tmp_path):
    scanfile.remember(tmp_path / "scan.json")
    assert stat.S_IMODE(scanfile._pointer().stat().st_mode) == 0o600
    assert stat.S_IMODE(scanfile._pointer().parent.stat().st_mode) == 0o700
    assert scanfile._pointer().read_text() == str((tmp_path / "scan.json").resolve())


def test_private_dir_tightens_an_existing_folder(tmp_path):
    folder = tmp_path / "c"
    folder.mkdir(mode=0o755)
    scanfile.private_dir(folder / "sub")
    scanfile.private_dir(folder)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700 and stat.S_IMODE((folder / "sub").stat().st_mode) == 0o700


def _setup(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    remembered = tmp_path / "remembered.json"
    remembered.write_text("{}")
    scanfile.remember(remembered)
    return work, remembered.resolve()


def test_a_group_readable_local_scan_is_not_trusted(tmp_path, monkeypatch, capsys):
    work, remembered = _setup(tmp_path, monkeypatch)
    local = work / "constellation.json"
    local.write_text("{}")
    local.chmod(0o644)
    assert scanfile.latest_scan() == remembered
    assert scanfile.target() == scanfile.default_out()
    err = capsys.readouterr().err
    assert err.count("ignoring ./constellation.json") == 2 and "\n" == err[-1] and err.count("\n") == 2
    local.chmod(0o600)
    assert scanfile.latest_scan() == scanfile.LOCAL and scanfile.target() == scanfile.LOCAL
    assert capsys.readouterr().err == ""


def test_a_symlinked_local_scan_is_not_trusted(tmp_path, monkeypatch):
    work, remembered = _setup(tmp_path, monkeypatch)
    real = tmp_path / "real.json"
    real.write_text("{}")
    real.chmod(0o600)
    (work / "constellation.json").symlink_to(real)
    assert scanfile.latest_scan() == remembered
    assert scanfile.target() == scanfile.default_out()


def test_an_absent_local_scan_is_silent(tmp_path, monkeypatch, capsys):
    _, remembered = _setup(tmp_path, monkeypatch)
    assert scanfile.latest_scan() == remembered and scanfile.target() == scanfile.default_out()
    assert capsys.readouterr().err == ""


def test_a_local_scan_owned_by_someone_else_is_not_trusted(tmp_path, monkeypatch):
    work, remembered = _setup(tmp_path, monkeypatch)
    (work / "constellation.json").write_text("{}")
    (work / "constellation.json").chmod(0o600)
    monkeypatch.setattr(os, "getuid", lambda: os.stat(work).st_uid + 1)
    assert scanfile.latest_scan() == remembered


def _fake_server(started_after_run):
    import time

    class Fake:
        def __init__(self, config):
            self.started = False
            self.should_exit = False

        def run(self):
            if started_after_run:
                self.started = True
                time.sleep(0.3)
                return
            while not self.should_exit:
                time.sleep(0.01)

    return Fake


def test_serve_trusts_the_server_started_flag_not_an_open_port(monkeypatch, capsys):
    import socket

    import uvicorn

    from constellation import opener, server

    real = opener.wait_ready
    monkeypatch.setattr(opener, "wait_ready", lambda *a, **k: real(*a, timeout=0.3, **k))
    with socket.socket() as squatter:  # something else already listens on the port
        squatter.bind(("127.0.0.1", 0))
        squatter.listen()
        port = squatter.getsockname()[1]
        monkeypatch.setattr(uvicorn, "Server", _fake_server(False))
        server.serve(None, port, False)  # type: ignore[arg-type]
    assert capsys.readouterr().err == f"  Could not start the server on port {port} (is it already in use?).\n"


def test_serve_announces_once_the_server_has_started(monkeypatch, capsys):
    import uvicorn

    from constellation import server

    monkeypatch.setattr(uvicorn, "Server", _fake_server(True))
    server.serve(None, 8765, False)  # type: ignore[arg-type]
    assert "http://127.0.0.1:8765/" in capsys.readouterr().out


def test_profile_without_a_saved_scan_says_so(tmp_path, monkeypatch, capsys):
    from constellation import cli, habits, history

    config = tmp_path / "cfg"
    (config / "projects" / "-x-app").mkdir(parents=True)
    ledger = tmp_path / "h.json"
    habits.save(ledger, {history.key(str(config.resolve())): {"salt": "b" * 64, "days": {}, "co": {}, "items": {}}})
    monkeypatch.chdir(tmp_path)
    assert cli.main(["profile", "app", "--config-dir", str(config), "--habits", str(ledger)]) == 2
    assert "is missing or not a constellation scan" in capsys.readouterr().err
