"""Forgotten-skill discovery uses invented local data only."""

import pytest

from constellation.retrieve import Index


def test_headings_find_a_skill_with_an_uninformative_description():
    items = [{"id": "cabinet", "kind": "skill", "name": "cabinet", "description": "A collection of references"}]
    index = Index(items, skill_content={"cabinet": [("heading", "Website typography")]})
    try:
        assert index.query("typography for websites") == [{"id": "cabinet", "why": "heading: Website typography"}]
        assert "skill_content" not in items[0]
    finally:
        index.close()


def test_find_command_discovers_headings_without_loading_env_or_a_model(tmp_path, monkeypatch, capsys):
    from fakes import write_skill

    from constellation import cli, skill_search

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography\nA small collection.", description="Assorted reference material")
    cache = tmp_path / "private-cache" / "skill-content.json"
    monkeypatch.setattr(skill_search, "DEFAULT_CACHE", cache)

    def forbidden(*args, **kwargs):
        raise AssertionError("Local find must not load credentials or a model")

    monkeypatch.setattr(cli, "load_env", forbidden)
    monkeypatch.setattr(cli, "_local_embedder", forbidden)
    assert cli.main(["find", "typography for websites", "--config-dir", str(root)]) == 0
    output = capsys.readouterr()
    assert "cabinet" in output.out and "heading: Website typography" in output.out
    assert "/cabinet" in output.out and "Assorted reference material" in output.out


def test_first_lines_are_searchable_and_the_content_index_is_private(tmp_path):
    import stat

    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(
        root,
        "cabinet",
        "Typography for websites.\nSecond introduction.\nThird introduction.\nPRIVATE-LATE-BODY-MARKER",
        description="Assorted reference material",
    )
    cache = tmp_path / "private-cache" / "skill-content.json"
    hits, warnings = find_skills("website typography", root, cache=cache)
    assert warnings == [] and hits[0]["why"] == "first line: Typography for websites."
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    assert "PRIVATE-LATE-BODY-MARKER" not in cache.read_text()
    assert not (root / "skill-content.json").exists()


