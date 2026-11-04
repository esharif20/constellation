"""Warning text is a contract: the viewer groups warnings by these prefixes (frontend/src/graph/model.ts, groupWarnings)."""

from pathlib import Path

from constellation import scan

ROOT = Path(__file__).parent.parent
REPO = ROOT.parent if ROOT.name == "mutants" else ROOT  # mutmut runs tests from a copy that has no frontend/
PREFIXES = {
    "Offline": "mode",
    "frontmatter is not valid YAML": "loose",
    "no frontmatter in": "loose-missing",
    "skipped ": "missing",
    "usage:": "usage",
    "could not label": "degraded",
    "could not verify": "degraded",
    "could not count": "degraded",
    "could not cluster": "degraded",
    "could not save the": "cache",
    "could not read skill lock": "lock",
}


def _skill(root, name, text):
    (root / "skills" / name).mkdir(parents=True)
    (root / "skills" / name / "SKILL.md").write_text(text)


def test_home_paths_are_written_with_a_tilde_and_the_scan_never_holds_the_home_folder(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config = home / ".claude"
    _skill(config, "loose", "---\nname: loose\ndescription: Use when asked: draw\n---\n")
    _skill(config, "nodesc", "---\nname: nodesc\n---\n")
    _skill(config, "bare", "no frontmatter\n")

    constellation = scan(config, offline=True)

    assert any(w.endswith("(~/.claude/skills/loose/SKILL.md)") for w in constellation.warnings)
    assert any("(~/.claude/skills/nodesc/SKILL.md)" in w for w in constellation.warnings)
    assert any(w == "no frontmatter in ~/.claude/skills/bare/SKILL.md" for w in constellation.warnings)
    assert str(home) not in "\n".join(constellation.warnings)


def test_paths_outside_home_are_left_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    _skill(tmp_path, "bare", "no frontmatter\n")

    assert any(str(tmp_path) in w for w in scan(tmp_path, offline=True).warnings)


def test_every_warning_prefix_the_viewer_groups_on_is_still_emitted_and_still_named_in_the_viewer(tmp_path):
    _skill(tmp_path, "loose", "---\nname: loose\ndescription: Use when asked: draw\n---\n")
    _skill(tmp_path, "nodesc", "---\nname: nodesc\n---\n")
    _skill(tmp_path, "bare", "no frontmatter\n")
    emitted = scan(tmp_path, offline=True).warnings
    for prefix in ("Offline", "frontmatter is not valid YAML", "no frontmatter in", "skipped "):
        assert any(w.startswith(prefix) for w in emitted), prefix

    # The rest need a provider or the filesystem to fail; pin their literal text in the source instead.
    source = "".join(p.read_text() for p in (ROOT / "src" / "constellation").glob("*.py"))
    viewer = (REPO / "frontend" / "src" / "graph" / "model.ts").read_text()
    for prefix in (
        "usage: ",
        "could not label",
        "could not verify",
        "could not count",
        "could not cluster",
        "could not save the",
        "could not read skill lock",
    ):
        assert prefix in source, prefix
    for prefix in PREFIXES:
        assert f'"{prefix}' in viewer, prefix
