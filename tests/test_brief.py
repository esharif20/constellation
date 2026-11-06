import os

from constellation.brief import append_line, checklist_ids
from constellation.suggestions import Suggestion


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