def test_reference_filenames_are_searchable_without_reading_their_contents(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Overview\nGeneral references.", description="Assorted material")
    reference = root / "skills" / "cabinet" / "references" / "notion-fonts.md"
    reference.parent.mkdir()
    reference.write_bytes(b"\xff\xfePRIVATE-REFERENCE-CONTENTS")
    hits, warnings = find_skills("fonts like Notion", root, cache=tmp_path / "index.json")
    assert warnings == [] and hits[0]["why"] == "file: notion-fonts.md"
    assert "PRIVATE-REFERENCE-CONTENTS" not in str(hits) + (tmp_path / "index.json").read_text()


def test_saved_local_content_can_be_searched_without_the_skill_files(tmp_path):
    import shutil

    from fakes import write_skill

    from constellation.skill_search import find_skills, load_content

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography", description="Assorted material")
    cache = tmp_path / "index.json"
    find_skills("typography", root, cache=cache)
    shutil.rmtree(root)
    metadata = [{"id": "claude-code:skill:cabinet", "kind": "skill", "name": "cabinet", "description": "Assorted material"}]
    index = Index(metadata, skill_content=load_content(cache))
    try:
        assert index.query("typography")[0]["why"] == "heading: Website typography"
    finally:
        index.close()


@pytest.mark.parametrize("secret_in_name", [False, True])
@pytest.mark.parametrize("assignment", ["API_TOKEN={secret}", "API_TOKEN='{secret}'", 'API_TOKEN="{secret}"', "--api-key {secret}"])
def test_body_credentials_are_redacted_everywhere_in_the_private_index_and_results(tmp_path, secret_in_name, assignment):
    from fakes import write_skill

    from constellation.skill_search import find_skills, load_content

    secret = "XtealcanaryprivatevalueX"
    root = tmp_path / f"invented-setup-{secret}"
    name = f"cabinet-{secret}" if secret_in_name else "cabinet"
    write_skill(
        root,
        name,
        f"{assignment.format(secret=secret)}\n# Website typography {secret}\nReference notes.",
        description=f"Assorted material {secret}",
    )
    reference = root / "skills" / name / f"notion-{secret}.md"
    reference.write_text("PRIVATE-REFERENCE-CONTENTS")
    cache = tmp_path / "index.json"
    hits, warnings = find_skills("typography", root, cache=cache)
    assert hits and warnings == []
    assert secret not in str(hits) + cache.read_text() + str(load_content(cache))
    assert hits[0]["why"] == "heading: Website typography [REDACTED]"
    assert "[REDACTED]" in cache.read_text()


@pytest.mark.parametrize("extra, expected", [("", {"s": [("heading", "Type")]}), (" ", {})])
def test_loading_the_saved_index_is_bounded_at_its_size_limit(tmp_path, monkeypatch, extra, expected):
    from constellation import skill_search

    raw = '{"s":[["heading","Type"]]}'
    cache = tmp_path / "index.json"
    cache.write_text(raw + extra)
    monkeypatch.setattr(skill_search, "MAX_CACHE_BYTES", len(raw))
    assert skill_search.load_content(cache) == expected


@pytest.mark.parametrize("fence, nested", [("```", "~~~"), ("~~~", "```")])
def test_markdown_headings_are_searched_but_code_examples_are_not(tmp_path, fence, nested):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", f"{fence}md\n# PRIVATECODEEXAMPLE\n{nested}\n{fence}\nWebsite typography\n==================\nReferences.")
    cache = tmp_path / "index.json"
    hits, warnings = find_skills("typography", root, cache=cache)
    assert warnings == [] and hits[0]["why"] == "heading: Website typography"
    assert "PRIVATECODEEXAMPLE" not in cache.read_text()
    assert find_skills("PRIVATECODEEXAMPLE", root, cache=cache)[0] == []


@pytest.mark.parametrize(
    "scope, expected_id, expected_invoke",
    [
        ("local", "claude-code:skill:cabinet", "/cabinet"),
        ("synced", "claude-code:skill:synced/cabinet", "/cabinet"),
        ("plugin", "claude-code:skill:toolbox/cabinet", "/toolbox:cabinet"),
    ],
)
def test_bundle_search_uses_the_reader_scopes_and_the_correct_invocation(tmp_path, scope, expected_id, expected_invoke):
    import json

    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    skill_root = root
    if scope == "plugin":
        skill_root = root / "plugins/cache/invented-market/toolbox/1"
        manifest = skill_root / ".claude-plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"name": "toolbox"}))
    write_skill(skill_root, "cabinet", "# Overview\nGeneral reference.")
    folder = skill_root / "skills/cabinet"
    if scope == "synced":
        target = root / "skills/synced/invented-account/cabinet"
        target.parent.mkdir(parents=True)
        folder.rename(target)
        folder = target
    (folder / "notion-fonts.md").write_bytes(b"\xffPRIVATE-REFERENCE")
    hits, warnings = find_skills("Notion fonts", root, cache=tmp_path / "index.json")
    assert warnings == []
    assert hits[0]["id"] == expected_id and hits[0]["invoke"] == expected_invoke
    assert hits[0]["why"] == "file: notion-fonts.md"


def test_skill_content_is_separate_from_provider_inputs_and_shared_outputs(tmp_path, monkeypatch):
    import json
    from dataclasses import asdict

    from fakes import FakeEmbedder, write_skill

    from constellation import public_export, scan
    from constellation.report import render_report
    from constellation.skill_search import find_skills, load_content
    from constellation.snapshot import snapshot

    root = tmp_path / "invented-setup"
    marker = "PRIVATEHEADINGTYPOGRAPHY"
    write_skill(root, "cabinet", f"# {marker}\nPrivate introductory evidence.", description="Assorted material")
    cache = tmp_path / "index.json"
    find_skills("typography", root, cache=cache)
    metadata = [{"id": "claude-code:skill:cabinet", "kind": "skill", "name": "cabinet", "description": "Assorted material"}]
    embed = FakeEmbedder({})
    index = Index(metadata, skill_content=load_content(cache))
    try:
        index.add_vectors(embed, tmp_path / "vectors.json")
        assert embed.texts == ["cabinet: Assorted material"]
        assert marker not in json.dumps(index.items)
    finally:
        index.close()
    data = asdict(scan(root, offline=True, usage=False, origins=False))
    report = render_report(data, top=15, color=False, width=100, show_all=True)
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html><head></head><body></body></html>")
    (static / "assets/app.js").write_text("/* invented build */")
    monkeypatch.setattr(public_export, "STATIC", static)
    public_export.write_snapshot(data, tmp_path / "public")
    assert marker not in json.dumps(data) + report + json.dumps(snapshot(data))
    assert all(marker.encode() not in path.read_bytes() for path in (tmp_path / "public").rglob("*") if path.is_file())


@pytest.mark.parametrize("location", ["inside", "symlink"])
def test_the_private_cache_never_changes_the_scanned_setup(tmp_path, location):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    skill = root / "skills/cabinet/SKILL.md"
    before = skill.read_bytes()
    cache = root / "index.json"
    if location == "symlink":
        cache = tmp_path / "index.json"
        cache.symlink_to(skill)
    hits, warnings = find_skills("typography", root, cache=cache)
    assert hits and warnings == ["The private skill index could not be written; local search still works."]
    assert skill.read_bytes() == before
    assert not (root / "index.json").exists()


def test_terminal_controls_and_long_evidence_are_not_rendered_unbounded(tmp_path):
    import json

    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    body = "# Typography " + "x" * 220 + "\x1b[31m\x85"
    write_skill(root, "cabinet", body)
    skill = root / "skills/cabinet/SKILL.md"
    skill.write_text(f"---\nname: {json.dumps('cabinet' + chr(27))}\ndescription: Assorted material\n---\n{body}")
    hits, warnings = find_skills("typography", root, cache=tmp_path / "index.json")
    assert warnings == [] and hits[0]["name"] == "cabinet"
    assert hits[0]["why"] == "heading: Typography " + "x" * 189
    assert "\x1b" not in str(hits) and "\x85" not in str(hits)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("not-json", {}),
        ("[]", {}),
        ('{"s":"bad rows"}', {}),
        ('{"s":[null,["heading"],["file","x",0],[[],"bad"],["unknown","bad"],["heading",5]]}', {"s": []}),
    ],
)
def test_invalid_cache_rows_cannot_enter_the_search_corpus(tmp_path, raw, expected):
    from constellation.skill_search import load_content

    cache = tmp_path / "index.json"
    cache.write_text(raw)
    assert load_content(cache) == expected


