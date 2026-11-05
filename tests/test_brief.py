import copy
import json
import os
from pathlib import Path

import pytest

from constellation.brief import append_line, brief, checklist_ids, frees
from constellation.suggestions import Suggestion, suggest


@pytest.fixture
def data():
    return json.loads((Path(__file__).parent / "fixtures" / "scan.json").read_text())


def test_cost_ranking_keeps_zero_and_counts_unknown_items(data):
    data["items"] = [
        {"id": id_, "name": name, "kind": "skill"}
        for id_, name in (("z", "Zulu"), ("b", "Alpha"), ("a", "Alpha"), ("zero", "Zero"), ("unknown", "Unknown"))
    ]
    data["costs"] = {id_: {"always_on": tokens} for id_, tokens in (("z", 20), ("b", 20), ("a", 20), ("zero", 0))}
    data["overlaps"] = []
    cost = brief(data)["cost"]
    assert [r["item_ids"] for r in cost["rows"]] == [["a"], ["b"], ["z"], ["zero"]]
    assert cost["measured"] is True
    assert cost["unknown"] == 1
    assert cost["unknown_rows"] == 0
    assert cost["frees"] == 60
    assert cost["rows"][0] == {
        "id": "8df16036cb82",
        "kind": "review_cost",
        "item_ids": ["a"],
        "removes": "a",
        "reason": "Alpha (skill): 20 always-on tokens every session. Is it worth it?",
        "tokens_saved": 20,
        "project": None,
        "confidence": None,
    }
    assert len(brief(data, top=2)["cost"]["rows"]) == 2


def test_pairs_reuse_suggestion_order_and_identify_the_removed_item(data):
    assert len(brief(data)["cost"]["rows"]) == 5
    pairs = brief(data)["pairs"]
    expected = suggest(data)
    assert [r["id"] for r in pairs["rows"]] == [s.id for s in expected]
    assert [r["removes"] for r in pairs["rows"]] == ["skill:ship", "agent:reviewer"]
    assert [r["kind"] for r in pairs["rows"]] == ["remove_duplicate", "use_underlying"]
    assert [r["item_ids"] for r in pairs["rows"]] == [list(s.item_ids) for s in expected]
    assert [r["reason"] for r in pairs["rows"]] == [s.reason for s in expected]
    assert [r["tokens_saved"] for r in pairs["rows"]] == [415, 60]
    assert pairs["frees"] == 475
    assert pairs["unknown"] == pairs["unknown_rows"] == 0
    assert len(brief(data, top=1)["pairs"]["rows"]) == 1
    both = brief(data, top=20)
    assert frees(both["cost"]["rows"] + both["pairs"]["rows"], {i: c["always_on"] for i, c in data["costs"].items() if c}) == sum(
        c["always_on"] for c in data["costs"].values() if c and c["always_on"] is not None
    )


def test_unknown_costs_and_zero_savings_are_distinct(data):
    data["costs"] = {"agent:reviewer": {"always_on": 0}}
    got = brief(data)
    assert got["pairs"]["frees"] == 0
    assert got["pairs"]["unknown"] == got["pairs"]["unknown_rows"] == 1
    assert [r["removes"] for r in got["pairs"]["rows"]] == ["agent:reviewer", None]
    assert got["cost"]["frees"] == 0
    del data["costs"]
    got = brief(data)
    assert got["cost"] == {"rows": [], "unknown": len(data["items"]), "measured": False, "unknown_rows": 0, "frees": None}
    assert got["pairs"]["frees"] is None
    assert got["pairs"]["unknown_rows"] == 2
    assert [r["removes"] for r in got["pairs"]["rows"]] == ["agent:reviewer", None]
    assert frees([], {}) is None


def test_duplicate_cost_ties_choose_the_lower_id(data):
    data["costs"]["skill:deploy"]["always_on"] = 415
    assert brief(data)["pairs"]["rows"][0]["removes"] == "skill:deploy"


def test_ids_and_order_are_stable_and_cost_rows_do_not_enter_review(data):
    reordered = copy.deepcopy(data)
    reordered["items"].reverse()
    reordered["overlaps"].reverse()
    assert brief(data) == brief(reordered)
    assert all(s.kind != "review_cost" for s in suggest(data))


def test_reasons_redact_names_and_verdict_text(data):
    secret = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])
    data["items"][0]["name"] = secret
    for item in data["items"]:
        item["description"] = secret
    for overlap in data["overlaps"]:
        overlap["reason"] = secret
    assert secret not in json.dumps(brief(data))


