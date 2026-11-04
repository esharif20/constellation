import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.server import create_app


@pytest.fixture(autouse=True)
def offline_tracing(monkeypatch):
    """Intercept the fallback transport too: nested contexts replace the outer client."""
    import requests
    from langsmith import run_trees, tracing_context
    from langsmith.client import Client

    class RecordingClient(Client):
        def __init__(self):
            self.calls = []

        def create_run(self, *args, **kwargs):
            self.calls.append((args, kwargs))

        def update_run(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    client = RecordingClient()

    def forbidden(*args, **kwargs):
        pytest.fail("A real tracing client or external HTTP transport must never be used")

    monkeypatch.setattr(Client, "__init__", forbidden)
    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setattr(run_trees, "get_cached_client", lambda **kwargs: client)
    with tracing_context(enabled=False, client=client):
        yield client


@pytest.fixture
def chat(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(server, "STATIC", static)
    data = {
        "items": [
            {"id": "mail", "kind": "skill", "name": "mail-helper", "description": "Send email and draft messages", "source": "PRIVATE"},
            {"id": "draft", "kind": "agent", "name": "draft", "description": "Write email drafts"},
            {"id": "unknown", "kind": "mcp_server", "name": "unknown", "description": "Calendar events"},
        ],
        "costs": {"mail": {"always_on": 400, "on_use": 800}, "draft": {"always_on": 20, "on_use": None}},
        "overlaps": [{"a_id": "mail", "b_id": "draft", "verdict": "duplicate", "reason": "Both draft email"}],
        "usage": {"mail": {"count": 2}, "draft": {"count": 0}},
        "usage_window": {"files": 3, "first": "2026-10-01", "last": "2026-11-01", "skipped": 0},
    }
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(data))
    client = TestClient(create_app(path, checklist=tmp_path / "checklist.md"), base_url="http://127.0.0.1:8765")
    return client, path, data


def ask(chat, question, **body):
    response = chat[0].post("/api/chat", json={"question": question, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_email_search_is_free_grounded_and_cached(chat, monkeypatch):
    import constellation
    import constellation.env as env

    def forbidden(*args, **kwargs):
        pytest.fail("chat must not access credentials, setup, or providers")

    for name in ("guarded", "guarded_embed", "guarded_count", "scan"):
        monkeypatch.setattr(constellation, name, forbidden)
    monkeypatch.setattr(env, "load_env", forbidden)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "invented-configured-key")
    response = ask(chat, "What can help me send email?")
    assert response == {
        "answer": "Matching Items:\n- mail-helper (skill): Send email and draft messages\n- draft (agent): Write email drafts",
        "actions": [{"kind": "highlight", "item_ids": ["mail", "draft"]}],
        "mode": "local",
        "cached": False,
    }
    assert ask(chat, "What can help me send email?") == {**response, "cached": True}
    assert "PRIVATE" not in str(response)


def test_top_costs_and_unknown_costs_are_grounded(chat):
    result = ask(chat, "What are my top costs?")
    assert (
        result["answer"] == "Highest always-on Context costs:\n- mail-helper: 400 tokens\n- draft: 20 tokens\n"
        "1 Items have unknown cost; unknown is never counted as 0."
    )
    assert result["actions"] == [{"kind": "highlight", "item_ids": ["mail", "draft"]}]
    chat[2]["costs"] = {}
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "What are my top costs?")
    assert result["cached"] is False
    assert result["answer"] == "Token costs were not measured in this scan.\n3 Items have unknown cost; unknown is never counted as 0."
    assert result["actions"] == []


def test_known_duplicate_and_wrapper_pairs(chat):
    assert (
        ask(chat, "Show duplicates")["answer"]
        == "Known duplicate/wrapper Overlaps:\n- Remove one of these two: draft (agent) and mail-helper (skill). Both draft email"
    )
    chat[2]["overlaps"][0]["verdict"] = "wrapper"
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "What wrappers are installed?")
    assert result["cached"] is False
    assert (
        result["answer"] == "Known duplicate/wrapper Overlaps:\n- mail-helper (skill) only calls draft (agent); "
        "consider using draft (agent) directly. Both draft email"
    )
    assert result["actions"] == [{"kind": "highlight", "item_ids": ["mail", "draft"]}]


