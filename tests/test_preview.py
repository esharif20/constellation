import json
import math
import os
import stat
from pathlib import Path

import pytest

from constellation import preview as preview_module
from constellation.costs import cache_key, save_cache
from constellation.preview import MAX_ENTRIES, MAX_FILE_BYTES, _plain, check_tree, preview
from constellation.snapshot import snapshot

PACK = Path(__file__).parent / "fixtures" / "preview_pack" / "pdf-kit"
DESC = "d" * 40


def skill(root: Path, name: str, description: str, folder: str | None = None) -> None:
    where = root / "skills" / (folder or name)
    where.mkdir(parents=True, exist_ok=True)
    (where / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nbody\n")


def scan_with(*items: tuple[str, str, str, str]) -> dict:
    return {"items": [{"id": i, "kind": k, "name": n, "description": d, "source": ""} for i, k, n, d in items]}


def concepts(texts):  # one dimension per concept, a third for everything else
    return [[float("pdf" in t), float("zebra" in t), float("pdf" not in t and "zebra" not in t)] for t in texts]


def test_plugin_pack_lists_its_items():
    result = preview(PACK, None)
    assert result["version"] == 1
    assert result["pack"] == {"name": "pdf-kit", "layout": "plugin"}
    assert len(result["items"]) == 5
    assert result["counts"] == {"plugin": 1, "skill": 2, "command": 1, "mcp_server": 1}
    assert {i["id"] for i in result["items"]} >= {"new:claude-code:skill:pdf-kit/trace-canvas"}
    assert result["warnings"] == []


def test_skill_pack_and_single_skill_layouts(tmp_path):
    skill(tmp_path / "pack", "a", "Does a thing.")
    result = preview(tmp_path / "pack", None)
    assert result["pack"] == {"name": "pack", "layout": "pack"}
    assert result["counts"] == {"skill": 1}
    (tmp_path / "one").mkdir()
    (tmp_path / "one" / "SKILL.md").write_text("---\nname: solo\ndescription: Alone.\n---\nbody\n")
    result = preview(tmp_path / "one", None)
    assert result["pack"] == {"name": "one", "layout": "skill"}
    assert [i["name"] for i in result["items"]] == ["solo"]
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "SKILL.md").write_text("---\nname: solo\n---\nbody\n")
    bad = preview(tmp_path / "bad", None)
    assert bad["items"] == [] and bad["warnings"] == ["skipped SKILL.md: it needs a name and a description"]
    (tmp_path / "bad" / "SKILL.md").write_text("no frontmatter\n")
    assert preview(tmp_path / "bad", None)["warnings"][0].startswith("no frontmatter in ")


def test_folder_without_anything_is_refused(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match=r"^No plugin, skill pack or SKILL\.md found in empty\.$"):
        preview(tmp_path / "empty", None)
    # a folder name carrying an escape does not reach the message raw
    odd = tmp_path / "a\x1b[31mb"
    odd.mkdir()
    with pytest.raises(ValueError) as error:
        preview(odd, None)
    assert "\x1b" not in str(error.value)


def test_tokens_estimated_from_text_length(tmp_path):
    skill(tmp_path, "x", DESC)
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {"srv": {"command": "run"}}}')
    result = preview(tmp_path, None)
    by_kind = {i["kind"]: i for i in result["items"]}
    assert by_kind["skill"]["always_on"] == math.ceil(len("x: " + DESC) / 4) == 11
    assert by_kind["skill"]["estimated"] is True
    assert by_kind["mcp_server"]["always_on"] is None and by_kind["mcp_server"]["estimated"] is False
    assert result["always_on"] == {"counted": 0, "estimated": 11, "unknown": 1}


def test_estimate_counts_bytes_not_characters(tmp_path):
    skill(tmp_path, "x", "é" * 10)  # 10 characters, 20 bytes
    assert preview(tmp_path, None)["items"][0]["always_on"] == math.ceil(len(b"x: " + ("é" * 10).encode()) / 4) == 6


def test_cached_count_is_used_and_marked_exact(tmp_path):
    skill(tmp_path / "p", "x", DESC)
    skill(tmp_path / "p", "y", DESC)
    cache = tmp_path / "counts.json"
    save_cache(cache, {cache_key("x: " + DESC, set()): 123})
    result = preview(tmp_path / "p", None, cost_cache=cache)
    exact, estimated = result["items"]
    assert (exact["always_on"], exact["estimated"]) == (123, False)
    assert (estimated["always_on"], estimated["estimated"]) == (11, True)
    assert result["always_on"] == {"counted": 123, "estimated": 11, "unknown": 0}
    assert json.loads(cache.read_text()) == {cache_key("x: " + DESC, set()): 123}  # a preview never writes the cache


