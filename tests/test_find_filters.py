"""#80: last-used and cost on find hits, the kind/forgotten/origin filters, and Ask answering from the same find."""

import json
from datetime import date

from constellation import chat, cli, find_view, skill_search
from constellation.cli_reports import Style

TODAY = date(2026, 11, 1)


def hit(id_="a", invoke="/a", kind="skill", **extra):
    return {"id": id_, "kind": kind, "name": id_, "description": "Does a thing", "invoke": invoke, "why": "name", **extra}


SCAN = {
    "usage_window": {"files": 3},
    "usage": {"a": {"count": 2, "last_used": "2026-10-30T10:00:00Z"}, "b": {"count": 1, "last_used": "2026-09-01"}},
    "costs": {"a": {"always_on": 1234}},
}


def test_annotate_reads_usage_and_cost_by_id():
    a, b, c = find_view.annotate([hit("a"), hit("b"), hit("c")], SCAN)
    assert (a["last_used"], a["always_on"], a["usage_known"]) == ("2026-10-30", 1234, True)
    assert (b["last_used"], b["always_on"]) == ("2026-09-01", None)
    assert (c["last_used"], c["usage_known"]) == (None, True)
    assert find_view.annotate([hit()], None)[0]["usage_known"] is False


def test_last_seen_words():
    def seen(last, known=True):
        return find_view.last_seen({"last_used": last, "usage_known": known}, TODAY)

    assert seen("2026-11-01") == "last used today"
    assert seen("2026-10-31") == "last used 1 day ago"
    assert seen("2026-10-26") == "last used 6 days ago"
    assert seen("2026-10-25") == "last used 1 week ago"
    assert seen("2026-10-11") == "last used 3 weeks ago"
    assert seen("2026-10-03") == "last used 4 weeks ago"
    assert seen("2026-10-02") == "last used 1 month ago"
    assert seen("2026-07-01") == "last used 4 months ago"
    assert seen(None) == "never seen used"
    assert seen(None, False) == "usage not read"
    assert seen("2026-10-31", False) == "usage not read"


def test_cost_text():
    assert find_view.cost_text({"always_on": 1234}) == "1,234 tokens every session"
    assert find_view.cost_text({"always_on": 0}) == "0 tokens every session"
    assert find_view.cost_text({"always_on": None}) == "cost unknown"


def test_forgotten_boundary_is_thirty_days():
    def forgotten(last, known=True):
        return find_view.is_forgotten({"last_used": last, "usage_known": known}, TODAY)

    assert forgotten("2026-10-02") is True  # exactly 30 days
    assert forgotten("2026-10-03") is False  # 29 days
    assert forgotten(None) is True
    assert forgotten(None, False) is False  # unknown usage is not evidence of neglect
    assert forgotten("2026-01-01", False) is False


def test_refine_filters_by_forgotten_and_origin():
    hits = find_view.annotate([hit("a"), hit("b", "/plug:b"), hit("c", "/plug:c")], SCAN)
    names = lambda rows: [h["id"] for h in rows]  # noqa: E731
    assert names(find_view.refine(hits, TODAY)) == ["a", "b", "c"]
    assert names(find_view.refine(hits, TODAY, forgotten=True)) == ["b", "c"]
    assert names(find_view.refine(hits, TODAY, origin_filter="plugin")) == ["b", "c"]
    assert names(find_view.refine(hits, TODAY, origin_filter="yours")) == ["a"]
    assert names(find_view.refine(hits, TODAY, forgotten=True, origin_filter="yours")) == []


def test_card_shows_last_seen_and_cost_only_for_annotated_hits():
    [annotated] = find_view.annotate([hit("a")], SCAN)
    out = find_view.render([annotated], "q", 0, Style(), 80, today=TODAY)
    assert out[5:7] == ["   last used 2 days ago · 1,234 tokens every session", "   /a"]
    assert "last used" not in "".join(find_view.render([hit("a")], "q", 0, Style(), 80))


def test_mixed_kinds_say_matches():
    out = find_view.render([hit("a"), hit("b", "@b", "agent")], "q", 0, Style(), 80)
    assert out[0] == 'Found 2 matches for "q"'
    assert find_view.render([hit("b", "@b", "agent")], "q", 0, Style(), 80)[0] == 'Found 1 match for "q"'


def test_json_carries_last_seen_and_cost():
    [row] = find_view.as_json(find_view.annotate([hit("a")], SCAN), "q", [], TODAY)["hits"]
    assert (row["last_used"], row["always_on"], row["last_seen"]) == ("2026-10-30", 1234, "last used 2 days ago")


def _setup(tmp_path, monkeypatch):
    from fakes import write_skill

    root = tmp_path / "invented-setup"
    write_skill(root, "cabinet", "# Website typography\nA small collection.", description="Assorted reference material")
    (root / "agents").mkdir()
    (root / "agents" / "typesetter.md").write_text("---\nname: typesetter\ndescription: Website typography helper\n---\nbody\n")
    monkeypatch.setattr(skill_search, "DEFAULT_CACHE", tmp_path / "private" / "skill-content.json")
    return root


