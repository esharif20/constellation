"""#79: bounded hostile inputs, using temporary invented setups and public seams only."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fakes import write_skill
from hypothesis import Phase, given, settings
from hypothesis import strategies as st

from constellation import scan
from constellation import usage as usage_reader

CANARY = "sk-ant-HOSTILE-CANARY-0123456789abcdef0123456789"
BOUNDED = settings(max_examples=8, deadline=500, derandomize=True, database=None, phases=(Phase.generate,))
PLUGIN_MANIFEST = "plugins/cache/invented-market/invented-plugin/1/.claude-plugin/plugin.json"


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def clean_result(result):
    assert CANARY not in repr(result)
    assert any(i.name == "survivor" for i in result.items), "one bad file must not prevent valid siblings from being read"
    assert any(not warning.startswith("Offline:") for warning in result.warnings), "a rejected input needs a warning"


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param(
            "settings.json",
            marks=pytest.mark.xfail(
                strict=True,
                raises=json.JSONDecodeError,
                reason="claude_code.py:482 parses malformed settings during secret collection without recovery",
            ),
        ),
        pytest.param(
            ".credentials.json",
            marks=pytest.mark.xfail(
                strict=True, raises=json.JSONDecodeError, reason="claude_code.py:498 parses malformed credentials without recovery"
            ),
        ),
        ".claude.json",
        ".mcp.json",
        "plugins/installed_plugins.json",
        PLUGIN_MANIFEST,
    ],
)
@BOUNDED
@given(suffix=st.text(alphabet="abc!{}[]", max_size=40))
def test_malformed_json_is_warned_without_aborting_the_scan(filename, suffix):
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        write_skill(root, "survivor", "Invented valid sibling")
        put(root / filename, ('{"private":"' + CANARY + '","broken":!' + suffix).encode())
        clean_result(scan(root, offline=True, origins=False))


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param(
            "settings.json",
            marks=pytest.mark.xfail(
                strict=True,
                raises=UnicodeDecodeError,
                reason="claude_code.py:482 reads non-UTF-8 settings during secret collection without recovery",
            ),
        ),
        pytest.param(
            ".credentials.json",
            marks=pytest.mark.xfail(
                strict=True, raises=UnicodeDecodeError, reason="claude_code.py:498 reads non-UTF-8 credentials without recovery"
            ),
        ),
        ".claude.json",
        ".mcp.json",
        "plugins/installed_plugins.json",
        PLUGIN_MANIFEST,
    ],
)
@BOUNDED
@given(raw=st.sampled_from([b"\xff\xfe", b"\x80", b"\xc0\xaf", b"\xed\xa0\x80"]))
def test_invalid_utf8_is_warned_without_aborting_the_scan(filename, raw):
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        write_skill(root, "survivor", "Invented valid sibling")
        put(root / filename, raw + CANARY.encode())
        clean_result(scan(root, offline=True, origins=False))


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param(
            "settings.json",
            marks=pytest.mark.xfail(strict=True, raises=AttributeError, reason="claude_code.py:482 assumes the settings root is an object"),
        ),
        pytest.param(
            ".claude.json",
            marks=pytest.mark.xfail(
                strict=True, raises=AssertionError, reason="claude_code.py:166 silently ignores a non-object .claude.json without a warning"
            ),
        ),
        ".mcp.json",
        "plugins/installed_plugins.json",
        PLUGIN_MANIFEST,
    ],
)
@BOUNDED
@given(depth=st.integers(min_value=5000, max_value=5050))
def test_deep_json_is_warned_without_aborting_the_scan(filename, depth):
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        write_skill(root, "survivor", "Invented valid sibling")
        put(root / filename, b"[" * depth + json.dumps(CANARY).encode() + b"]" * depth)
        clean_result(scan(root, offline=True, origins=False))


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param(
            "hooks-list",
            marks=pytest.mark.xfail(strict=True, raises=AttributeError, reason="claude_code.py:313 assumes hooks is an object"),
        ),
        pytest.param(
            "groups-null",
            marks=pytest.mark.xfail(strict=True, raises=TypeError, reason="claude_code.py:314 assumes hook groups are iterable"),
        ),
        pytest.param(
            "handler-without-type",
            marks=pytest.mark.xfail(strict=True, raises=KeyError, reason="claude_code.py:322 indexes a missing hook handler type"),
        ),
    ],
)
@BOUNDED
@given(private=st.text(alphabet="abcXYZ012", max_size=30))
def test_bad_hook_shapes_are_warned_and_valid_items_survive(shape, private):
    hooks = (
        []
        if shape == "hooks-list"
        else {"SessionStart": None if shape == "groups-null" else [{"hooks": [{"command": "echo " + CANARY + private}]}]}
    )
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        write_skill(root, "survivor", "Invented valid sibling")
        put(root / "settings.json", json.dumps({"hooks": hooks}).encode())
        clean_result(scan(root, offline=True, origins=False))


@pytest.mark.parametrize("kind", ["syntax", "encoding", "deep", "line-cap", "file-cap"])
@BOUNDED
@given(extra=st.integers(min_value=1, max_value=64))
def test_hostile_transcripts_are_bounded_warned_and_do_not_hide_a_valid_sibling(kind, extra):
    # Small caps exercise the real oversize paths without creating large files.
    with TemporaryDirectory() as scratch, pytest.MonkeyPatch.context() as patch:
        patch.setattr(usage_reader, "LINE_CAP", 512)
        patch.setattr(usage_reader, "FILE_CAP", 8192)
        root = Path(scratch)
        write_skill(root, "survivor", "Invented valid sibling")
        record = {
            "type": "assistant",
            "timestamp": "2026-11-05T12:00:00Z",
            "message": {"content": [{"type": "tool_use", "id": "invented-valid", "name": "Skill", "input": {"skill": "survivor"}}]},
        }
        put(root / "projects/invented/valid.jsonl", (json.dumps(record) + "\n").encode())
        if kind == "syntax":
            raw = b'{"tool_use": !' + CANARY.encode() + b"x" * extra
        elif kind == "encoding":
            raw = b'{"tool_use": "\xff' + CANARY.encode() + b"x" * extra
        elif kind == "deep":
            # Reach the JSON/shape guards rather than the oversize guard.
            patch.setattr(usage_reader, "FILE_CAP", 16384)
            patch.setattr(usage_reader, "LINE_CAP", 16384)
            raw = b"[" * (5000 + extra) + b'{"tool_use":0}' + b"]" * (5000 + extra)
        elif kind == "line-cap":
            raw = CANARY.encode() + b"x" * (512 + extra)
        else:
            raw = CANARY.encode() + b"x" * (8192 + extra)
        put(root / "projects/invented/hostile.jsonl", raw + b"\n")
        result = scan(root, offline=True, origins=False)
        clean_result(result)
        assert result.usage["claude-code:skill:survivor"].count == 1
        assert result.usage_window.files == (1 if kind == "file-cap" else 2)


@pytest.mark.parametrize("location", ["projects", "project-folder", "transcript", "subagent-folder"])
@BOUNDED
@given(suffix=st.text(alphabet="abc012", min_size=1, max_size=8))
def test_transcript_symlinks_are_not_followed_even_when_the_target_is_temporary(location, suffix):
    with TemporaryDirectory() as scratch:
        base = Path(scratch)
        root = base / "config"
        write_skill(root, "survivor", "Invented valid sibling")
        target = base / ("invented-target-" + suffix)
        target.mkdir()
        raw = json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-11-05T12:00:00Z",
                "message": {"content": [{"type": "tool_use", "id": CANARY, "name": "Skill", "input": {"skill": "survivor"}}]},
            }
        ).encode()
        put(target / "outside.jsonl", raw)
        if location == "projects":
            link = root / "projects"
        elif location == "project-folder":
            link = root / "projects/invented"
        elif location == "subagent-folder":
            link = root / "projects/invented/session/subagents"
        else:
            link = root / "projects/invented/linked.jsonl"
            target = target / "outside.jsonl"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target, target_is_directory=location != "transcript")
        result = scan(root, offline=True, origins=False)
        clean_result(result)
        assert result.usage["claude-code:skill:survivor"].count == 0
        assert result.usage_window.skipped == 1


@BOUNDED
@given(extra=st.integers(min_value=65536, max_value=69632))
def test_large_malformed_mcp_json_is_warned_without_echoing_its_content(extra):
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        write_skill(root, "survivor", "Invented valid sibling")
        put(root / ".mcp.json", b"\n" * extra + b'{"private":"' + CANARY.encode() + b'",!')
        clean_result(scan(root, offline=True, origins=False))


@pytest.mark.parametrize(
    "location",
    [
        "skill",
        "mcp-file",
        pytest.param(
            "manifest",
            marks=pytest.mark.xfail(
                strict=True, raises=AssertionError, reason="claude_code.py:380 follows plugin manifest symlinks outside the plugin root"
            ),
        ),
    ],
)
def test_plugin_symlinks_cannot_read_a_sibling_outside_the_plugin(tmp_path, location):
    root = tmp_path / "config"
    write_skill(root, "survivor", "Invented valid sibling")
    plugin = root / "plugins/cache/invented-market/invented-plugin/1"
    put(plugin / ".claude-plugin/plugin.json", json.dumps({"name": "invented-plugin"}).encode())
    target = tmp_path / "invented-private-target"
    if location == "skill":
        target.write_text(f"---\nname: forbidden-symlink\ndescription: {CANARY}\n---\nInvented body")
        link = plugin / "skills/linked/SKILL.md"
    elif location == "manifest":
        target.write_text(json.dumps({"name": "forbidden-symlink", "description": CANARY}))
        link = plugin / ".claude-plugin/plugin.json"
        link.unlink()
    else:
        target.write_text(json.dumps({"mcpServers": {"forbidden-symlink": {"command": "invented"}}}))
        link = plugin / ".mcp.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    result = scan(root, offline=True, origins=False)
    clean_result(result)
    assert all(i.name != "forbidden-symlink" for i in result.items)


@pytest.mark.parametrize("field", ["tool-id", "user-uuid"])
@BOUNDED
@given(surrogate=st.integers(min_value=0xD800, max_value=0xDFFF).map(chr))
def test_json_surrogates_in_transcript_ids_are_warned_instead_of_crashing(field, surrogate):
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        write_skill(root, "survivor", "Invented valid sibling")
        if field == "tool-id":
            record = {
                "type": "assistant",
                "timestamp": "2026-11-05T12:00:00Z",
                "message": {"content": [{"type": "tool_use", "id": surrogate, "name": "Skill", "input": {"skill": "survivor"}}]},
            }
        else:
            record = {
                "type": "user",
                "uuid": surrogate,
                "timestamp": "2026-11-05T12:00:00Z",
                "message": {"content": "<command-name>/survivor</command-name>"},
            }
        put(root / "projects/invented/hostile.jsonl", (json.dumps(record) + "\n").encode())
        clean_result(scan(root, offline=True, origins=False))


@pytest.mark.xfail(strict=True, raises=RecursionError, reason="claude_code.py:467 recursively walks credentials without a depth bound")
def test_deep_credentials_are_warned_without_crashing(tmp_path):
    # A fixed reproducer avoids Hypothesis's changing recursion limit and traceback locations during replay.
    write_skill(tmp_path, "survivor", "Invented valid sibling")
    put(tmp_path / ".credentials.json", b"[" * 5000 + json.dumps(CANARY).encode() + b"]" * 5000)
    try:
        result = scan(tmp_path, offline=True, origins=False)
    except RecursionError:
        # Keep pytest from formatting thousands of repeated frames for this known failure.
        raise RecursionError("credential nesting exceeded the reader's recursion bound") from None
    clean_result(result)
