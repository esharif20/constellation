"""Redaction removes secrets without garbling ordinary text: short or prose-shaped values never become needles (invented data only)."""

import json

import pytest
from fakes import FakeEmbedder, write_skill

from constellation import public_export, server
from constellation.cli import main
from constellation.redact import REDACTED, redact
from constellation.skill_search import find_skills

SECRET = "Q7zInventedCredentialValue-91"
ENV_SECRET = "invented-env-value-4471"
PEM = "-----BEGIN INVENTED KEY-----\nMIIBinventedKeyBody0123\n-----END INVENTED KEY-----"
PROSE = "Use when the user wants to scrape pages that need clicks or logins, beyond what Claude can do. Not for local file operations."
NAMES = ["obsidian-tikz", "design-taste-frontend", "vercel-plugin", "site-section"]
# Body lines the find path learns needles from: every value here is prose or too short, so none may hide ordinary text.
BODY = "auth: required\n--api-key your-key-here\ntoken: -\npassword: want\nkey: [\nsecret: to\n# A site section\nFor local file operations."


def test_short_and_marker_pieces_are_never_needles():
    text = f"obsidian-tikz wants to need clicks or logins {REDACTED}"
    assert redact(text, known=["", " ", "-", "want", "to", "need", "[", "]", "log", "[REDACTED", "REDACTED]", "1234567"]) == text


def test_a_marker_is_never_redacted_again():
    assert redact(f"{SECRET} then [REDACTED]", known=[SECRET, "[REDACTED]", "REDACTED"]) == "[REDACTED] then [REDACTED]"


def test_needles_are_escaped_literals():
    needle = "a.b*c+d?e|(f)"
    assert redact(f"aXbbbcde f {needle}", known=[needle]) == f"aXbbbcde f {REDACTED}"


def test_the_longest_known_value_wins_where_two_overlap():
    assert redact(f"x {SECRET}-tail y", known=[SECRET, f"{SECRET}-tail"]) == "x [REDACTED] y"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config = tmp_path / "invented-config"
    config.mkdir()
    credentials = {
        "claudeAiOauth": {"accessToken": SECRET, "scopes": ["user:x", "-", " ", ""], "expiresAt": 1234567890123, "ok": True},
        "pem": PEM,
        "url": "https://invented.example/path?q=1",
        "short": "want",
    }
    (config / ".credentials.json").write_text(json.dumps(credentials))
    (config / "settings.json").write_text(json.dumps({"env": {"INVENTED_TOKEN": ENV_SECRET, "FLAG": "true", "DASH": "-"}}))
    for name in NAMES:
        write_skill(config, name, BODY, description=PROSE)
    write_skill(config, "leaky-skill", BODY, description=f"Deploys with {SECRET} and {ENV_SECRET}")
    monkeypatch.setattr("constellation.cli.load_env", lambda: None)
    static = tmp_path / "invented-build"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html></html>")
    monkeypatch.setattr(public_export, "STATIC", static)
    monkeypatch.setattr(server, "STATIC", static)
    return config


def test_ordinary_words_and_hyphens_are_never_redacted(setup, tmp_path):
    out = tmp_path / "scan.json"
    assert main(["scan", str(setup), "--offline", "--no-origins", "--out", str(out)], embedder=FakeEmbedder({})) == 0
    saved = json.loads(out.read_text())
    items = {i["name"]: i for i in saved["items"]}
    assert set(NAMES) <= set(items)
    for name in NAMES:
        assert items[name]["description"] == PROSE and items[name]["id"].endswith(f":skill:{name}")
    assert items["leaky-skill"]["description"] == "Deploys with [REDACTED] and [REDACTED]"
    text = out.read_text()
    assert SECRET not in text and ENV_SECRET not in text and "REDACTED]REDACTED" not in text

    hits, warnings = find_skills("scrape pages", setup, cache=tmp_path / "index.json")
    found = {h["name"]: h for h in hits}
    assert warnings == [] and set(NAMES) <= set(found)
    for name in NAMES:
        assert found[name]["description"] == PROSE and found[name]["invoke"] == f"/{name}"
    content = (tmp_path / "index.json").read_text()
    assert '["heading", "A site section"]' in content and "REDACTED]REDACTED" not in content