def test_find_cli_filters_and_shows_last_used(tmp_path, monkeypatch, capsys):
    root = _setup(tmp_path, monkeypatch)
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({"usage_window": {"files": 1}, "usage": {}, "costs": {}}))
    args = ["find", "typography", "--config-dir", str(root), "--file", str(scan)]
    assert cli.main([*args, "--json"]) == 0
    [row] = json.loads(capsys.readouterr().out)["hits"]
    assert (row["name"], row["last_seen"], row["always_on"]) == ("cabinet", "never seen used", None)
    assert cli.main([*args, "--json", "--kind", "agent"]) == 0
    [row] = json.loads(capsys.readouterr().out)["hits"]
    assert (row["name"], row["kind"], row["invoke"]) == ("typesetter", "agent", "@typesetter")
    assert cli.main([*args, "--forgotten", "--origin", "plugin"]) == 0
    assert 'No match for "typography"' in capsys.readouterr().out
    assert cli.main([*args, "--forgotten", "--origin", "yours"]) == 0
    out = capsys.readouterr().out
    assert "cabinet" in out and "never seen used · cost unknown" in out


def test_find_cli_without_a_saved_scan_says_usage_not_read(tmp_path, monkeypatch, capsys):
    root = _setup(tmp_path, monkeypatch)
    assert cli.main(["find", "typography", "--config-dir", str(root), "--file", str(tmp_path / "none.json"), "--forgotten"]) == 0
    assert 'No match for "typography"' in capsys.readouterr().out  # unknown usage is never "forgotten"


def test_ask_intent_and_terms():
    for q in ("What skill helps with typography?", "which agent can handle tidy commits", "is there a skill for pdf forms?"):
        assert chat._intent(q) == "findskill", q
    assert chat._intent("which skills cost the most?") != "findskill"
    assert chat._find_terms("What skill helps with typography for websites?") == "typography for websites"
    assert chat._find_terms("which skill handles typography") == "which skill handles typography"


def test_ask_answers_with_the_top_three_find_hits():
    asked = []
    hits = [{**h, "invoke": f"/{h['id']}"} for h in find_view.annotate([hit(n) for n in "abcd"], SCAN)]

    def finder(q):
        asked.append(q)
        return hits, []

    answer = _ask_with(finder, "What skill helps with typography?")
    assert asked == ["typography"]
    assert [r["name"] for r in answer["blocks"]["rows"]] == ["a", "b", "c"]
    value = answer["blocks"]["rows"][0]["value"]  # today is the real date here
    assert value.startswith("/a · last used ") and value.endswith(" · 1,234 tokens every session")
    assert answer["blocks"]["more"] == 1
    assert answer["actions"] == [{"kind": "highlight", "item_ids": ["a", "b", "c"]}]


def test_ask_without_a_config_dir_or_matches():
    assert "needs your local" in _ask_with(None, "which skill helps with typography")["blocks"]["headline"]
    assert "could not find" in _ask_with(lambda q: ([], []), "which skill helps with typography")["blocks"]["headline"]


def _ask_with(finder, question):
    from constellation.assessment import compute

    data = {
        "items": [{"id": n, "name": n, "kind": "skill", "description": f"{n} does a thing. More."} for n in "abcd"],
    }
    local = chat.LocalChat()
    return local.answer(data, question, [], lambda items: None, compute(data, None, None), finder)


def test_api_find_filters_and_ask_use_the_same_backend(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from constellation import server

    root = _setup(tmp_path, monkeypatch)
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(server, "STATIC", static)
    scan = tmp_path / "scan.json"
    scan.write_text(
        json.dumps(
            {
                "usage_window": {"files": 1},
                "usage": {},
                "costs": {},
                "items": [
                    {"id": "claude-code:skill:cabinet", "name": "cabinet", "kind": "skill", "description": "Assorted reference material"}
                ],
            }
        )
    )
    client = TestClient(
        server.create_app(scan, checklist=tmp_path / "c.md", config_dir=root, embedder=lambda t: [[0.0] * 4] * len(t)),
        base_url="http://127.0.0.1:8765",
    )
    [row] = client.get("/api/find", params={"q": "typography"}).json()["results"]
    assert (row["last_seen"], row["cost"]) == ("never seen used", "cost unknown")
    assert client.get("/api/find", params={"q": "typography", "origin": "plugin"}).json()["results"] == []
    assert (
        client.get("/api/find", params={"q": "typography", "forgotten": "true", "origin": "yours"}).json()["results"][0]["name"]
        == "cabinet"
    )
    assert [r["name"] for r in client.get("/api/find", params={"q": "typography", "kind": "agent"}).json()["results"]] == ["typesetter"]
    assert client.get("/api/find", params={"q": "typography", "kind": "bogus"}).status_code == 422
    answer = client.post("/api/chat", json={"question": "What skill helps with typography?"}).json()
    assert [r["name"] for r in answer["blocks"]["rows"]] == ["cabinet"]
    assert "never seen used" in answer["blocks"]["rows"][0]["value"]
