import json
from dataclasses import asdict

from fakes import FakeCounter

from constellation import scan
from constellation.models import Weight
from constellation.report import render_report

SECRET = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])


def hook(command, event="SessionStart", matcher=None):
    return event, {**({"matcher": matcher} if matcher else {}), "hooks": [{"type": "command", "command": command}]}


def config(tmp_path, *hooks, env=None):
    groups = {}
    for event, group in hooks:
        groups.setdefault(event, []).append(group)
    (tmp_path / "settings.json").write_text(json.dumps({"hooks": groups, "env": env or {}}))
    return tmp_path


def only(result):
    return next(iter(result.hook_weights.values()))


def test_script_file_inside_the_config_dir_is_sized_in_bytes_and_nothing_runs(tmp_path):
    script = tmp_path / "start.sh"
    script.write_text("touch ran.flag\necho héllo\n")
    result = scan(config(tmp_path, hook(f"bash {script}")))

    assert only(result) == Weight(len(script.read_bytes()), None)
    assert not (tmp_path / "ran.flag").exists()


def test_literal_echo_and_printf_text_is_sized_and_flags_are_not_counted(tmp_path):
    result = scan(config(tmp_path, hook("echo -n 'use tabs'"), hook("printf 'ab cd'", "UserPromptSubmit")))

    assert sorted(w.bytes for w in result.hook_weights.values()) == [5, 8]


def test_everything_else_is_unknown_never_zero(tmp_path):
    outside = tmp_path.parent / "outside.sh"
    outside.write_text("x" * 50)
    commands = [
        "echo $HOME",
        "echo a; echo b",
        "cat <(date)",
        f"bash {tmp_path}/missing.sh",
        f"bash {outside}",
        "bash rel.sh",
        "echo 'open",
        "",
    ]
    result = scan(config(tmp_path, *[hook(c) for c in commands]))

    assert len(result.hook_weights) == len(commands)
    assert set(result.hook_weights.values()) == {Weight(None, None)}


def test_a_symlink_out_of_the_config_dir_is_unknown(tmp_path):
    outside = tmp_path.parent / "secret-outside.sh"
    outside.write_text("x" * 50)
    (tmp_path / "link.sh").symlink_to(outside)

    assert only(scan(config(tmp_path, hook(f"bash {tmp_path}/link.sh")))) == Weight(None, None)


def test_only_prompt_time_hooks_are_listed(tmp_path):
    result = scan(config(tmp_path, hook("echo a", "PostToolUse", "Read"), hook("echo b", "Stop"), hook("echo c", "UserPromptSubmit")))

    assert [w.bytes for w in result.hook_weights.values()] == [1]


def test_a_hook_that_calls_an_mcp_tool_is_unknown(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "mcp_tool", "server": "db", "tool": "boot"}]}]}})
    )

    assert only(scan(tmp_path)) == Weight(None, None)


def test_plugin_root_variable_resolves_inside_that_plugin(tmp_path):
    root = tmp_path / "plugins" / "cache" / "m" / "demo" / "1.0.0"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"name": "demo"}')
    (root / "hooks").mkdir()
    (root / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/boot.sh"}]}]}})
    )
    (root / "boot.sh").write_text("12345678")

    assert only(scan(tmp_path)).bytes == 8


def test_tokens_are_not_counted_without_the_opt_in_and_bytes_still_show(tmp_path):
    counter = FakeCounter()
    result = scan(config(tmp_path, hook("echo one two three")), counter=counter, cost_cache=tmp_path / "c.json")

    assert only(result) == Weight(13, None)
    assert all("one two three" not in t for t in counter.texts)


def test_tokens_are_counted_with_count_bodies_cached_and_the_secret_never_reaches_the_counter(tmp_path):
    (tmp_path / "start.sh").write_text(f"echo one two three {SECRET}")
    cfg = config(tmp_path, hook(f"bash {tmp_path}/start.sh"), env={"TOKEN": SECRET})
    cache = tmp_path / "c.json"
    counter = FakeCounter()

    first = scan(cfg, counter=counter, count_bodies=True, cost_cache=cache)
    asked = len(counter.texts)
    second = scan(cfg, counter=counter, count_bodies=True, cost_cache=cache)

    assert only(first).tokens == only(second).tokens > 0
    assert len(counter.texts) == asked  # unchanged setup: zero new paid calls
    assert SECRET not in "".join(counter.texts)
    assert SECRET not in cache.read_text()