def test_unwritable_index_warns_but_local_search_still_works(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    blocker = tmp_path / "blocker"
    blocker.write_text("invented blocker")
    hits, warnings = find_skills("typography", root, cache=blocker / "index.json")
    assert hits[0]["why"] == "heading: Website typography"
    assert warnings == ["The private skill index could not be written; local search still works."]


def test_an_existing_cache_is_made_private_before_replacing_it(tmp_path):
    import stat

    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    cache = tmp_path / "index.json"
    cache.write_text("{}")
    cache.chmod(0o666)
    assert find_skills("typography", root, cache=cache)[0]
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600


def test_body_evidence_is_ignored_for_non_skills_and_unknown_ids():
    items = [{"id": "hook", "kind": "hook", "name": "quiet", "description": "A hook"}]
    index = Index(items, skill_content={"hook": [("heading", "Typography")], "unknown": [("file", "fonts.md")]})
    try:
        assert index.query("typography fonts") == []
    finally:
        index.close()


def test_duplicate_content_hits_keep_the_strongest_reason_without_duplicate_results():
    items = [{"id": "cabinet", "kind": "skill", "name": "cabinet", "description": "Assorted material"}]
    index = Index(
        items,
        skill_content={"cabinet": [("heading", "Typography for many unrelated desktop applications"), ("heading", "Website typography")]},
    )
    try:
        assert index.query("website typography") == [{"id": "cabinet", "why": "heading: Website typography"}]
    finally:
        index.close()


def test_user_linked_skills_keep_their_bundled_reference_names(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root, external = tmp_path / "invented-setup", tmp_path / "invented-shared-skills"
    write_skill(external, "cabinet", "General reference.")
    (external / "skills/cabinet/notion-fonts.md").write_bytes(b"\xff")
    (root / "skills").mkdir(parents=True)
    (root / "skills/cabinet").symlink_to(external / "skills/cabinet", target_is_directory=True)
    hits, warnings = find_skills("Notion fonts", root, cache=tmp_path / "index.json")
    assert warnings == [] and hits[0]["why"] == "file: notion-fonts.md"


def test_a_plugin_skill_link_cannot_escape_its_plugin_root(tmp_path):
    import json

    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    plugin = root / "plugins/cache/invented-market/toolbox/1"
    manifest = plugin / ".claude-plugin/plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": "toolbox"}))
    outside = tmp_path / "invented-outside"
    outside.write_bytes(b"\xffPRIVATE-OUTSIDE")
    folder = plugin / "skills/cabinet"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").symlink_to(outside)
    write_skill(plugin, "zzz", "General reference.")
    (plugin / "skills/zzz/notion-fonts.md").write_bytes(b"\xff")
    hits, warnings = find_skills("notion fonts", root, cache=tmp_path / "index.json")
    assert hits[0]["name"] == "zzz" and any("outside" in warning for warning in warnings)


