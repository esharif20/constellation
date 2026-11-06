import json

from constellation import cli


def scan_file(tmp_path, assessments=True):
    items = [
        {
            "id": "s:react",
            "kind": "skill",
            "name": "react-patterns",
            "description": "React hooks and TypeScript.",
            "source": "x",
        },
        {"id": "s:pdf", "kind": "skill", "name": "pdf-forms", "description": "Fill and merge PDF forms.", "source": "x"},
        {"id": "s:pytest", "kind": "skill", "name": "pytest-helper", "description": "Write pytest fixtures and tests.", "source": "x"},
        {"id": "p:off", "kind": "plugin", "name": "bundle", "description": "react everything", "source": "x"},
    ]
    data = {
        "items": items,
        "costs": {"s:react": {"always_on": 40}, "s:pdf": {"always_on": 55}, "s:pytest": {"always_on": 30}},
        "assessments": {"s:pdf": {"tier": "redundant", "label": "Redundant"}} if assessments else {},
    }
    f = tmp_path / "scan.json"
    f.write_text(json.dumps(data))
    return f


def project(tmp_path):
    p = tmp_path / "app"
    p.mkdir()
    (p / "README.md").write_text("A React dashboard with hooks and components.")
    (p / "package.json").write_text(
        json.dumps({"name": "dash", "dependencies": {"react": "1", "typescript": "5"}, "scripts": {"build": "x", "test": "y"}})
    )
    (p / ".env").write_text("SECRET=1")
    return p


def test_text_output_exact(tmp_path, capsys):
    p, f = project(tmp_path), scan_file(tmp_path)
    assert cli.main(["advise", str(p), "--scan", str(f)]) == 0
    assert capsys.readouterr().out == (
        "Advice for dash (local words only; nothing sent)\n\n"
        "Installed Items that fit, best first:\n"
        "  react-patterns (skill): matches react, typescript, hook, 40 tokens always on\n"
        "\nLikely noise for this project:\n"
        "  pdf-forms (skill): no match here; scan verdict: redundant, 55 tokens always on\n"
        "\nDraft CLAUDE.md (--write saves it as a new file):\n"
        "  # dash\n  \n  Stack: react, typescript\n  Conventions:\n  - Language: TypeScript\n  Commands:\n"
        "  - npm run build\n  - npm run test\n  Skills worth using here:\n  - react-patterns: matches react, typescript, hook\n"
    )


def test_json_and_no_verdict_fallback(tmp_path, capsys):
    p, f = project(tmp_path), scan_file(tmp_path, assessments=False)
    assert cli.main(["advise", str(p), "--scan", str(f), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in out["fits"]] == ["react-patterns"]
    assert [(r["name"], r["reason"]) for r in out["noise"]] == [
        ("pdf-forms", "no match here and always on"),
        ("pytest-helper", "no match here and always on"),
    ]
    assert out["always_on_fits"] == 40 and len(out["draft"].splitlines()) < 25


def test_write_never_overwrites(tmp_path, capsys):
    p, f = project(tmp_path), scan_file(tmp_path)
    assert cli.main(["advise", str(p), "--scan", str(f), "--write", "--dry-run"]) == 0
    assert not (p / "CLAUDE.md").exists()
    assert cli.main(["advise", str(p), "--scan", str(f), "--write"]) == 0
    first = (p / "CLAUDE.md").read_text()
    assert first.startswith("# dash\n") and "SECRET" not in first
    (p / "CLAUDE.md").write_text("mine")
    assert cli.main(["advise", str(p), "--scan", str(f), "--write"]) == 2
    assert (p / "CLAUDE.md").read_text() == "mine"
    assert "already exists" in capsys.readouterr().err


def test_missing_folder_and_pyproject(tmp_path, capsys):
    f = scan_file(tmp_path)
    assert cli.main(["advise", str(tmp_path / "nope"), "--scan", str(f)]) == 2
    p = tmp_path / "py"
    p.mkdir()
    (p / "pyproject.toml").write_text('[project]\nname="svc"\ndependencies=["pytest>=8"]\n[project.scripts]\nsvc="x:y"\n')
    assert cli.main(["advise", str(p), "--scan", str(f), "--json"]) == 0
    draft = json.loads(capsys.readouterr().out)["draft"]
    assert "Stack: pytest\nConventions:\n- Tests: pytest\nCommands:\n- svc\n" in draft