def test_hooks_are_unknown_never_zero(tmp_path):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "hooks.json").write_text('{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}')
    result = preview(tmp_path, None)
    assert result["counts"] == {"hook": 1}
    assert result["items"][0]["always_on"] is None
    assert result["always_on"] == {"counted": 0, "estimated": 0, "unknown": 1}


def test_same_name_is_a_possible_overlap():
    scan = scan_with(("s1", "skill", "trace-canvas", "Draws."), ("s2", "agent", "pdf-reader", "Not a skill."))
    result = preview(PACK, scan)
    assert result["compared"] is True
    assert result["overlaps"] == [
        {"new_id": "new:claude-code:skill:pdf-kit/trace-canvas", "existing_id": "s1", "existing_name": "trace-canvas", "why": "same name"}
    ]
    assert "Meaning-based overlap is off" in result["note"]


def test_similar_meaning_uses_local_vectors(tmp_path):
    embed = concepts

    scan = scan_with(
        ("s1", "skill", "pdf-tools", "Work with pdf files."),
        ("s2", "skill", "zoo", "Count zebra herds."),
        ("s3", "hook", "pdf", "pdf hook"),
    )
    result = preview(PACK, scan, embedder=embed, vector_cache=tmp_path / "vec.json")
    assert result["note"] is None
    pairs = {(o["new_id"].rsplit("/", 1)[1], o["existing_id"], o["why"]) for o in result["overlaps"]}
    assert pairs == {("pdf-reader", "s1", "similar meaning")}
    assert (tmp_path / "vec.json").stat().st_mode & 0o777 == 0o600
    # without the local embedder only the note changes
    assert preview(PACK, scan, embedder=None)["overlaps"] == []


def test_same_name_wins_over_similar_meaning_and_failed_embedder_is_noted(tmp_path):
    scan = scan_with(("s1", "skill", "pdf-reader", "Work with pdf files."))
    result = preview(PACK, scan, embedder=concepts, vector_cache=tmp_path / "v.json")
    assert [(o["existing_id"], o["why"]) for o in result["overlaps"]] == [("s1", "same name")]

    def broken(texts):
        raise RuntimeError("no model")

    result = preview(PACK, scan, embedder=broken, vector_cache=tmp_path / "v2.json")
    assert "Meaning-based search is off" in result["note"]
    assert len(result["overlaps"]) == 1


def test_already_installed_plugin():
    scan = scan_with(("claude-code:plugin:pdf-kit", "plugin", "pdf-kit", "Read and fold PDF files."))
    result = preview(PACK, scan)
    assert result["already_installed"] is True
    assert result["overlaps"] == []  # the plugin matching itself is not an overlap
    assert preview(PACK, scan_with(("p", "plugin", "other", "x")))["already_installed"] is False
    assert preview(PACK, scan_with(("p", "skill", "pdf-kit", "x")))["already_installed"] is False


def test_pack_named_like_a_plugin_is_not_already_installed(tmp_path):
    skill(tmp_path / "pdf-kit", "a", "Does a thing.")
    assert preview(tmp_path / "pdf-kit", scan_with(("p", "plugin", "pdf-kit", "x")))["already_installed"] is False


def test_no_scan_means_not_compared():
    result = preview(PACK, None, embedder=lambda t: [[1.0] for _ in t])
    assert result["compared"] is False
    assert result["overlaps"] == []
    assert result["already_installed"] is False
    assert result["note"] is None


def read_log(monkeypatch) -> list[Path]:
    opened: list[Path] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        opened.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    return opened