def test_usage_and_never_seen_stay_local_with_window(chat):
    result = ask(chat, "Which Items were never used?")
    assert (
        result["answer"] == "Never seen in the scanned transcripts:\n- draft\n"
        "Covers 3 transcript files from 2026-10-01 to 2026-11-01 (32 days); 0 files skipped. "
        "Claude Code deletes old transcripts, so 'never seen' covers only these files and is not proof an Item is unused."
    )
    assert result["actions"] == [{"kind": "highlight", "item_ids": ["draft"]}]
    assert (
        ask(chat, "Show usage")["answer"] == "Recorded usage:\n- draft: 0 uses\n- mail-helper: 2 uses\n- unknown: usage unknown\n"
        "Covers 3 transcript files from 2026-10-01 to 2026-11-01 (32 days); 0 files skipped. "
        "Claude Code deletes old transcripts, so 'never seen' covers only these files and is not proof an Item is unused."
    )
    chat[2]["usage"]["draft"]["count"] = 4
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "Which Items were never used?")["answer"].startswith("No Items were never seen in this scan.\nCovers")
    chat[2].pop("usage_window")
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "Show usage")["answer"] == "Usage was not read in this scan."


def test_chat_preserves_current_scan_usage_coverage_and_skipped_files(chat):
    chat[2]["usage_window"]["skipped"] = 2
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "Show usage")
    assert "from 2026-10-01 to 2026-11-01 (32 days); 2 files skipped" in result["answer"]
    assert "not proof an Item is unused" in result["answer"]


def test_selected_followup_and_named_explanation(chat):
    expected = "Item details:\n- mail-helper (skill): Send email and draft messages\n  Always-on: 400 tokens; on-use: 800 tokens."
    assert ask(chat, "Explain mail-helper")["answer"] == expected
    assert ask(chat, "Explain this", selected_ids=["mail"])["answer"] == expected
    assert ask(chat, "Explain unknown")["answer"].endswith("Always-on: unknown; on-use: unknown.")
    assert ask(chat, "Focus mail-helper")["actions"] == [{"kind": "focus", "item_ids": ["mail"]}]
    assert ask(chat, "Filter email")["actions"] == [{"kind": "highlight", "item_ids": ["draft", "mail"]}]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": " \n "},
        {"question": "x" * 1001},
        {"question": 5},
        {"question": "email", "selected_ids": ["mail"] * 9},
        {"question": "email", "selected_ids": [1]},
        {"question": "email", "model": "paid"},
    ],
)
def test_chat_validates_bounded_explicit_submission(chat, body):
    assert chat[0].post("/api/chat", json=body).status_code == 422


@pytest.mark.parametrize("field,value", [("id", 1), ("name", None), ("kind", []), ("description", {})])
def test_chat_rejects_malformed_metadata_types(chat, field, value):
    chat[2]["items"][0][field] = value
    chat[1].write_text(json.dumps(chat[2]))
    assert chat[0].post("/api/chat", json={"question": "email"}).status_code == 404


def test_chat_accepts_question_and_selection_boundaries(chat):
    assert ask(chat, "e")["mode"] == "local"
    assert ask(chat, "e" * 1000, selected_ids=["mail"] * 8)["mode"] == "local"
    assert chat[0].post("/api/chat", json={"question": "email", "selected_ids": ["missing"]}).status_code == 404


@pytest.mark.parametrize("text", ["", "null", "[]", "{}", '{"items":null}', '{"items":[{}]}', '{"items":[{"id":[]}]}'])
def test_chat_rejects_malformed_scan_without_exposing_path(chat, text):
    chat[1].write_text(text)
    response = chat[0].post("/api/chat", json={"question": "email"})
    assert response.status_code == 404
    assert response.json() == {"detail": "The saved scan could not be read"}


@pytest.mark.parametrize(
    "question", ['email" OR * NOT (', "email'; DROP TABLE metadata; --", "C++", '"', "mail-helper", "mcp__email__send"]
)
def test_hostile_fts_syntax_is_only_literal_words(chat, question):
    result = ask(chat, question)
    assert set(id_ for action in result["actions"] for id_ in action["item_ids"]) <= {"mail", "draft", "unknown"}
    assert ask(chat, "email")["actions"]


