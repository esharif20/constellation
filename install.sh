#!/bin/sh
# Installs Constellation (constellation-cli) with uv or pipx. No sudo, no network beyond the package manager,
# never edits your shell files (it prints the line to add instead). Read me before piping me into sh.
#   sh install.sh [--dry-run] [--method uv|pipx] [--git]
#   --git installs from GitHub, for use until the package is on PyPI.
set -eu

PKG="constellation-cli"
GIT="git+https://github.com/esharif20/constellation"

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Run a command, or only show it under --dry-run.
run() {
  if [ "$DRY" = 1 ]; then say "would run: $*"; else say "running: $*"; "$@"; fi
}

main() {
  DRY=0 METHOD="" SRC="$PKG"
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) DRY=1 ;;
      --git) SRC="$GIT" ;;
      --method) [ $# -ge 2 ] || die "--method needs uv or pipx"; METHOD="$2"; shift ;;
      -h|--help) say "usage: sh install.sh [--dry-run] [--method uv|pipx] [--git]"; return 0 ;;
      *) die "unknown option: $1" ;;
    esac
    shift
  done

  [ "$(id -u)" -ne 0 ] || die "run without sudo; nothing here needs root."

  if [ -z "$METHOD" ]; then
    if have uv; then METHOD=uv; elif have pipx; then METHOD=pipx; fi
  fi

  case "$METHOD" in
    uv)
      have uv || die "uv not found. Install uv (https://docs.astral.sh/uv/ or 'brew install uv'), then rerun."
      say "uv found; it fetches Python 3.13 itself if needed."
      run uv tool install --force "$SRC" ;;
    pipx)
      have pipx || die "pipx not found. Install pipx (https://pipx.pypa.io/ or 'brew install pipx'), then rerun."
      have python3.13 || die "pipx needs python3.13 on PATH (Constellation requires Python 3.13). Use uv instead, or install it."
      run pipx install --force "$SRC" ;;
    "") die "neither uv nor pipx found. Install uv (https://docs.astral.sh/uv/ or 'brew install uv'), then rerun." ;;
    *) die "unknown method '$METHOD' (use uv or pipx)" ;;
  esac

  if [ "$DRY" = 1 ]; then say "dry run: nothing was changed."; return 0; fi

  say "Installed $SRC with $METHOD."
  if have constellation; then
    say "Try: constellation open demo"
  else
    say "'constellation' is not on your PATH yet. I have not touched any shell file. To fix it, add this line"
    say "to your shell startup file (for example ~/.zshrc) yourself, or run 'uv tool update-shell':"
    say '  export PATH="$HOME/.local/bin:$PATH"'
  fi
}

main "$@"
