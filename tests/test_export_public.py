import json
import stat

import pytest

from constellation import public_export
from constellation.cli import main


@pytest.fixture
def export_fixture(tmp_path, monkeypatch):
    static = tmp_path / "invented-build"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text('<html><head><script type="module" src="./assets/app.js"></script></head><body></body></html>')
    (static / "assets/app.js").write_text('fetch("api/constellation")')
    monkeypatch.setattr(public_export, "STATIC", static)

    def forbidden(*args, **kwargs):
        raise AssertionError("Export must not read setup, environment or providers")

    monkeypatch.setattr("constellation.cli.load_env", forbidden)
    monkeypatch.setattr("constellation.cli.read_secrets", forbidden)
    monkeypatch.setattr("constellation.cli.scan", forbidden)
    saved = tmp_path / "invented-scan.json"
    saved.write_text(
        json.dumps({"items": [{"id": "private-id", "kind": "skill", "name": "Invented", "description": "Demo", "source": "local"}]})
    )
    return saved, tmp_path / "public", static


def test_export_writes_read_only_snapshot_directory_and_free_text_notice(export_fixture, capsys):
    saved, out, _ = export_fixture
    original = saved.read_bytes()

    assert main(["export", "--public", str(saved), "--out", str(out)]) == 0

    data = json.loads((out / "api/constellation").read_text())
    assert data["items"] == [{"id": "item-1", "kind": "skill", "name": "Invented", "description": "Demo", "source": ""}]
    assert (out / "assets/app.js").is_file()
    assert {p.name for p in out.iterdir()} == {"api", "assets", "index.html", "snapshot-readonly.js", "README.txt"}
    assert {p.name for p in (out / "api").iterdir()} == {"constellation"}
    assert (out / "index.html").read_text() == (
        '<html><head><script type="module" src="./assets/app.js"></script>'
        '<script src="./snapshot-readonly.js"></script></head><body></body></html>'
    )
    assert "does NOT anonymise free text" in (out / "README.txt").read_text()
    assert "does NOT anonymise free text" in capsys.readouterr().out
    assert saved.read_bytes() == original
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out.rglob("*") if p.is_file())


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "dangling"])
def test_export_never_replaces_existing_output(export_fixture, tmp_path, capsys, kind):
    saved, out, _ = export_fixture
    target = tmp_path / "invented-target"
    if kind == "directory":
        out.mkdir()
        (out / "keep.txt").write_text("keep")
    elif kind == "file":
        out.write_text("keep")
    else:
        if kind == "symlink":
            target.mkdir()
            (target / "keep.txt").write_text("keep")
        out.symlink_to(target, target_is_directory=True)
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 2
    assert "already exists" in capsys.readouterr().err
    if kind == "directory":
        assert [p.name for p in out.iterdir()] == ["keep.txt"]
        assert (out / "keep.txt").read_text() == "keep"
    elif kind == "file":
        assert out.read_text() == "keep"
    elif kind == "symlink":
        assert [p.name for p in target.iterdir()] == ["keep.txt"]
    else:
        assert out.is_symlink() and not target.exists()


@pytest.mark.parametrize("missing", ["--public", "--out"])
def test_export_requires_explicit_public_mode_and_output(export_fixture, missing):
    saved, out, _ = export_fixture
    args = ["export", str(saved)]
    args += ["--public"] if missing == "--out" else ["--out", str(out)]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert not out.exists()


@pytest.mark.parametrize(
    "failure",
    [
        "missing_index",
        "invalid_index",
        "missing_assets",
        "linked_index",
        "linked_asset",
        "linked_assets",
        "index_case",
        "assets_case",
    ],
)
def test_export_rejects_incomplete_or_linked_build_before_creating_output(export_fixture, tmp_path, failure):
    saved, out, static = export_fixture
    if failure == "missing_index":
        (static / "index.html").unlink()
    elif failure == "invalid_index":
        (static / "index.html").write_text("not a frontend build")
    elif failure == "missing_assets":
        (static / "assets/app.js").unlink()
    elif failure == "index_case":
        (static / "index.html").rename(static / "INDEX.HTML")
    elif failure == "assets_case":
        (static / "assets").rename(static / "ASSETS")
    elif failure == "linked_assets":
        private = tmp_path / "invented-private-build"
        private.mkdir()
        (private / "app.js").write_text("must not enter the Snapshot")
        (static / "assets/app.js").unlink()
        (static / "assets").rmdir()
        (static / "assets").symlink_to(private, target_is_directory=True)
    else:
        private = tmp_path / "invented-private-file"
        private.write_text("must not enter the Snapshot")
        path = static / ("index.html" if failure == "linked_index" else "assets/app.js")
        path.unlink()
        path.symlink_to(private)
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 2
    assert not out.exists()