def test_unknown_semantic_matches_and_empty_scan_are_honest(chat):
    result = ask(chat, "Communicate electronically")
    assert result["answer"] == "No matching Items found. Try an Item name or a word from its description."
    assert result["actions"] == []
    chat[1].write_text('{"items":[]}')
    assert ask(chat, "email")["actions"] == []
    assert ask(chat, "duplicates")["answer"] == "No known duplicate/wrapper Overlaps in this scan."
    assert ask(chat, "usage")["answer"] == "Usage was not read in this scan."


def test_redaction_precedes_metadata_shortening_and_indexing(chat):
    secret = "sk-" + "Z" * 30
    chat[2]["items"][0]["description"] = "a " * 490 + secret + " end"
    chat[2]["items"][0]["name"] = "email " + secret
    chat[2]["items"][0]["kind"] = "skill " + secret
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "email " + secret)
    assert secret not in result["answer"]
    assert "sk-" not in result["answer"]
    assert "[REDACTED]" in result["answer"]
    assert ask(chat, "email sk-" + "Y" * 30)["cached"] is True
    assert ask(chat, "Z" * 15)["actions"] == []


def test_cache_follows_selection_scan_costs_and_usage_but_ignores_unrelated_provenance(chat):
    first = ask(chat, "Explain this", selected_ids=["mail"])
    assert first["cached"] is False
    assert ask(chat, "Explain this", selected_ids=["draft"])["cached"] is False
    chat[2]["items"][0]["source"] = "different local path"
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "Explain this", selected_ids=["mail"])["cached"] is True
    chat[2]["usage"]["mail"]["count"] = 99
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "Explain this", selected_ids=["mail"])["cached"] is True
    assert "99 uses" in ask(chat, "usage")["answer"]
    chat[2]["items"][0]["description"] = "Changed email description"
    chat[2]["costs"]["mail"]["always_on"] = 500
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "Explain this", selected_ids=["mail"])
    assert result["cached"] is False
    assert "Changed email description" in result["answer"] and "500 tokens" in result["answer"]


def test_concurrent_identical_requests_share_memory_cache_and_close_sqlite(chat, monkeypatch):
    import sqlite3

    connections = []
    original = sqlite3.connect

    class RecordingConnection(sqlite3.Connection):
        def close(self):
            connections.append(self)
            super().close()

    monkeypatch.setattr(sqlite3, "connect", lambda *args: original(*args, factory=RecordingConnection, check_same_thread=False))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ask(chat, "email"), range(8)))
    assert sum(not result["cached"] for result in results) == 1
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")
    before = {p: p.read_bytes() for p in chat[1].parent.rglob("*") if p.is_file()}
    for n in range(127):
        ask(chat, f"email query {n}")
    assert ask(chat, "email")["cached"] is True
    ask(chat, "email query 127")
    assert ask(chat, "email")["cached"] is True
    assert ask(chat, "email query 0")["cached"] is False
    assert {p: p.read_bytes() for p in chat[1].parent.rglob("*") if p.is_file()} == before


def test_exact_names_precede_lexical_matches_and_selection_precedes_names(chat):
    chat[2]["items"] += [
        {"id": "exact", "name": "email", "kind": "skill", "description": "unrelated context " * 8},
        {"id": "tie-z", "name": "z", "kind": "skill", "description": "lexical"},
        {"id": "tie-a", "name": "a", "kind": "skill", "description": "lexical"},
    ]
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "email")["actions"][0]["item_ids"] == ["exact", "draft", "mail"]
    assert ask(chat, "email", selected_ids=["unknown"])["actions"][0]["item_ids"] == ["exact", "draft", "mail"]
    assert ask(chat, "lexical")["actions"][0]["item_ids"] == ["tie-a", "tie-z"]
    assert ask(chat, "Explain email")["actions"][0]["item_ids"] == ["exact"]


