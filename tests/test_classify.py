import json
from pathlib import Path

from fakes import FakeEmbedder, FakeLLM

from constellation import scan

FIXTURE = Path(__file__).parent / "fixtures" / "claude_config"


def test_every_item_gets_a_free_text_label_from_the_llm():
    llm = FakeLLM({"alpha": "writing helpers", "beta": "test tooling"})

    constellation = scan(FIXTURE, llm=llm)

    assert constellation.labels["claude-code:skill:alpha"] == "writing helpers"
    assert constellation.labels["claude-code:skill:beta"] == "test tooling"
    assert {i.id for i in constellation.items} == set(constellation.labels)


def test_only_names_and_descriptions_are_sent_to_the_llm_and_the_embedder(tmp_path):
    def write(rel, content):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content))

    write("skills/tidy/SKILL.md", "---\nname: tidy\ndescription: Tidies a repo\n---\nBODY_MARKER full instructions\n")
    write("agents/reviewer.md", "---\nname: reviewer\ndescription: Reviews diffs\n---\nAGENT_BODY_MARKER prompt\n")
    write(".mcp.json", {"mcpServers": {"gh": {"command": "gh-mcp", "env": {"ENV_NAME_MARKER": "x"}, "notes": "EXTRA_FIELD_MARKER"}}})
    write("settings.json", {"permissions": {"allow": ["PERMISSION_MARKER"]}, "model": "MODEL_MARKER"})
    write("plugins/cache/m/p/1/.claude-plugin/plugin.json", {"name": "p", "description": "A plugin", "author": "AUTHOR_MARKER"})
    llm, embedder = FakeLLM({}), FakeEmbedder({})

    scan(tmp_path, llm=llm, embedder=embedder)

    sent = "\n".join(llm.prompts + embedder.texts)
    assert (
        "Name: tidy" in sent and "Description: Reviews diffs" in sent and "Name: gh" in sent
    )  # items were sent, so the check is not vacuous
    for marker in [
        "BODY_MARKER",
        "AGENT_BODY_MARKER",
        "ENV_NAME_MARKER",
        "EXTRA_FIELD_MARKER",
        "PERMISSION_MARKER",
        "MODEL_MARKER",
        "AUTHOR_MARKER",
    ]:
        assert marker not in sent
    assert str(tmp_path) not in sent  # file paths are never sent
