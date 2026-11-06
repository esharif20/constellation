import argparse

from constellation import cli_help, completion


def build():
    p = argparse.ArgumentParser(prog="constellation")
    sp = p.add_subparsers(dest="c")
    a = sp.add_parser("scan")
    a.add_argument("--out")
    a.add_argument("-x")
    a.description = "Read it: it's fine. Second sentence."
    b = sp.add_parser("completion")
    b.add_argument("shell", choices=["bash", "zsh"])
    b.description = "Print."
    sp.add_parser("plain")
    return p, sp.choices


def test_table_takes_the_first_sentence_long_options_and_choices():
    p, _ = build()
    assert completion.table(p) == {
        "scan": ("Read it: it's fine", ["--help", "--out"]),
        "completion": ("Print", ["--help", "bash", "zsh"]),
        "plain": ("", ["--help"]),
    }


def test_bash_script_exact():
    p, _ = build()
    assert completion.render(p, "bash") == (
        "# bash completion for constellation\n_constellation() {\n"
        '  local cur="${COMP_WORDS[COMP_CWORD]}"\n'
        '  if [ "$COMP_CWORD" -eq 1 ]; then\n'
        '    COMPREPLY=($(compgen -W "scan completion plain --help --version" -- "$cur"))\n'
        "    return\n  fi\n"
        '  case "${COMP_WORDS[1]}" in\n'
        '    scan) COMPREPLY=($(compgen -W "--help --out" -- "$cur")) ;;\n'
        '    completion) COMPREPLY=($(compgen -W "--help bash zsh" -- "$cur")) ;;\n'
        '    plain) COMPREPLY=($(compgen -W "--help" -- "$cur")) ;;\n'
        "  esac\n}\ncomplete -o default -F _constellation constellation\n"
    )


def test_zsh_script_exact():
    p, _ = build()
    assert completion.render(p, "zsh") == (
        "#compdef constellation\n_constellation() {\n  local -a verbs\n  verbs=(\n"
        "    'scan:Read it\\: it'\\''s fine'\n"
        "    'completion:Print'\n"
        "    'plain:'\n"
        "  )\n  if (( CURRENT == 2 )); then\n    _describe 'command' verbs\n    return\n  fi\n"
        '  case "$words[2]" in\n'
        "    scan) compadd -- --help --out; _files ;;\n"
        "    completion) compadd -- --help bash zsh; _files ;;\n"
        "    plain) compadd -- --help; _files ;;\n"
        '  esac\n}\n_constellation "$@"\n'
    )


def test_zsh_bare_verb_branch_when_no_words():
    assert completion._zsh({"x": ("d", [])}).count("    x) _files ;;") == 1


def test_fish_script_exact():
    p, _ = build()
    s = "complete -c constellation"
    assert completion.render(p, "fish") == (
        f"# fish completion for constellation\n{s} -f\n"
        f"{s} -n __fish_use_subcommand -a scan -d 'Read it: it\\'s fine'\n"
        f"{s} -n '__fish_seen_subcommand_from scan' -l help\n"
        f"{s} -n '__fish_seen_subcommand_from scan' -l out\n"
        f"{s} -n __fish_use_subcommand -a completion -d 'Print'\n"
        f"{s} -n '__fish_seen_subcommand_from completion' -l help\n"
        f"{s} -n '__fish_seen_subcommand_from completion' -a bash\n"
        f"{s} -n '__fish_seen_subcommand_from completion' -a zsh\n"
        f"{s} -n __fish_use_subcommand -a plain -d ''\n"
        f"{s} -n '__fish_seen_subcommand_from plain' -l help\n"
    )


def test_decorate_exact():
    p, ch = build()
    cli_help.decorate(p, ch)
    assert p.epilog == (
        "Map:\n  scan        Read a Claude Code config directory and write a constellation JSON file\n\n"
        "Manage:\n  completion  Print a shell completion script (bash, zsh or fish) to stdout\n  plain       \n\n"
        "Exit codes: 0 ok, 1 runtime error, 2 usage error or missing input, 130 interrupted.\n"
        "No telemetry. The network is used only by scan (with a key), ask and update."
    )
    scan, comp, plain = ch["scan"], ch["completion"], ch["plain"]
    assert scan.description == "Read a Claude Code config directory and write a constellation JSON file."
    assert scan.epilog == (
        "examples:\n  constellation scan ~/.claude --dry-run   # show what would be sent and written\n"
        "  constellation scan ~/.claude --offline"
    )
    assert plain.epilog == "examples:\n  constellation plain" and plain.description is None
    assert all(s.formatter_class is argparse.RawDescriptionHelpFormatter for s in ch.values())
    assert scan.get_default("writes") is True and comp.get_default("writes") is None and plain.get_default("writes") is None
    assert [a.option_strings for a in scan._actions].count(["--dry-run"]) == 1
    assert not any("--dry-run" in a.option_strings for a in comp._actions)
    dry = next(a for a in scan._actions if a.option_strings == ["--dry-run"])
    assert dry.help == "show what would be written; write nothing" and dry.const is True


def test_decorate_keeps_an_existing_epilog_and_dry_run():
    p, ch = build()
    ch["plain"].epilog = "mine"
    ch["scan"].add_argument("--dry-run", action="store_true", help="own")
    cli_help.decorate(p, ch)
    assert ch["plain"].epilog == "mine"
    assert [a.help for a in ch["scan"]._actions if a.option_strings == ["--dry-run"]] == ["own"]


def test_help_groups_orders_groups_and_skips_empty_ones():
    p, ch = build()
    cli_help.decorate(p, ch)
    out = cli_help.help_groups({"doctor": ch["scan"], "clean": ch["scan"]})
    assert out.startswith("Look:\n  doctor") and "\n\nAct:\n  clean" in out and "Map:" not in out and "Manage:" not in out


def test_known_verb_table_is_complete():
    assert all(len(v) == 3 and v[0] in ("Look", "Act", "Map", "Manage") and v[1].endswith(".") and v[2] for v in cli_help._VERBS.values())


def _described(text):
    sub = argparse.ArgumentParser()
    sub.description = text
    return sub


def test_first_sentence_cut_is_exact_in_both_places():
    for text, want in [
        ("Fix X.", "Fix X"),
        ("A. B. C", "A"),
        ("Wait...", "Wait"),
        ("Ends in X. Then", "Ends in X"),
        ("No stop", "No stop"),
    ]:
        p = argparse.ArgumentParser(prog="constellation")
        sp = p.add_subparsers()
        sp.add_parser("zz").description = text
        assert completion.table(p)["zz"][0] == want
        assert cli_help.help_groups({"zz": _described(text)}) == f"Manage:\n  {'zz':<12}{want}"