def test_five_results_cost_order_zero_and_omitted_search_matches(chat):
    chat[2]["items"] += [{"id": f"extra-{n}", "name": f"extra-{n}", "kind": "skill", "description": "email"} for n in range(6)]
    chat[2]["costs"].update({f"extra-{n}": {"always_on": n, "on_use": None} for n in range(6)})
    chat[1].write_text(json.dumps(chat[2]))
    costs = ask(chat, "top costs")
    assert costs["actions"] == [{"kind": "highlight", "item_ids": ["mail", "draft", "extra-5", "extra-4", "extra-3"]}]
    assert costs["answer"].endswith("1 Items have unknown cost; unknown is never counted as 0.")
    search = ask(chat, "email")
    assert len(search["actions"][0]["item_ids"]) == 5
    assert search["answer"].endswith("More matches omitted; narrow your question.")
    assert "Always-on: 0 tokens; on-use: unknown." in ask(chat, "Explain this", selected_ids=["extra-0"])["answer"]


def test_dangling_overlaps_and_costs_cannot_create_unknown_graph_ids(chat):
    chat[2]["overlaps"] += [
        {"a_id": "fake", "b_id": "mail", "verdict": "wrapper", "reason": "Must not appear"},
        {"a_id": "mail", "b_id": "other-fake", "verdict": "duplicate", "reason": "Must not appear"},
    ]
    chat[2]["costs"]["fake"] = {"always_on": 99999}
    chat[1].write_text(json.dumps(chat[2]))
    assert "Must not appear" not in ask(chat, "overlaps")["answer"]
    assert "99999" not in ask(chat, "costs")["answer"]
    assert ask(chat, "costs")["actions"][0]["item_ids"] == ["mail", "draft"]


def test_usage_window_and_redacted_overlap_reasons(chat):
    chat[2]["usage_window"]["files"] = 0
    chat[2]["overlaps"][0]["reason"] = "api_key=planted-value"
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "usage")["answer"] == "No transcripts found."
    assert "api_key=[REDACTED]" in ask(chat, "overlaps")["answer"]
    assert "planted-value" not in str(ask(chat, "overlaps"))
    chat[1].unlink()
    response = chat[0].post("/api/chat", json={"question": "email"})
    assert response.status_code == 404
    assert response.json() == {"detail": "The saved scan could not be read"}


def test_post_requires_json_and_accepts_same_origin_charset(chat):
    client = chat[0]
    for headers in ({}, {"content-type": "text/plain"}):
        assert client.post("/api/chat", content='{"question":"email"}', headers=headers).status_code == 415
    for site in ("same-origin", "none"):
        response = client.post(
            "/api/chat",
            content='{"question":"email"}',
            headers={"content-type": "application/json; charset=utf-8", "origin": "http://127.0.0.1:8765", "sec-fetch-site": site},
        )
        assert response.status_code == 200


def test_explicit_explanations_and_usage_win_over_words_inside_names(chat):
    chat[2]["items"] += [
        {"id": "named-cost", "name": "cost-helper", "kind": "skill", "description": "Estimate budgets"},
        {"id": "named-unused", "name": "unused-helper", "kind": "skill", "description": "Maintain inventory"},
    ]
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "Explain cost-helper")["answer"].startswith("Item details:\n- cost-helper (skill): Estimate budgets")
    assert ask(chat, "Describe unused-helper")["answer"].startswith("Item details:\n- unused-helper (skill): Maintain inventory")
    assert ask(chat, "Which unused Items cost most?")["answer"].startswith("Never seen in the scanned transcripts:\n- draft\n")


def test_metadata_display_is_shortened_only_after_redaction(chat):
    secret = "sk-" + "Z" * 30
    chat[2]["items"][0].update(name="n" * 90 + secret, kind="k" * 34 + secret, description="d" * 154 + secret)
    chat[2]["overlaps"][0]["reason"] = "r" * 234 + secret
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "Explain this", selected_ids=["mail"])
    assert (
        result["answer"]
        == "Item details:\n- "
        + "n" * 90
        + "[REDAC… ("
        + "k" * 34
        + "[REDAC…): "
        + "d" * 154
        + "[REDAC…\n  Always-on: 400 tokens; on-use: 800 tokens."
    )
    pairs = ask(chat, "duplicates")["answer"]
    assert "r" * 234 + "[REDAC…" in pairs
    assert secret not in result["answer"] + pairs


def test_local_graph_disables_configured_external_tracing(chat, offline_tracing):
    from langsmith import tracing_context

    with tracing_context(enabled=True, client=offline_tracing):
        assert ask(chat, "email")["mode"] == "local"
    assert offline_tracing.calls == []