def test_refuses_symlink_outside(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    skill(outside, "evil", "Out there.")
    (outside / "mcp.json").write_text('{"mcpServers": {"x": {"command": "y"}}}')
    pack = tmp_path / "pack"
    skill(pack, "ok", "Fine.")
    (pack / "skills" / "evil").symlink_to(outside / "skills" / "evil")
    opened = read_log(monkeypatch)
    assert check_tree(pack) == "skills/evil: symlink points outside the folder"
    with pytest.raises(ValueError, match=r"^skills/evil: symlink points outside the folder$"):
        preview(pack, None)
    (pack / "skills" / "evil").unlink()
    (pack / ".mcp.json").symlink_to(outside / "mcp.json")
    with pytest.raises(ValueError, match=r"^\.mcp\.json: symlink points outside"):
        preview(pack, None)
    assert not [p for p in opened if outside in p.parents]


def test_symlink_inside_the_folder_is_allowed(tmp_path):
    skill(tmp_path, "a", "Fine.")
    (tmp_path / "alias").symlink_to(tmp_path / "skills")
    (tmp_path / "SKILL.md").symlink_to(tmp_path / "skills" / "a" / "SKILL.md")
    assert check_tree(tmp_path) is None
    (tmp_path / "dangling").symlink_to(tmp_path / "nothing")
    assert check_tree(tmp_path) == "dangling: cannot be read"


def test_refuses_fifo_huge_and_too_many(tmp_path):
    fifo = tmp_path / "fifo"
    skill(fifo, "a", "x")
    os.mkfifo(fifo / "skills" / "pipe")
    assert check_tree(fifo) == "skills/pipe: not a regular file or folder"
    with pytest.raises(ValueError, match="not a regular file"):
        preview(fifo, None)
    huge = tmp_path / "huge"
    skill(huge, "a", "x")
    (huge / "skills" / "a" / "SKILL.md").write_text("x" * (MAX_FILE_BYTES + 1))
    assert check_tree(huge) == f"skills/a/SKILL.md: file is larger than {MAX_FILE_BYTES} bytes"
    with pytest.raises(ValueError, match="larger than"):
        preview(huge, None)
    many = tmp_path / "many"
    many.mkdir()
    for n in range(MAX_ENTRIES + 1):
        (many / f"f{n:04d}").touch()
    assert check_tree(many) == f"f{MAX_ENTRIES:04d}: more than {MAX_ENTRIES} entries in the folder"
    with pytest.raises(ValueError, match="more than 2000 entries"):
        preview(many, None)


def test_size_and_entry_limits_are_inclusive(tmp_path):
    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "a.md").write_text("x" * MAX_FILE_BYTES)
    (ok / "b.JSON").write_text("x" * MAX_FILE_BYTES)
    (ok / "c.txt").write_text("x" * (MAX_FILE_BYTES + 1))  # only .md and .json are read, so only they are limited
    assert check_tree(ok) is None
    (ok / "d.json").write_text("x" * (MAX_FILE_BYTES + 1))
    assert check_tree(ok) == f"d.json: file is larger than {MAX_FILE_BYTES} bytes"
    exact = tmp_path / "exact"
    exact.mkdir()
    for n in range(MAX_ENTRIES):
        (exact / f"f{n:04d}").touch()
    assert check_tree(exact) is None


def test_limits_are_the_documented_ones():
    assert (MAX_ENTRIES, MAX_FILE_BYTES) == (2000, 1_000_000)


def test_git_and_node_modules_are_pruned_and_nested_entries_counted(tmp_path):
    skill(tmp_path, "a", "Fine.")
    for pruned in (".git", "node_modules"):
        (tmp_path / pruned).mkdir()
        os.mkfifo(tmp_path / pruned / "pipe")
        (tmp_path / pruned / "big.md").write_text("x" * (MAX_FILE_BYTES + 1))
    assert check_tree(tmp_path) is None
    assert preview(tmp_path, None)["counts"] == {"skill": 1}
    deep = tmp_path / "skills" / "a" / "deep" / "er"
    deep.mkdir(parents=True)
    os.mkfifo(deep / "pipe")
    assert check_tree(tmp_path) == "skills/a/deep/er/pipe: not a regular file or folder"


def test_reason_names_the_relative_path_without_controls(tmp_path):
    (tmp_path / "bad\x1b[31mname").mkdir()
    os.mkfifo(tmp_path / "bad\x1b[31mname" / "p")
    assert check_tree(tmp_path) == "badname/p: not a regular file or folder"


@pytest.mark.parametrize(
    ("raw", "cap", "clean"),
    [
        ("\x1b[31mred‮ evil​", 80, "red evil"),
        ("a\x1b]0;title\x07b", 80, "ab"),
        ("a\x9b31mb", 80, "ab"),
        ("a\x9dtitle\x9cb", 80, "ab"),
        ("a\x1b]0;title\x1b\\b", 80, "ab"),
        ("one\ntwo\t three four", 80, "one two three four"),
        ("a\x00b\x7fc\U000e0041d", 80, "abcd"),
        ("a\x85b", 80, "a b"),
        ("  padded  ", 80, "padded"),
        ("abcdefghij", 5, "abcde"),
        ("abcde fghij", 6, "abcde"),
        ("abc", 3, "abc"),
        ("é" * 10, 10, "é" * 10),
    ],
)
def test_control_and_bidi_text_is_stripped(raw, cap, clean):
    assert _plain(raw, cap) == clean