def test_offline_reports_cached_tokens_only(tmp_path):
    cfg = config(tmp_path, hook("echo one two three"))
    cache = tmp_path / "c.json"

    cold = scan(cfg, count_bodies=True, offline=True, cost_cache=cache)
    scan(cfg, counter=FakeCounter(), count_bodies=True, cost_cache=cache)
    warm = scan(cfg, count_bodies=True, offline=True, cost_cache=cache)

    assert only(cold) == Weight(13, None)
    assert only(warm) == Weight(13, 3)


def test_a_failing_counter_leaves_tokens_unknown_with_a_warning(tmp_path):
    result = scan(
        config(tmp_path, hook("echo one")), counter=FakeCounter(fail_with="down"), count_bodies=True, cost_cache=tmp_path / "c.json"
    )

    assert only(result) == Weight(3, None)
    assert any("down" in w for w in result.warnings)


def render(result):
    return render_report(asdict(result), top=5, color=False, width=80, show_all=False)


def test_report_shows_per_hook_sizes_and_a_lower_bound_total(tmp_path):
    (tmp_path / "start.sh").write_text("x" * 1234)
    out = render(scan(config(tmp_path, hook(f"bash {tmp_path}/start.sh", matcher="startup"), hook("echo $HOME", "UserPromptSubmit"))))

    assert "Session-start weight (hooks, nothing run)" in out
    assert "  - SessionStart:startup (hook): 1,234 B\n" in out
    assert "  - UserPromptSubmit (hook): unknown\n" in out
    assert (
        "At least 1,234 bytes across 1 of 2 hooks (lower bound; the rest are unknown). Tokens not counted (use --count-bodies)."
        in " ".join(out.split())
    )


def test_report_shows_tokens_when_counted(tmp_path):
    out = render(
        scan(config(tmp_path, hook("echo one two three")), counter=FakeCounter(), count_bodies=True, cost_cache=tmp_path / "c.json")
    )

    assert "  - SessionStart (hook): 13 B, 3 tokens\n" in out
    assert "At least 13 bytes across 1 of 1 hooks" in out
    assert "At least 3 tokens." in " ".join(out.split())


def test_report_orders_hooks_by_name_and_has_no_section_without_prompt_time_hooks(tmp_path):
    out = render(scan(config(tmp_path, hook("echo b", "UserPromptSubmit"), hook("echo a"))))
    assert out.index("SessionStart (hook)") < out.index("UserPromptSubmit (hook)")
    assert "Session-start weight" not in render(scan(config(tmp_path, hook("echo a", "Stop"))))


def test_echo_flags_of_every_case_are_dropped_and_other_dashed_words_kept(tmp_path):
    result = scan(config(tmp_path, hook("echo -neE hi"), hook("echo -E -e hi", "UserPromptSubmit"), hook("echo -x hi", "UserPromptSubmit")))

    assert [w.bytes for w in result.hook_weights.values()] == [2, 2, 5]


def test_a_script_that_is_not_utf8_is_still_sized(tmp_path):
    (tmp_path / "bin.sh").write_bytes(b"\xff")

    assert only(scan(config(tmp_path, hook(f"bash {tmp_path}/bin.sh")))).bytes == 3  # shortcut: U+FFFD stands in for the bad byte


def test_report_orders_by_displayed_name_falls_back_to_the_id_and_wraps_with_a_hanging_indent():
    data = {
        "items": [{"id": "zz", "name": "aaaa bbbb cccc dddd", "kind": "hook", "description": ""}],
        "hook_weights": {"h1": {"bytes": 1, "tokens": None}, "zz": {"bytes": 2, "tokens": None}},
    }
    out = render_report(data, top=5, color=False, width=24, show_all=False)

    assert "\n  - aaaa bbbb cccc dddd\n      (hook): 2 B\n  - h1: 1 B\n" in out
    assert "\n\n  At least 3 bytes" in out


def test_report_heading_is_bold_when_colour_is_on_and_absent_without_hooks():
    data = {"items": [], "hook_weights": {"x": {"bytes": 1, "tokens": None}}}

    assert "\033[1mSession-start weight (hooks, nothing run)\033[0m" in render_report(data, top=5, color=True, width=60, show_all=False)
    assert "\nSession-start weight (hooks, nothing run) -" in render_report(data, top=5, color=False, width=60, show_all=False)
    assert "Session-start" not in render_report({"items": []}, top=5, color=False, width=60, show_all=False)
