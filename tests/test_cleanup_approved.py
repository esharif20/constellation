import json
import os
import stat
from pathlib import Path

import pytest

from constellation.report import render_cleanup, write_private
from constellation.suggestions import suggest

FIXTURE = Path(__file__).parent / "fixtures" / "scan.json"


@pytest.fixture
def data():
    return json.loads(FIXTURE.read_text())


def test_approved_suggestions_replace_the_duplicates_section(data):
    s = suggest(data)
    text = render_cleanup(data, top=1, approved=[s[0]])
    assert "## Duplicates" not in text
    assert "## Approved Suggestions\n\n" + f"- [ ] {s[0].reason} Saves about 415 always-on tokens. (id {s[0].id})\n" in text
    assert text.startswith("Constellation never edits your config.")
    assert "## Highest always-on cost" in text
    assert s[1].reason not in text


def test_unknown_saving_and_nothing_approved(data):
    s = suggest(data)[0]
    unknown = type(s)(s.id, s.kind, s.item_ids, "r.", None)
    assert f"- [ ] r. Saving not measured. (id {s.id})" in render_cleanup(data, top=1, approved=[unknown])
    assert "## Approved Suggestions\n\nNone approved.\n" in render_cleanup(data, top=1, approved=[])


def test_without_approved_the_output_is_unchanged(data):
    assert render_cleanup(data, top=3, approved=None) == (FIXTURE.parent / "cleanup.md").read_text()
    assert render_cleanup(data, top=3) == (FIXTURE.parent / "cleanup.md").read_text()


def test_write_private_is_0600_even_over_an_open_file(tmp_path):
    path = tmp_path / "out.md"
    path.write_text("old")
    os.chmod(path, 0o644)
    write_private(path, "new")
    assert path.read_text() == "new"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