def test_long_name_and_description_are_capped(tmp_path):
    skill(tmp_path, "n" * 120, "\x1b[31mred‮ evil​ " + "w" * 300, folder="long")
    item = preview(tmp_path, None)["items"][0]
    assert item["name"] == "n" * 80
    assert item["description"].startswith("red evil w") and len(item["description"]) == 200


def test_no_absolute_path_and_secrets_redacted(tmp_path):
    secret = "hunter2hunter"
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"srv": {"command": "run", "env": {"TOKEN": secret}}}}))
    skill(tmp_path, "a", f"Uses {secret} and also h​unter2hunter")
    skill(tmp_path, "nodesc", "x", folder="nofront")
    (tmp_path / "skills" / "nofront" / "SKILL.md").write_text("no frontmatter here\n")
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "c.md").write_text("---\ndescription:\n---\n")
    result = preview(tmp_path, None)
    dumped = json.dumps(result)
    assert str(tmp_path) not in dumped and str(tmp_path.resolve()) not in dumped
    assert secret not in dumped and "hunter2" not in dumped
    assert any(w.startswith("no frontmatter in ") and tmp_path.name in w for w in result["warnings"])
    assert any("skipped command 'c'" in w and str(tmp_path) not in w for w in result["warnings"])


def test_pack_under_home_hides_the_home_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    pack = tmp_path / "work" / "packx"
    (pack / "skills" / "s").mkdir(parents=True)
    (pack / "skills" / "s" / "SKILL.md").write_text("nothing\n")
    result = preview(pack, None)
    assert result["warnings"] == ["no frontmatter in packx/skills/s/SKILL.md", "skipped skill with no name (packx/skills/s/SKILL.md)"]


def test_snapshot_drops_preview_fields():
    demo = {"items": [{"id": "s1", "kind": "skill", "name": "trace-canvas", "description": "Draws.", "source": ""}]}
    result = preview(PACK, scan_with(("s1", "skill", "trace-canvas", "x")))
    out = snapshot({**demo, "preview": result})
    assert set(out) == {"items", "relations", "labels", "clusters", "costs", "overlaps"}
    assert "pdf-kit" not in json.dumps(out)


@pytest.mark.parametrize(
    "files",
    [
        {"hooks/hooks.json": '{"hooks": {"Stop": [{}]}}'},
        {".claude-plugin/plugin.json": '{"description": "no name"}'},
        {".claude-plugin/plugin.json": '{"name": ""}'},
        {".claude-plugin/plugin.json": '{"name": 5}'},
        {".claude-plugin/plugin.json": "[1]"},
        {".claude-plugin/plugin.json": "not json"},
        {"SKILL.md": "---\nname: a\n---\n", "skills/x/SKILL.md": b"\xff\xfe"},
    ],
)
def test_malformed_pack_is_refused_not_crash(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())
    with pytest.raises(ValueError, match=r"^could not read the pack: malformed file$"):
        preview(tmp_path, None)


@pytest.mark.parametrize("text", ["[]", '{"hooks": {"Stop": [{"hooks": [{"type": "command"}]}]}}'])
def test_bad_hooks_file_warns_not_crash(tmp_path, text):
    # after #72 the shared reader turns these into a fixed warning instead of refusing the whole pack
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "hooks.json").write_text(text)
    result = preview(tmp_path, None)  # must not raise
    assert bool(result["warnings"]) == (text != "[]")  # an empty list is silently fine; a hook without a command warns


def test_plugin_manifest_mcp_entries(tmp_path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "pk", "mcpServers": {"inline": {"command": "a", "env": {"K": "supersecretvalue"}}}})
    )
    result = preview(tmp_path, None)
    assert [i["name"] for i in result["items"]] == ["pk", "inline"]
    assert "supersecretvalue" not in json.dumps(result)


def test_hook_commands_are_text_only(tmp_path):
    marker = tmp_path / "ran"
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    command = f"touch {marker}"
    (hooks / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}))
    assert preview(tmp_path, None)["items"][0]["description"].startswith("touch ")
    assert not marker.exists()