def test_export_copies_build_assets_only_and_never_writes_inside_claude(export_fixture, tmp_path):
    saved, out, static = export_fixture
    (static / "private.json").write_text("invented-private-data")
    (static / "assets/private.json").write_text("invented-private-data")
    (static / "assets/nested.js/a/b").mkdir(parents=True)
    (static / "assets/nested.js/a/b/font.woff2").write_bytes(b"invented-font")
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 0
    assert not (out / "private.json").exists()
    assert not (out / "assets/private.json").exists()
    assert (out / "assets/nested.js/a/b/font.woff2").read_bytes() == b"invented-font"
    config = tmp_path / ".claude"
    config.mkdir()
    assert main(["export", "--public", str(saved), "--out", str(config / "public")]) == 2
    assert list(config.iterdir()) == []


@pytest.mark.parametrize(
    "attack",
    [
        "/Users/invented-person/notes",
        "'/home/invented person/private notes'",
        r"D:\work\invented-person\notes",
        "ｄｂ．ｉｎｔｅｒｎａｌ",
        "db\u3002corp",
        "192.168.25.3:5432",
        "dbhost:5432",
        "2001:db8:85a3:0:0:8a2e:370:7334",
        "fe80::1ff:fe23:4567:890a",
        "::1",
        "https://invented-user:invented-password@db.internal/private",
        "person\uff20example.test",
    ],
)
def test_export_scrubs_nfkc_paths_hosts_and_ipv6_in_every_retained_field(export_fixture, attack):
    saved, out, _ = export_fixture
    secret = "ghp_" + "A" * 36
    saved.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "private-id",
                        "kind": "skill",
                        "name": attack,
                        "description": attack,
                        "source": secret,
                        "body": secret,
                        "env": {"TOKEN": secret},
                    }
                ],
                "labels": {"private-id": attack},
                "clusters": [{"name": attack, "item_ids": ["private-id"]}],
                "overlaps": [{"a_id": "private-id", "b_id": "private-id", "verdict": "overlap", "reason": attack}],
                "usage": {"private-id": {"count": 42, "last_used": "2026-11-04"}},
                "warnings": [secret],
            }
        )
    )
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 0
    data = json.loads((out / "api/constellation").read_text())
    assert data["items"][0]["name"] == "[REDACTED]"
    assert data["items"][0]["description"] == "[REDACTED]"
    assert data["labels"] == {"item-1": "[REDACTED]"}
    assert data["clusters"] == [{"name": "[REDACTED]", "item_ids": ["item-1"]}]
    assert data["overlaps"][0]["reason"] == "[REDACTED]"
    assert "usage" not in data and "warnings" not in data
    assert all(secret.encode() not in p.read_bytes() for p in out.rglob("*") if p.is_file())


@pytest.mark.parametrize(
    "text,remaining",
    [
        ("invented-person said hello", "invented-person"),
        (r"C:\Users\invented person\notes", r"person\notes"),
        ("person [at] example [dot] com", "[at]"),
        ("docs.example.com", "docs.example.com"),
        ("//server/share", "//server/share"),
    ],
)
def test_export_documents_limits_instead_of_claiming_free_text_anonymisation(export_fixture, text, remaining):
    saved, out, _ = export_fixture
    data = json.loads(saved.read_text())
    data["items"][0]["description"] = text
    saved.write_text(json.dumps(data))
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 0
    assert remaining in json.loads((out / "api/constellation").read_text())["items"][0]["description"]
    notice = (out / "README.txt").read_text()
    for limit in ("bare usernames", "unquoted paths with spaces", "obfuscated emails", "public hostnames", "//server/share"):
        assert limit in notice