def test_cost_questions_honor_named_or_selected_scope_and_decline_unsupported_totals(chat):
    named = ask(chat, "What is the on-use cost of mail-helper?")
    assert (
        named["answer"]
        == "Item details:\n- mail-helper (skill): Send email and draft messages\n  Always-on: 400 tokens; on-use: 800 tokens."
    )
    assert named["actions"] == [{"kind": "highlight", "item_ids": ["mail"]}]
    selected = ask(chat, "What does this cost?", selected_ids=["unknown"])
    assert selected["answer"] == "Item details:\n- unknown (mcp_server): Calendar events\n  Always-on: unknown; on-use: unknown."
    for question in ("What is the total always-on cost?", "Which Items have the highest on-use cost?"):
        result = ask(chat, question)
        assert (
            result["answer"]
            == "Local chat ranks always-on Context costs. Ask for top costs, or name/select an Item to see its always-on and on-use costs."
        )
        assert result["actions"] == []


def test_counts_and_global_costs_ignore_stale_selection(chat):
    result = ask(chat, "How many Items do I have?")
    assert result == {"answer": "The current scan contains 3 Items.", "actions": [], "mode": "local", "cached": False}
    result = ask(chat, "What are my top costs?", selected_ids=["unknown"])
    assert result["actions"] == [{"kind": "highlight", "item_ids": ["mail", "draft"]}]


def test_named_usage_and_overlap_questions_do_not_return_unrelated_rows(chat):
    assert ask(chat, "Usage of draft")["answer"].startswith("Recorded usage:\n- draft: 0 uses\nCovers")
    assert ask(chat, "Usage of this", selected_ids=["mail"])["answer"].startswith("Recorded usage:\n- mail-helper: 2 uses\nCovers")
    assert ask(chat, "Duplicates of unknown")["actions"] == []
    assert ask(chat, "Duplicates of draft")["actions"] == [{"kind": "highlight", "item_ids": ["draft", "mail"]}]


def test_stop_words_and_redaction_markers_do_not_create_search_matches(chat):
    secret = "sk-" + "Z" * 30
    chat[2]["items"] += [
        {"id": "stop", "name": "generic", "kind": "skill", "description": "what can help me"},
        {"id": "redacted", "name": "hidden", "kind": "skill", "description": secret},
    ]
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "What can help me send email?")["actions"] == [{"kind": "highlight", "item_ids": ["mail", "draft"]}]
    assert ask(chat, secret)["actions"] == []


def test_followup_this_without_explain_keyword_shows_item_details(chat):
    assert ask(chat, "What is this?", selected_ids=["mail"])["answer"].startswith("Item details:\n- mail-helper")


@pytest.mark.parametrize("size", [5, 6])
def test_search_and_usage_five_result_boundary(chat, size):
    chat[2]["items"] = [{"id": str(n), "name": f"entry {n}", "kind": "skill", "description": "testing"} for n in range(size)]
    chat[2]["costs"] = {}
    chat[2]["usage"] = {str(n): {"count": 0} for n in range(size)}
    chat[2]["overlaps"] = []
    chat[1].write_text(json.dumps(chat[2]))
    search = ask(chat, "testing")
    assert search["answer"].startswith("Matching Items:\n- entry 0 (skill): testing")
    assert ("More matches omitted" in search["answer"]) is (size == 6)
    for question in ("testing", "usage", "never used"):
        assert ask(chat, question)["actions"][0]["item_ids"] == ["0", "1", "2", "3", "4"]


def test_metadata_display_boundary_and_long_item_ids_remain_known(chat):
    long_id = "skill:" + "long-name-" * 30
    chat[2]["items"][0].update(id=long_id, name="n" * 96, kind="k" * 40, description="d" * 160)
    chat[2]["overlaps"][0].update(a_id=long_id, reason="r" * 240)
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "Explain this", selected_ids=[long_id])
    assert "…" not in result["answer"]
    assert "n" * 96 + " (" + "k" * 40 + "): " + "d" * 160 in result["answer"]
    overlaps = ask(chat, "duplicates")
    assert "r" * 240 in overlaps["answer"] and "…" not in overlaps["answer"]
    assert long_id in overlaps["actions"][0]["item_ids"]


