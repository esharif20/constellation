"""Static shell completion scripts built by walking the argparse parser (no extra dependency, no Python on Tab)."""

import argparse

SHELLS = ("bash", "zsh", "fish")


def table(parser: argparse.ArgumentParser) -> dict[str, tuple[str, list[str]]]:
    """verb -> (description, words that may follow it: option strings and fixed positional choices)."""
    commands: dict[str, argparse.ArgumentParser] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            commands.update(action.choices)
    out = {}
    for name, sub in commands.items():
        words: list[str] = []
        for a in sub._actions:
            words += [o for o in a.option_strings if o.startswith("--")] + [str(c) for c in a.choices or ()]
        out[name] = ((sub.description or "").split(". ")[0].rstrip("."), words)
    return out


def render(parser: argparse.ArgumentParser, shell: str) -> str:
    verbs = table(parser)
    return {"bash": _bash, "zsh": _zsh, "fish": _fish}[shell](verbs)


def _bash(verbs: dict[str, tuple[str, list[str]]]) -> str:
    cases = "\n".join(f'    {n}) COMPREPLY=($(compgen -W "{" ".join(w)}" -- "$cur")) ;;' for n, (_, w) in verbs.items())
    return (
        "# bash completion for constellation\n"
        "_constellation() {\n"
        '  local cur="${COMP_WORDS[COMP_CWORD]}"\n'
        '  if [ "$COMP_CWORD" -eq 1 ]; then\n'
        f'    COMPREPLY=($(compgen -W "{" ".join(verbs)} --help --version" -- "$cur"))\n'
        "    return\n"
        "  fi\n"
        '  case "${COMP_WORDS[1]}" in\n'
        f"{cases}\n"
        "  esac\n"
        "}\n"
        "complete -o default -F _constellation constellation\n"
    )


def _zsh_quote(text: str) -> str:
    return text.replace("'", "'\\''").replace(":", "\\:")


def _zsh(verbs: dict[str, tuple[str, list[str]]]) -> str:
    described = "\n".join(f"    '{n}:{_zsh_quote(d)}'" for n, (d, _) in verbs.items())
    cases = "\n".join(f"    {n}) compadd -- {' '.join(w)}; _files ;;" if w else f"    {n}) _files ;;" for n, (_, w) in verbs.items())
    return (
        "#compdef constellation\n"
        "_constellation() {\n"
        "  local -a verbs\n"
        f"  verbs=(\n{described}\n  )\n"
        "  if (( CURRENT == 2 )); then\n"
        "    _describe 'command' verbs\n"
        "    return\n"
        "  fi\n"
        '  case "$words[2]" in\n'
        f"{cases}\n"
        "  esac\n"
        "}\n"
        '_constellation "$@"\n'
    )


def _fish(verbs: dict[str, tuple[str, list[str]]]) -> str:
    lines = ["# fish completion for constellation", "complete -c constellation -f"]
    for name, (desc, words) in verbs.items():
        lines.append(f"complete -c constellation -n __fish_use_subcommand -a {name} -d '{desc.replace(chr(39), chr(92) + chr(39))}'")
        for w in words:
            flag = f"-l {w[2:]}" if w.startswith("--") else f"-a {w}"
            lines.append(f"complete -c constellation -n '__fish_seen_subcommand_from {name}' {flag}")
    return "\n".join(lines) + "\n"