def test_reference_symlinks_are_not_indexed(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "General reference.")
    outside = tmp_path / "invented-outside"
    outside.write_bytes(b"\xffPRIVATE-OUTSIDE")
    (root / "skills/cabinet/notion-fonts.md").symlink_to(outside)
    hits, warnings = find_skills("Notion fonts", root, cache=tmp_path / "index.json")
    assert warnings == [] and hits == []


def test_bad_or_missing_skill_frontmatter_is_warned_and_skipped(tmp_path):
    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    folder = root / "skills/invalid"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("No frontmatter.\n# Typography")
    hits, warnings = find_skills("typography", root, cache=tmp_path / "index.json")
    assert hits == [] and any("no name" in warning for warning in warnings)


def test_unreadable_or_symlinked_saved_content_is_ignored(tmp_path):
    from constellation.skill_search import load_content

    assert load_content(tmp_path / "missing.json") == {}
    target = tmp_path / "invented-private.json"
    target.write_text('{"s":[["heading","Typography"]]}')
    link = tmp_path / "index.json"
    link.symlink_to(target)
    assert load_content(link) == {}


def test_empty_credential_examples_do_not_hide_valid_content(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "API_TOKEN=''\n# Website typography")
    hits, warnings = find_skills("typography", root, cache=tmp_path / "index.json")
    assert warnings == [] and hits[0]["why"] == "heading: Website typography"


def test_cached_evidence_is_scrubbed_and_clipped_when_reloaded(tmp_path):
    import json

    from constellation.skill_search import load_content

    cache = tmp_path / "index.json"
    cache.write_text(json.dumps({"s": [["heading", "Typography sk-" + "a" * 32 + " " + "x" * 250 + "\x1b"]]}))
    assert load_content(cache) == {"s": [("heading", "Typography [REDACTED] " + "x" * 178)]}