def test_preview_module_imports_no_provider():
    source = Path(preview_module.__file__).read_text()
    assert "anthropic" not in source and "env import" not in source and "load_env" not in source


def test_stat_module_flags_are_what_check_tree_uses():
    assert stat.S_ISREG(os.stat(PACK / ".mcp.json").st_mode)


def test_long_pack_name_and_long_warning_are_capped(tmp_path):
    pack = tmp_path / ("p" * 120)
    where = pack / "skills" / "s"
    where.mkdir(parents=True)
    (where / "SKILL.md").write_text(f"---\nname: {'n' * 300}\n---\nbody\n")
    result = preview(pack, None)
    assert result["pack"]["name"] == "p" * 80
    assert len(result["warnings"][0]) == 200
    assert result["warnings"][0].startswith("skipped skill 'nnn")


def test_scan_names_are_cleaned_before_comparing_and_showing(tmp_path):
    scan = scan_with(("s1", "skill", "trace-​canvas\x1b[31m", "x"), ("s2", "skill", "pdf-reader" + "y" * 100, "x"))
    result = preview(PACK, scan)
    assert [(o["existing_id"], o["existing_name"]) for o in result["overlaps"]] == [("s1", "trace-canvas")]
    long = scan_with(("p1", "plugin", "pdf-kit" + "​", "x"))
    assert preview(PACK, long)["already_installed"] is True
    longname = tmp_path / ("q" * 100)
    (longname / ".claude-plugin").mkdir(parents=True)
    (longname / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "q" * 100}))
    assert preview(longname, scan_with(("p", "plugin", "q" * 100, "x")))["already_installed"] is True
    shown = preview(PACK, scan_with(("s1", "skill", "trace-canvas", "x"), ("s9", "skill", "z" * 100, "x")), embedder=concepts)
    assert shown["note"] is None


def test_similar_meaning_details(tmp_path, monkeypatch):
    scan = scan_with(("s2", "skill", "alpha", "Work with pdf files."), ("s1", "skill", "zeta", "Work with pdf files."))
    result = preview(PACK, scan, embedder=concepts, vector_cache=tmp_path / "v.json")
    assert result["overlaps"] == [
        {"new_id": "new:claude-code:skill:pdf-kit/pdf-reader", "existing_id": "s1", "existing_name": "zeta", "why": "similar meaning"}
    ]
    monkeypatch.setattr(preview_module.retrieve, "SIMILAR", 1.0)  # an exactly equal score still counts
    again = preview(PACK, scan, embedder=concepts, vector_cache=tmp_path / "v2.json")
    assert len(again["overlaps"]) == 1


def test_missing_embedder_note_text():
    assert preview(PACK, scan_with(("s1", "skill", "q", "x")))["note"] == (
        "Meaning-based overlap is off (the local embedder is unavailable); only same names were compared."
    )


def test_long_scan_name_is_capped_for_display():
    scan = scan_with(("s1", "skill", "pdf-reader", "x"))
    scan["items"][0]["name"] = "pdf-reader" + " tail" * 40
    result = preview(PACK, scan)
    assert result["overlaps"] == []  # the long name no longer equals the pack's
    scan = scan_with(("s1", "skill", "pdf-reader", "x"), ("s2", "skill", "m" * 100, "x"))
    out = preview(PACK, scan, embedder=lambda t: [[1.0, 0.0] for _ in t])
    assert {o["existing_name"] for o in out["overlaps"]} <= {"pdf-reader", "m" * 80}


def test_similar_match_shows_a_capped_name(tmp_path):
    long = "pdf-" + "m" * 100
    out = preview(PACK, scan_with(("s1", "skill", long, "pdf files")), embedder=concepts, vector_cache=tmp_path / "v.json")
    assert [o["existing_name"] for o in out["overlaps"]] == [long[:80]]


@pytest.mark.parametrize("folder", ["node_modules", ".git"])
def test_nested_pruned_names_are_still_vetted(tmp_path, folder):
    fifo = tmp_path / "fifo"
    skill(fifo, "a", "x")
    (fifo / "skills" / folder).mkdir()
    os.mkfifo(fifo / "skills" / folder / "SKILL.md")
    assert check_tree(fifo) == f"skills/{folder}/SKILL.md: not a regular file or folder"
    big = tmp_path / "big"
    skill(big, "a", "x")
    (big / "skills" / folder).mkdir()
    (big / "skills" / folder / "SKILL.md").write_text("---\nname: b\ndescription: " + "x" * 3_000_000 + "\n---\n")
    assert check_tree(big) == f"skills/{folder}/SKILL.md: file is larger than {MAX_FILE_BYTES} bytes"
    with pytest.raises(ValueError, match="larger than"):
        preview(big, None)


