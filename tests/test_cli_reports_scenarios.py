"""Builders and renderers on demo-derived scans that exercise what the plain demo does not: session history, clashes, name matching."""

import json
from pathlib import Path

import pytest

from constellation.cli import main

DEMO = Path(__file__).parent.parent / "docs" / "design" / "demo.json"
GOLDEN = Path(__file__).parent / "golden" / "cli"
COUNTS = {  # every other Item is used 5 times
    "skill:lumen:audit-contrast": 6,
    "skill:lumen:focus-rings": 2,
    "skill:quill:changelog-draft": 1,
    "skill:quill:release-notes": 4,
    "skill:harbour:smoke-check": 3,
    "skill:sentinel:suggest-tests": 3,
    "skill:redgreen:refactor-safely": 0,
    "skill:redgreen:make-it-pass": 0,
    "skill:lumen:tune-spacing": 0,
    "skill:lumen:pick-palette": 0,
    "skill:quill:summarise-notes": 0,
    "skill:sieve:chart-draft": 0,
}


def with_history(data):
    data["usage_window"] = {"files": 3, "first": "2026-01-01", "last": "2026-03-01"}
    data["usage"] = {i["id"]: {"count": COUNTS.get(i["id"], 5), "last_used": "2026-03-01"} for i in data["items"]}
    return data


def with_clashes(data):
    hook = next(i for i in data["items"] if i["kind"] == "hook")
    data["items"].append(dict(hook, id=hook["id"] + "-twin"))
    server = next(i for i in data["items"] if i["kind"] == "mcp_server")
    data["items"].append(dict(server, id=server["id"] + "-other"))
    skills = [i for i in data["items"] if i["kind"] == "skill"][:2]
    for s in skills:
        s["description"] += ' Use when the user says "ship it now".'
    return data


def review(data):
    return next(i for i in data["items"] if i["name"] == "review-diff")


def scan_path(tmp_path, change):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(change(json.loads(DEMO.read_text()))))
    return path


def out_of(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


CASES = [
    ("history", with_history, ["unused"]),
    ("history", with_history, ["twins"]),
    ("history", with_history, ["triggers"]),
    ("history", with_history, ["doctor"]),
    ("history", with_history, ["cost"]),
    ("history", with_history, ["why", "review-diff"]),
    ("clashes", with_clashes, ["clashes"]),
    ("clashes", with_clashes, ["doctor"]),
]


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(("scenario", "change", "argv"), CASES, ids=[f"{s}-{a[0]}" for s, _, a in CASES])
def test_scenario_output_matches_golden(tmp_path, capsys, scenario, change, argv, as_json):
    path = scan_path(tmp_path, change)

    code, out, _ = out_of(capsys, *argv, str(path), *(["--json"] if as_json else []))

    assert code == 0
    assert out == (GOLDEN / f"{scenario}-{argv[0]}{'.json' if as_json else '.txt'}").read_text()


def test_why_finds_by_id_or_name_and_by_case_when_nothing_matches_exactly(capsys):
    by_id = out_of(capsys, "why", "skill:sentinel:review-diff", str(DEMO))
    by_case = out_of(capsys, "why", "Review-Diff", str(DEMO))
    by_name = out_of(capsys, "why", "review-diff", str(DEMO))

    assert by_id == by_case == by_name and by_name[0] == 0


def test_why_prefers_an_exact_match_over_a_case_variant(tmp_path, capsys):
    def change(data):
        data["items"].append(dict(review(data), id="skill:x:Review-Diff", name="Review-Diff"))
        return data

    _, out, _ = out_of(capsys, "why", "Review-Diff", str(scan_path(tmp_path, change)))

    assert out.startswith("Review-Diff (skill)\n")


def test_why_case_variants_that_collide_ask_for_the_id(tmp_path, capsys):
    def change(data):
        data["items"].append(dict(review(data), id="skill:x:REVIEW-DIFF", name="REVIEW-DIFF"))
        return data

    path = str(scan_path(tmp_path, change))
    code, out, err = out_of(capsys, "why", "Review-Diff", path)

    assert (code, out) == (2, "")
    assert err == "'Review-Diff' matches several Items: skill:sentinel:review-diff, skill:x:REVIEW-DIFF. Use the id.\n"


def test_an_unknown_item_with_nothing_close_gives_no_suggestion(capsys):
    code, _, err = out_of(capsys, "why", "zzzzzzzz", str(DEMO))

    assert (code, err) == (2, "No Item named 'zzzzzzzz'.\n")


def test_close_matches_are_capped_at_three_and_each_name_once(tmp_path, capsys):
    def change(data):
        for n in ("review-diffs", "review-diffz", "review-diffy"):
            data["items"].append(dict(review(data), id="skill:x:" + n, name=n))
        data["items"].append(dict(review(data), id="skill:y:review-diffs", name="review-diffs"))
        return data

    _, _, err = out_of(capsys, "why", "review-diffq", str(scan_path(tmp_path, change)))

    assert err == "No Item named 'review-diffq'. Did you mean: review-diff, review-diffz, review-diffy?\n"


def test_the_query_is_redacted_in_errors(capsys):
    secret = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])

    _, _, err = out_of(capsys, "why", secret, str(DEMO))

    assert secret not in err and err.startswith("No Item named '")


def test_ask_echoes_the_question_and_answers_locally(capsys):
    _, out, _ = out_of(capsys, "ask", "what costs the most?", str(DEMO), "--json")

    parsed = json.loads(out)
    assert list(parsed) == ["question", "answer"] and parsed["question"] == "what costs the most?"


def test_ask_without_a_question_still_answers(capsys):
    code, out, _ = out_of(capsys, "ask", "", str(DEMO))

    assert code == 0 and out.endswith("\n") and out != "\n"


def test_ask_closes_the_index_even_when_answering_fails(monkeypatch):
    from constellation import cli_reports as cr

    closed = []

    class Index:
        def __init__(self, items):
            pass

        def close(self):
            closed.append(1)

    class Chat:
        def answer(self, data, question, history, index_for, found):
            index_for([])
            raise RuntimeError("boom")

    monkeypatch.setattr(cr.retrieve, "Index", Index)
    monkeypatch.setattr(cr, "LocalChat", Chat)

    with pytest.raises(RuntimeError):
        cr._ask(cr.load(DEMO), "q")
    assert closed == [1]


def test_clean_reports_an_unwritable_target(tmp_path, capsys):
    out_file = tmp_path / "missing-dir" / "cleanup.md"

    code, out, err = out_of(capsys, "clean", str(DEMO), "--out", str(out_file))

    assert (code, out, err) == (2, "", f"Could not write {out_file}.\n")