def test_a_large_index_does_not_replace_the_previous_cache(tmp_path, monkeypatch):
    from fakes import write_skill

    from constellation import skill_search

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    cache = tmp_path / "index.json"
    cache.write_text("{}")
    monkeypatch.setattr(skill_search, "MAX_CACHE_BYTES", 1)
    hits, warnings = skill_search.find_skills("typography", root, cache=cache)
    assert hits and warnings == ["The private skill index could not be written; local search still works."]
    assert cache.read_text() == "{}"


def test_an_index_at_the_write_size_limit_is_accepted(tmp_path, monkeypatch):
    from fakes import write_skill

    from constellation import skill_search

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    cache = tmp_path / "index.json"
    skill_search.find_skills("typography", root, cache=cache)
    monkeypatch.setattr(skill_search, "MAX_CACHE_BYTES", cache.stat().st_size)
    hits, warnings = skill_search.find_skills("typography", root, cache=cache)
    assert hits and warnings == []


def test_empty_lines_do_not_consume_the_first_visible_lines(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Overview\n\nFirst introduction.\n\nWebsite typography.")
    hits, warnings = find_skills("typography", root, cache=tmp_path / "index.json")
    assert warnings == [] and hits[0]["why"] == "first line: Website typography."


def test_missing_name_in_a_sibling_does_not_replace_a_valid_skill_named_none(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "None", "# Overview")
    write_skill(root, "zzz", "# Overview")
    (root / "skills/None/notion-fonts.md").write_bytes(b"\xff")
    (root / "skills/zzz/notion-fonts.md").write_bytes(b"\xff")
    invalid = root / "skills/invalid/SKILL.md"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("No frontmatter")
    hits, warnings = find_skills("notion fonts", root, cache=tmp_path / "index.json")
    assert warnings and hits[0]["name"] == "None" and hits[0]["why"] == "file: notion-fonts.md"
    assert {h["name"] for h in hits} == {"None", "zzz"}


def test_a_deep_saved_index_is_ignored_without_crashing(tmp_path):
    from constellation.skill_search import load_content

    cache = tmp_path / "index.json"
    cache.write_text("[" * 1200 + "0" + "]" * 1200)
    assert load_content(cache) == {}


def test_a_cache_symlink_cannot_overwrite_an_unrelated_file(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    unrelated = tmp_path / "invented-unrelated.txt"
    unrelated.write_text("INVENTED-KEEP-THIS-FILE")
    cache = tmp_path / "index.json"
    cache.symlink_to(unrelated)
    hits, warnings = find_skills("typography", root, cache=cache)
    assert hits and warnings == ["The private skill index could not be written; local search still works."]
    assert unrelated.read_text() == "INVENTED-KEEP-THIS-FILE"


def test_reindexing_drops_removed_skills_without_leaving_trailing_data(tmp_path):
    import shutil

    from fakes import write_skill

    from constellation.skill_search import find_skills, load_content

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    write_skill(root, "removed", "# PRIVATE-REMOVED-EVIDENCE " + "x" * 100)
    cache = tmp_path / "index.json"
    find_skills("typography", root, cache=cache)
    shutil.rmtree(root / "skills/removed")
    find_skills("typography", root, cache=cache)
    assert set(load_content(cache)) == {"claude-code:skill:cabinet"}
    assert "PRIVATE-REMOVED-EVIDENCE" not in cache.read_text()


def test_a_matching_heading_explains_the_hit_even_when_the_description_matches_one_word():
    items = [{"id": "cabinet", "kind": "skill", "name": "cabinet", "description": "Website utilities"}]
    index = Index(items, skill_content={"cabinet": [("heading", "Website typography")]})
    try:
        assert index.query("website typography") == [{"id": "cabinet", "why": "heading: Website typography"}]
    finally:
        index.close()


def test_a_setext_heading_at_the_end_of_the_file_is_still_a_heading(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "Website typography\n==================")
    hits, warnings = find_skills("typography", root, cache=tmp_path / "index.json")
    assert warnings == [] and hits[0]["why"] == "heading: Website typography"


def test_configured_secret_values_are_kept_when_body_credentials_are_learned(tmp_path):
    import json

    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    secret = "opaqueconfiguredprivatevalue"
    write_skill(root, "cabinet", f"OTHER_TOKEN=bodyexample\n# Website typography {secret}")
    (root / "settings.json").write_text(json.dumps({"env": {"API_TOKEN": secret}}))
    cache = tmp_path / "index.json"
    hits, warnings = find_skills("typography", root, cache=cache)
    assert warnings == [] and hits[0]["why"] == "heading: Website typography [REDACTED]"
    assert secret not in cache.read_text() + str(hits)


def test_only_the_first_plugin_instance_chosen_by_the_reader_is_indexed(tmp_path):
    import json

    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    for market, filename in (("aaa-market", "notion-fonts.md"), ("zzz-market", "unselected-private-reference.md")):
        plugin = root / f"plugins/cache/{market}/toolbox/1"
        manifest = plugin / ".claude-plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"name": "toolbox"}))
        write_skill(plugin, "cabinet", "General reference.")
        (plugin / f"skills/cabinet/{filename}").write_bytes(b"\xff")
    cache = tmp_path / "index.json"
    hits, warnings = find_skills("notion fonts", root, cache=cache)
    assert warnings == [] and hits[0]["why"] == "file: notion-fonts.md"
    assert "unselected-private-reference" not in cache.read_text()


@pytest.mark.parametrize("manifest_kind", ["missing", "malformed"])
def test_plugin_discovery_matches_the_new_optional_manifest_reader(tmp_path, manifest_kind):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "local", "# Overview")
    plugin = root / "plugins/cache/invented-market/toolbox/1"
    write_skill(plugin, "cabinet", "General reference.")
    (plugin / "skills/cabinet/notion-fonts.md").write_bytes(b"\xff")
    if manifest_kind == "malformed":
        manifest = plugin / ".claude-plugin/plugin.json"
        manifest.parent.mkdir()
        manifest.write_text("{invalid")
    hits, warnings = find_skills("notion fonts", root, cache=tmp_path / "index.json")
    if manifest_kind == "missing":
        assert warnings == [] and hits[0]["invoke"] == "/toolbox:cabinet"
    else:
        assert hits == [] and warnings == ["skipped a plugin: its plugin.json is unreadable, not valid JSON or has no name"]


def test_a_skill_evicted_after_the_source_read_keeps_its_local_heading_evidence(tmp_path, monkeypatch):
    import shutil

    from fakes import write_skill

    from constellation import skill_search

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    read_items = skill_search.read_items

    def read_then_evict(config_dir):
        data = read_items(config_dir)
        shutil.rmtree(root / "skills/cabinet")
        return data

    monkeypatch.setattr(skill_search, "read_items", read_then_evict)
    hits, warnings = skill_search.find_skills("typography", root, cache=tmp_path / "index.json")
    assert warnings == [] and hits[0]["why"] == "heading: Website typography"


def test_a_fresh_nested_cache_directory_is_created_private_even_with_a_loose_umask(tmp_path):
    import os
    import stat

    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    cache = tmp_path / "never-created/nested/constellation/index.json"
    previous_mask = os.umask(0)
    try:
        hits, warnings = find_skills("typography", root, cache=cache)
    finally:
        os.umask(previous_mask)
    assert hits and warnings == []
    assert stat.S_IMODE(cache.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600


def test_a_failed_permission_update_leaves_an_empty_private_cache(tmp_path, monkeypatch):
    import os
    import stat

    from fakes import write_skill

    from constellation import skill_search

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography")
    cache = tmp_path / "index.json"

    def failed_permissions(fd, mode):
        raise OSError("invented permission-update failure")

    monkeypatch.setattr(skill_search.os, "fchmod", failed_permissions)
    previous_mask = os.umask(0)
    try:
        hits, warnings = skill_search.find_skills("typography", root, cache=cache)
    finally:
        os.umask(previous_mask)
    assert hits and warnings == ["The private skill index could not be written; local search still works."]
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600 and cache.read_bytes() == b""


def test_reader_warnings_redact_opaque_configuration_values(tmp_path):
    import json

    from fakes import write_skill

    from constellation.skill_search import find_skills

    secret = "opaqueconfiguredprivatevalue"
    root = tmp_path / f"invented-{secret}"
    write_skill(root, "cabinet", "# Website typography")
    (root / "settings.json").write_text(json.dumps({"env": {"TOKEN": secret}}))
    bad = root / "skills/invalid/SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("No frontmatter")
    cache = tmp_path / "index.json"
    hits, warnings = find_skills("typography", root, cache=cache)
    assert hits and warnings and "[REDACTED]" in str(warnings)
    assert secret not in str(warnings) + cache.read_text() + str(hits)


def test_find_command_output_is_cards_with_one_warning_line_and_json(tmp_path, monkeypatch, capsys):
    import json

    from fakes import write_skill

    from constellation import cli, skill_search

    root = tmp_path / "invented-setup"
    for n in range(10):
        write_skill(root, f"fonts{n}", "# Website typography", description=f"Typography helper number {n}")
    bad = root / "skills" / "loose" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("---\nname: loose\ndescription: Typography: loosely quoted\n---\nbody\n")
    monkeypatch.setattr(skill_search, "DEFAULT_CACHE", tmp_path / "private" / "skill-content.json")
    assert cli.main(["find", "typography", "--config-dir", str(root)]) == 0
    out = capsys.readouterr()
    assert 'Found 11 skills for "typography"' in out.out and "Showing 8 of 11" in out.out
    assert out.out.rstrip().endswith("1 file had loose frontmatter and was read leniently (--verbose lists them)")
    assert "not valid YAML" not in out.out + out.err
    assert cli.main(["find", "typography", "--config-dir", str(root), "--all", "--verbose"]) == 0
    out = capsys.readouterr()
    assert "11. " in out.out and "not valid YAML" in out.err
    assert cli.main(["find", "typography", "--config-dir", str(root), "--json", "--limit", "2"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["hits"]) == 2 and data["hits"][0]["origin"] == "yours" and data["warnings"] == []
    assert cli.main(["find", "zzqq", "--config-dir", str(root)]) == 0
    text = capsys.readouterr().out
    assert 'No match for "zzqq"' in text and "Closest names: " in text


def test_closest_names_returns_three_skill_names(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import closest_names

    root = tmp_path / "invented-setup"
    for name in ("alpha", "alphabet", "beta", "gamma"):
        write_skill(root, name, "# x", description="d")
    assert closest_names("alpha", root)[:2] == ["alpha", "alphabet"] and len(closest_names("alpha", root)) == 3


def test_closest_names_redacts_secret_names_and_limits_to_three(tmp_path):
    import json

    from fakes import write_skill

    from constellation.skill_search import closest_names

    secret = "ZZQ-INVENTED-SECRET-NAME-81"
    root = tmp_path / "invented-setup"
    root.mkdir()
    (root / "settings.json").write_text(json.dumps({"env": {"INVENTED_TOKEN": secret}}))
    for name in (secret, "one", "two", "three", "four"):
        write_skill(root, name, "# x", description="d")
    names = closest_names(secret, root)
    assert len(names) == 3 and secret not in " ".join(names) and any("[REDACTED]" in n for n in names)


def test_find_skills_limit_caps_the_hits(tmp_path):
    from fakes import write_skill

    from constellation.skill_search import find_skills

    root = tmp_path / "invented-setup"
    for n in range(5):
        write_skill(root, f"fonts{n}", "# Website typography", description="Typography helper")
    assert len(find_skills("typography", root, cache=tmp_path / "i.json", limit=2)[0]) == 2
    assert len(find_skills("typography", root, cache=tmp_path / "i.json", limit=4)[0]) == 4