def test_static_snapshot_api_guard_never_sends_search_questions_or_writes(export_fixture):
    import shutil
    import subprocess

    saved, out, _ = export_fixture
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 0
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the static frontend adapter check")
    script = """
      import assert from 'node:assert/strict';
      import fs from 'node:fs';
      import vm from 'node:vm';
      globalThis.document = {baseURI: 'https://snapshot.example.test/demo/'};
      const sent = [];
      globalThis.fetch = async (input) => {
        sent.push(input instanceof Request ? input.url : String(input));
        return new Response('file', {status: 200});
      };
      vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
      for (const endpoint of ['search?q=invented-private', 'chat', 'checklist', 'expand', 'brief', 'constellation?q=invented-private']) {
        const r = await fetch('api/' + endpoint, {method: endpoint.includes('?') ? 'GET' : 'POST'});
        assert.equal(r.status, 404);
        assert.deepEqual(await r.json(), {detail: 'Read-only Snapshot'});
      }
      assert.equal((await fetch(new Request('https://snapshot.example.test/demo/api/constellation', {method:'POST'}))).status, 404);
      assert.equal((await fetch('api/constellation')).status, 200);
      assert.equal((await fetch(new URL('./assets/app.js', document.baseURI))).status, 200);
      assert.equal((await fetch('api/search', {method: 'get'})).status, 404);
      assert.deepEqual(sent, ['api/constellation', 'https://snapshot.example.test/demo/assets/app.js']);
    """
    subprocess.run(
        [node, "--input-type=module", "-e", script, str(out / "snapshot-readonly.js")], check=True, env={"PATH": "/usr/bin:/bin"}
    )


def test_export_disk_failure_is_an_error_and_partial_output_is_not_replaced(export_fixture, monkeypatch, capsys):
    from pathlib import Path

    saved, out, _ = export_fixture
    original = Path.open

    def fail(path, *args, **kwargs):
        if path == out / "api/constellation":
            raise OSError("invented-private-disk-error")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 1
    captured = capsys.readouterr()
    assert "Could not export" in captured.err and "invented-private-disk-error" not in captured.err
    assert "does NOT anonymise" not in captured.out
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 2
    assert "already exists" in capsys.readouterr().err


def test_export_refuses_case_variants_and_the_configured_config_folder(export_fixture, tmp_path, monkeypatch):
    saved, _, _ = export_fixture
    upper = tmp_path / ".CLAUDE"
    upper.mkdir()
    assert main(["export", "--public", str(saved), "--out", str(upper / "public")]) == 2
    custom = tmp_path / "invented-config"
    custom.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(custom))
    assert main(["export", "--public", str(saved), "--out", str(custom / "public")]) == 2
    assert list(upper.iterdir()) == [] and list(custom.iterdir()) == []


def test_export_creates_nested_folders_private_and_prints_limits_and_path(export_fixture, capsys):
    saved, out, static = export_fixture
    (static / "assets/a/b").mkdir(parents=True)
    (static / "assets/a/b/x.js").write_text("1")
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 0
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o700 for p in out.rglob("*") if p.is_dir())
    printed = capsys.readouterr().out
    assert "cluster name" in printed and "bare usernames" in printed and "//server/share" in printed
    assert str(out.resolve()) in printed


def test_export_reads_index_as_utf8(export_fixture, monkeypatch):
    saved, out, _ = export_fixture
    seen = []
    real = public_export.Path.read_text

    def spy(self, *args, **kwargs):
        seen.append((self.name, kwargs.get("encoding")))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(public_export.Path, "read_text", spy)
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 0
    assert ("index.html", "utf-8") in seen


def test_export_outside_a_set_config_folder_still_works(export_fixture, tmp_path, monkeypatch):
    saved, out, _ = export_fixture
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "invented-config"))
    assert main(["export", "--public", str(saved), "--out", str(out)]) == 0