def test_multiple_overlap_rows_and_canonical_cache_metadata(chat):
    chat[2]["overlaps"].append({"a_id": "mail", "b_id": "unknown", "verdict": "wrapper", "reason": "Known wrapper"})
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "overlaps")
    assert result["answer"].count("\n- ") == 2
    assert "Known wrapper\n- Remove one" in result["answer"]
    chat[1].write_text(json.dumps(chat[2], sort_keys=True))
    assert ask(chat, "overlaps")["cached"] is True


def test_email_topic_is_separated_from_query_framing(chat):
    chat[2]["items"] = [
        {"id": "mail", "name": "mail-helper", "kind": "skill", "description": "Searches email"},
        {"id": "fs", "name": "fs-helper", "kind": "skill", "description": "Touches local filesystem"},
        {"id": "screen", "name": "screen-helper", "kind": "skill", "description": "Touches screen gestures"},
    ]
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "Show me everything that touches email")["actions"] == [{"kind": "highlight", "item_ids": ["mail"]}]
    assert ask(chat, "touches screen")["actions"][0]["item_ids"] == ["screen", "fs"]


def test_full_redacted_metadata_is_searchable_even_when_display_is_short(chat):
    chat[2]["items"][0]["description"] = "long description " * 100 + " raretopic"
    chat[1].write_text(json.dumps(chat[2]))
    result = ask(chat, "raretopic")
    assert result["actions"] == [{"kind": "highlight", "item_ids": ["mail"]}]
    assert len(result["answer"]) < 240


def test_new_explicit_search_ignores_stale_selection_but_contextual_explanation_keeps_it(chat):
    assert ask(chat, "Search email", selected_ids=["unknown"])["actions"] == [{"kind": "highlight", "item_ids": ["draft", "mail"]}]
    assert ask(chat, "Explain this", selected_ids=["unknown"])["actions"] == [{"kind": "highlight", "item_ids": ["unknown"]}]
    assert ask(chat, "Explain draft", selected_ids=["mail"])["actions"] == [{"kind": "highlight", "item_ids": ["mail", "draft"]}]


def test_overlap_scope_is_applied_before_top_five_ranking(chat):
    chat[2]["items"] += [{"id": f"pair-{n}", "name": f"partner-{n}", "kind": "skill", "description": "demo"} for n in range(6)]
    chat[2]["overlaps"] = [{"a_id": "mail", "b_id": f"pair-{n}", "verdict": "wrapper", "reason": f"Pair {n}"} for n in range(6)]
    chat[1].write_text(json.dumps(chat[2]))
    assert ask(chat, "overlaps")["answer"].count("\n- ") == 5
    result = ask(chat, "Overlaps of partner-5")
    assert result["actions"] == [{"kind": "highlight", "item_ids": ["mail", "pair-5"]}]
    assert result["answer"].count("\n- ") == 1


def test_scoped_empty_answers_do_not_deny_facts_elsewhere_in_scan(chat):
    pairs = ask(chat, "Duplicates of unknown")
    assert pairs["answer"] == "No known duplicate/wrapper Overlaps for the requested Items."
    assert pairs["actions"] == []
    unused = ask(chat, "Never used mail-helper")
    assert unused["answer"].startswith("None of the requested Items are recorded as never seen.\nCovers 3 transcript files")
    assert unused["actions"] == []
    assert "draft" in ask(chat, "Never used")["answer"]
    assert "Both draft email" in ask(chat, "duplicates")["answer"]


@pytest.mark.parametrize("size,status", [(16384, 200), (16385, 413)])
def test_chat_rejects_oversized_body_before_json_parsing(chat, size, status):
    body = '{"question":"email"}'.ljust(size)
    response = chat[0].post("/api/chat", content=body, headers={"content-type": "application/json"})
    assert response.status_code == status
    if status == 413:
        assert response.json() == {"detail": "Chat request exceeds 16384 bytes"}
    malformed = chat[0].post("/api/chat", content="invalid", headers={"content-type": "application/json", "content-length": "16385"})
    assert malformed.status_code == 413


def test_focus_selected_item_routes_to_focus_operation(chat):
    result = ask(chat, "Focus this", selected_ids=["unknown"])
    assert result["actions"] == [{"kind": "focus", "item_ids": ["unknown"]}]
    assert "Calendar events" in result["answer"]
