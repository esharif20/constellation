import argparse
import importlib.util
import json
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from . import scan
from .classify import FAILED_PREFIX
from .claude_code import read_secrets
from .env import load_env
from .models import LLM, Constellation, Embedder, TokenCounter
from .overlaps import estimate_cost
from .redact import redact

Serve = Callable[[Any, int, bool], None]  # app, port, open the browser


def main(
    argv: Sequence[str] | None = None,
    llm: LLM | None = None,
    embedder: Embedder | None = None,
    counter: TokenCounter | None = None,
    verifier: LLM | None = None,
    serve: Serve | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="constellation")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_command = commands.add_parser("scan", help="read a Claude Code config directory and write a constellation JSON file")
    scan_command.add_argument("config_dir", type=Path)
    scan_command.add_argument("--out", type=Path, default=Path("constellation.json"))
    scan_command.add_argument("--dry-run", action="store_true", help="print what would be sent to the providers; send nothing")
    scan_command.add_argument("--no-verify", action="store_true", help="skip the stronger model that labels candidate Overlaps")
    open_command = commands.add_parser("open", help="serve a constellation JSON file as a graph in the browser")
    open_command.add_argument("file", type=Path, nargs="?", default=Path("constellation.json"))
    open_command.add_argument("--port", type=int, default=8765)
    open_command.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "open":
        return _open(args, serve)  # serving never needs the API key, so it skips load_env
    load_env()  # a .env file in the working directory may hold ANTHROPIC_API_KEY

    if not args.config_dir.is_dir():
        print(f"{args.config_dir} is not a directory.", file=sys.stderr)
        return 2

    sent: list[str] = []
    if args.dry_run:
        # These sit behind scan()'s redaction, so what is printed is exactly what a real run would send.
        local = embedder or _local_embedder()  # the local embedder sends nothing anywhere, so the dry run may really use it
        llm, embedder, counter = _record_prompt(sent), _record_texts(sent, local), _record_counts(sent)
        verifier = _record_verify(sent)
    else:
        if llm is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("ANTHROPIC_API_KEY is not set; export it or use --dry-run.", file=sys.stderr)
                return 2
            try:
                from .anthropic_llm import VERIFIER_MODEL, anthropic_counter, anthropic_llm

                llm, counter = anthropic_llm(), counter or anthropic_counter()
                verifier = verifier or anthropic_llm(model=VERIFIER_MODEL, max_tokens=2048)
            except ImportError:
                print("The anthropic package is not installed; run `uv sync --extra llm`.", file=sys.stderr)
                return 2
        if embedder is None:
            from .embeddings import fastembed_embedder

            embedder = fastembed_embedder()

    with tempfile.TemporaryDirectory() as scratch:  # a dry run must not write the real token-count cache
        cache = Path(scratch) / "counts.json" if args.dry_run else None
        result = scan(
            args.config_dir,
            llm=llm,
            embedder=embedder,
            counter=counter,
            cost_cache=cache,
            verifier=None if args.no_verify else verifier,
            verdict_cache=Path(scratch) / "verdicts.json" if args.dry_run else None,
            on_verify=None if args.dry_run else _announce,
        )
    if args.dry_run:
        print("\n".join(sorted(sent)))  # parallel calls finish in any order; one sorted print is whole, readable and repeatable
        if local is None and not args.no_verify:
            print("No similarity-based verifier prompts can be shown: install the local embedder with `uv sync --extra local`.")
        for warning in result.warnings:
            if warning.startswith("could not cluster items"):
                print(warning, file=sys.stderr)
        return 0
    if result.items and not result.labels:  # every model call failed: report why instead of writing a half-empty file
        first = next((w for w in result.warnings if FAILED_PREFIX in w), "unknown")
        print(f"No Item could be labelled. First problem: {first}", file=sys.stderr)
        return 1
    _write(result, args.out, read_secrets(args.config_dir))
    return 0


def _open(args: argparse.Namespace, serve: Serve | None) -> int:
    if not args.file.is_file():
        print(f"{args.file} not found; run `constellation scan` first.", file=sys.stderr)
        return 2
    try:
        from . import server
    except ImportError:
        print("fastapi and uvicorn are not installed; run `uv sync --extra app`.", file=sys.stderr)
        return 2
    if not (server.STATIC / "index.html").is_file():
        print(server.BUILD_HINT, file=sys.stderr)
        return 2
    (serve or server.serve)(server.create_app(args.file), args.port, not args.no_browser)
    return 0


def _write(result: Constellation, path: Path, secrets: set[str]) -> None:
    result.items = [replace(i, description=redact(i.description, secrets)) for i in result.items]  # the Items hold raw text
    text = json.dumps(asdict(result), indent=2)  # serialise first: a failure must not leave an empty file behind
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)  # open() keeps the mode of a file that already existed
    with os.fdopen(fd, "w") as f:
        f.write(text)


def _local_embedder() -> Embedder | None:
    if importlib.util.find_spec("fastembed") is None:
        return None
    from .embeddings import fastembed_embedder

    return fastembed_embedder()


def _announce(calls: int, input_tokens: int) -> None:
    from .anthropic_llm import VERIFIER_MODEL

    pairs = f"{calls} pair" + ("" if calls == 1 else "s")
    print(
        f"verifying {pairs} with {VERIFIER_MODEL}, about ${estimate_cost(calls, input_tokens):.3f} (cached pairs are free)", file=sys.stderr
    )


def _record_verify(sent: list[str]) -> LLM:
    def call(prompt: str) -> str:
        sent.append(f"--- VERIFY ---\n{prompt}")
        return '{"verdict": "distinct", "reason": "dry-run"}'

    return call


def _record_counts(sent: list[str]) -> TokenCounter:
    def count(texts: list[str]) -> list[int]:
        sent.extend(f"--- COUNT ---\n{text}" for text in texts)
        return [0] * len(texts)

    return count


def _record_prompt(sent: list[str]) -> LLM:
    def call(prompt: str) -> str:
        sent.append(f"--- PROMPT ---\n{prompt}")
        return "dry-run"

    return call


def _record_texts(sent: list[str], inner: Embedder | None = None) -> Embedder:
    def call(texts: list[str]) -> list[list[float]]:
        sent.extend(f"--- EMBED TEXT ---\n{text}" for text in texts)
        return inner(texts) if inner else [[0.0] for _ in texts]

    return call