def test_alias_bomb_is_refused_quickly(tmp_path):
    import signal

    bomb = "a: &a [x,x,x,x,x,x,x,x,x]\n" + "".join(
        f"{c}: &{c} [*{p},*{p},*{p},*{p},*{p},*{p},*{p},*{p},*{p}]\n" for p, c in zip("abcdefgh", "bcdefghi", strict=True)
    )
    assert len(bomb) < 1024
    where = tmp_path / "skills" / "s"
    where.mkdir(parents=True)
    (where / "SKILL.md").write_text(f"---\n{bomb}name: *i\ndescription: *i\n---\nbody")
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("hung")))
    signal.alarm(10)
    try:
        with pytest.raises(ValueError, match=r"^could not read the pack: malformed file$"):
            preview(tmp_path, None)
    finally:
        signal.alarm(0)


def test_frontmatter_with_asterisks_in_text_is_fine(tmp_path):
    skill(tmp_path, "a", "Uses *bold* and a&b and x * y")
    assert preview(tmp_path, None)["items"][0]["description"] == "Uses *bold* and a&b and x * y"


def test_non_text_name_or_description_is_dropped_with_a_fixed_warning(tmp_path):
    where = tmp_path / "skills" / "a"
    where.mkdir(parents=True)
    (where / "SKILL.md").write_text("---\nname: 42\ndescription: [one, two]\n---\nbody\n")
    result = preview(tmp_path, None)
    assert result["items"] == []
    assert result["warnings"] == ["skipped an item: its name or description is not text"]


def test_item_ids_are_cleaned(tmp_path):
    skill(tmp_path, "a‮b\x1b[31mc​" + "z" * 400, "Fine.", folder="s")
    ident = preview(tmp_path, None)["items"][0]["id"]
    assert ident.startswith("new:claude-code:skill:") and "‮" not in ident and "\x1b" not in ident and "​" not in ident
    assert len(ident) == 304  # 4 for the "new:" prefix


def test_preview_leaves_the_default_vector_cache_alone(tmp_path, monkeypatch):
    cache = tmp_path / "default.json"
    cache.write_text('{"keep": [1.0]}')
    monkeypatch.setattr(preview_module.retrieve, "DEFAULT_CACHE", cache)
    preview(PACK, scan_with(("s1", "skill", "zzz", "Other.")), embedder=concepts)
    assert cache.read_text() == '{"keep": [1.0]}'


def test_unreadable_folders_are_refused_without_absolute_paths(tmp_path):
    with pytest.raises(ValueError) as error:
        preview(Path(__file__), None)
    assert str(error.value) == "test_preview.py: cannot be read"
    pack = tmp_path / "pk"
    skill(pack, "a", "x")
    locked = pack / "sub"
    locked.mkdir()
    locked.chmod(0)
    try:
        assert check_tree(pack) == "sub: cannot be read"
    finally:
        locked.chmod(0o700)


def test_declared_mcp_file_of_any_type_is_size_checked(tmp_path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "e", "mcpServers": ["m.txt"]}))
    (tmp_path / "m.txt").write_text(json.dumps({"mcpServers": {"s": {"command": "x"}}}) + " " * (MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="malformed"):
        preview(tmp_path, None)
    (tmp_path / "m.txt").write_text(json.dumps({"mcpServers": {"s": {"command": "x"}}}))
    assert preview(tmp_path, None)["counts"] == {"plugin": 1, "mcp_server": 1}


def test_preview_survives_a_wrong_dimension_vector_cache(tmp_path):
    from constellation import retrieve

    scan = scan_with(("s1", "skill", "pdf-tools", "Work with pdf files."), ("s2", "skill", "zoo", "Count zebra herds."))
    stale = tmp_path / "v.json"
    stale.write_text(json.dumps({retrieve._key("pdf-tools: Work with pdf files."): [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]}))
    result = preview(PACK, scan, embedder=concepts, vector_cache=stale)
    assert {(o["new_id"].rsplit("/", 1)[1], o["existing_id"]) for o in result["overlaps"]} == {("pdf-reader", "s1")}
    assert result["note"] == "Some saved search vectors did not match the local embedder and were rebuilt."
    assert stale.stat().st_mode & 0o777 == 0o600