def test_unused_suggestions_do_not_displace_pairs(data):
    data["usage"] = {i["id"]: {"count": 0, "last_seen": None} for i in data["items"]}
    data["usage_window"] = {"files": 5, "first": "2026-01-01", "last": "2026-02-01", "skipped": 0}
    assert any(s.kind == "remove_unused" for s in suggest(data))
    assert [r["kind"] for r in brief(data, top=1)["pairs"]["rows"]] == ["remove_duplicate"]


def test_append_checklist_uses_review_format_and_is_idempotent(tmp_path):
    path = tmp_path / "nested" / "deeper" / "checklist.md"
    s = Suggestion("012345abcdef", "review_cost", ("a",), "Review Alpha.", 1200)
    assert append_line(path, s) is True
    expected = (
        "Constellation never edits your config. Every change below is yours to make by hand.\n\n"
        "# Constellation cleanup checklist\n\n"
        "- [ ] Review Alpha. Saves about 1,200 always-on tokens. (id 012345abcdef)\n"
    )
    assert path.read_text() == expected
    assert path.stat().st_mode & 0o777 == 0o600
    before = path.stat().st_mtime_ns
    assert append_line(path, s) is False
    assert path.read_text() == expected
    assert path.stat().st_mtime_ns == before
    path.chmod(0o644)
    assert append_line(path, Suggestion("abcdef012345", "review_cost", ("b",), "Review Beta.", None)) is True
    assert path.read_text() == expected + "- [ ] Review Beta. Saving not measured. (id abcdef012345)\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert checklist_ids(path.read_text()) == ["012345abcdef", "abcdef012345"]


def test_checklist_ids_accept_only_markers_and_preserve_order():
    text = (
        "(id 111111111111)\n"
        "- [ ] Review (id 222222222222) continued text\n"
        "- [ ] Review (id ABCDEF012345)\n"
        "- [ ] Review (id abcdef0123456)\n"
        "- [ ] Review (id 000000000000)\n"
        "- [x] Review (id abcdef012345)\r\n"
        "- [X] Review (id fedcba012345)\n"
        "- [ ] Review (id 000000000000)"
    )
    assert checklist_ids(text) == ["000000000000", "abcdef012345", "fedcba012345"]


def test_appending_preserves_the_last_entry_without_a_final_newline(tmp_path):
    path = tmp_path / "checklist.md"
    path.write_text("- [x] Existing. (id 000000000000)")
    s = Suggestion("012345abcdef", "review_cost", ("a",), "Review Alpha.", 100)
    assert append_line(path, s) is True
    assert checklist_ids(path.read_text()) == ["000000000000", "012345abcdef"]
    assert path.read_text().startswith("- [x] Existing. (id 000000000000)\n- [ ] ")


def test_appended_reasons_keep_their_text_on_one_line(tmp_path):
    path = tmp_path / "checklist.md"
    s = Suggestion("012345abcdef", "review_cost", ("a",), "Review Alpha.\r\nThen check Beta.\u2028Keep Gamma.", 100)
    assert append_line(path, s) is True
    assert path.read_text().endswith(
        "- [ ] Review Alpha. Then check Beta. Keep Gamma. Saves about 100 always-on tokens. (id 012345abcdef)\n"
    )


def test_unknown_saving_is_excluded_even_if_an_item_cost_is_available():
    assert frees([{"removes": "a", "tokens_saved": None}], {"a": 10}) is None


def test_append_never_rewrites_existing_text(tmp_path):
    path = tmp_path / "checklist.md"
    path.write_text("# mine\n- [ ] hand edit (id 0123456789ab)\n")
    inode = path.stat().st_ino
    assert append_line(path, Suggestion("abcdef012345", "review_cost", ("b",), "Review Beta.", None)) is True
    assert path.read_text() == "# mine\n- [ ] hand edit (id 0123456789ab)\n- [ ] Review Beta. Saving not measured. (id abcdef012345)\n"
    assert path.stat().st_ino == inode


def test_append_writes_one_whole_line_with_o_append(tmp_path, monkeypatch):
    path = tmp_path / "checklist.md"
    path.write_text("keep\n")
    calls = []
    real_open = os.open
    monkeypatch.setattr(os, "open", lambda p, flags, *a: calls.append(flags) or real_open(p, flags, *a))
    append_line(path, Suggestion("abcdef012345", "review_cost", ("b",), "Review Beta.", None))
    assert calls[0] & os.O_APPEND and not calls[0] & os.O_TRUNC


def test_append_adds_a_missing_final_newline_inside_the_same_write(tmp_path):
    path = tmp_path / "checklist.md"
    path.write_text("- [ ] x (id 0123456789ab)")
    append_line(path, Suggestion("abcdef012345", "review_cost", ("b",), "Review Beta.", None))
    assert path.read_text().splitlines()[1].startswith("- [ ] Review Beta.")
