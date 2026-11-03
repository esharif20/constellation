import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path

from . import scan
from .claude_code import read_secrets
from .models import LLM, Embedder
from .redact import redact


def main(argv: Sequence[str] | None = None, llm: LLM | None = None, embedder: Embedder | None = None) -> int:
    parser = argparse.ArgumentParser(prog="constellation")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("scan", help="read a Claude Code config directory and write a constellation JSON file")
    cmd.add_argument("config_dir", type=Path)
    cmd.add_argument("--out", type=Path, default=Path("constellation.json"))
    cmd.add_argument("--dry-run", action="store_true", help="print what would be sent to the providers; send nothing")
    args = parser.parse_args(argv)

    if args.dry_run:
        # Recording providers sit behind scan()'s redaction, so what is printed is exactly what a real run would send.
        llm = _record("PROMPT", lambda p: "dry-run")
        embedder = _record_texts()
    else:
        if llm is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("ANTHROPIC_API_KEY is not set; export it or use --dry-run.", file=sys.stderr)
                return 2
            from .anthropic_llm import anthropic_llm

            llm = anthropic_llm()
        if embedder is None:
            from .embeddings import fastembed_embedder

            embedder = fastembed_embedder()

    result = scan(args.config_dir, llm=llm, embedder=embedder)
    if args.dry_run:
        return 0

    secrets = read_secrets(args.config_dir)
    result.items = [replace(i, description=redact(i.description, secrets)) for i in result.items]  # the Items hold raw text
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(args.out, 0o600)  # open() keeps the mode of a file that already existed
    with os.fdopen(fd, "w") as f:
        json.dump(asdict(result), f, indent=2)
    return 0


def _record(label: str, reply: LLM) -> LLM:
    def call(prompt: str) -> str:
        print(f"--- {label} ---\n{prompt}")
        return reply(prompt)

    return call


def _record_texts() -> Embedder:
    def call(texts: list[str]) -> list[list[float]]:
        for text in texts:
            print(f"--- EMBED TEXT ---\n{text}")
        return [[0.0] for _ in texts]

    return call
