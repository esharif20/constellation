import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from langgraph.types import Command

from . import habits, history, scan, scan_graph
from . import origins as origin_sources
from .classify import FAILED_PREFIX
from .claude_code import read_secrets
from .diff import diff_scans, render_diff
from .env import load_env
from .expansion import Query, expand
from .models import LLM, Constellation, Embedder, TokenCounter
from .overlaps import estimate_cost
from .preview import delta, preview, render_delta, render_preview
from .public_export import LIMITS, NOTICE, write_snapshot
from .redact import redact
from .report import render_cleanup, render_report, write_private
from .review import build_review_graph, open_checkpointer, thread_id
from .suggestions import Suggestion, suggest

Serve = Callable[[Any, int, bool], None]  # app, port, open the browser


class _PairReviewStopped(Exception):
    """The user stopped at the human prompt; ordinary scan interrupts retain their existing behavior."""


def main(
    argv: Sequence[str] | None = None,
    llm: LLM | None = None,
    embedder: Embedder | None = None,
    counter: TokenCounter | None = None,
    verifier: LLM | None = None,
    serve: Serve | None = None,
    expansion_query: Query | None = None,
    decide: Callable[[Suggestion], str] | None = None,  # returns "a", "s" or "q"; the default asks on stdin
) -> int:
    parser = argparse.ArgumentParser(prog="constellation")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_command = commands.add_parser("scan", help="read a Claude Code config directory and write a constellation JSON file")
    scan_command.add_argument("config_dir", type=Path)
    scan_command.add_argument("--no-usage", action="store_true", help="skip reading local transcripts")
    scan_command.add_argument("--no-origins", action="store_true", help="do not work out where each Item came from (no lockfile is read)")
    scan_command.add_argument(
        "--skill-lock", type=Path, help="the skills installer lockfile to read `source` from (default ~/.agents/.skill-lock.json)"
    )
    scan_command.add_argument("--out", type=Path, default=Path("constellation.json"))
    scan_command.add_argument("--project", type=Path, help="also read this repo's .claude/ folder and .mcp.json as project-scope Items")
    scan_command.add_argument(
        "--count-bodies",
        action="store_true",
        help="also count each skill's full text (sends redacted bodies to Anthropic's counting endpoint)",
    )
    scan_command.add_argument("--no-history", action="store_true", help="do not record this scan's counts in the scan history")
    scan_command.add_argument("--dry-run", action="store_true", help="print what would be sent to the providers; send nothing")
    scan_command.add_argument(
        "--offline", action="store_true", help="make no paid or network calls: no labels or verifier, cached token costs only"
    )
    scan_command.add_argument("--no-verify", action="store_true", help="skip the stronger model that labels candidate Overlaps")
    scan_command.add_argument(
        "--review-ambiguous", action="store_true", help="pause uncertain pairs for same/different/skip before model verification"
    )
    open_command = commands.add_parser("open", help="serve a constellation JSON file as a graph in the browser")
    open_command.add_argument("file", type=Path, nargs="?", default=Path("constellation.json"))
    open_command.add_argument("--port", type=int, default=8765)
    open_command.add_argument("--no-browser", action="store_true")
    open_command.add_argument("--history", type=Path, help="scan history file to chart (default ~/.cache/constellation/history.json)")
    open_command.add_argument("--preview", type=Path, help="saved `preview --out` file to show in the Brief (read-only)")
    open_command.add_argument("--config-dir", type=Path, help="enable live MCP tool listing from this config root")
    expand_command = commands.add_parser("expand", help="list the tools of one configured local MCP server")
    expand_command.add_argument("item_id")
    expand_command.add_argument("--config-dir", type=Path, required=True)
    expand_command.add_argument("--file", type=Path, default=Path("constellation.json"))
    open_command.add_argument("--checklist", type=Path, help="private cleanup checklist path (outside the Claude setup)")
    report_command = commands.add_parser(
        "report", help="print a plain-text report of a saved scan (reads the file only; no network, no cost)"
    )
    report_command.add_argument("file", type=Path, nargs="?", default=Path("constellation.json"))
    report_command.add_argument("--top", type=int, default=15, help="how many Items to list by always-on cost")
    report_command.add_argument("--all", action="store_true", help="also list distinct pairs")
    report_command.add_argument("--cleanup", type=Path, help="also write a markdown checklist of cleanup candidates to this new file")
    report_command.add_argument("--force", action="store_true", help="let --cleanup overwrite an existing file")
    export_command = commands.add_parser("export", help="write a read-only public Snapshot; does NOT anonymise free text")
    export_command.add_argument("--public", action="store_true", required=True)
    export_command.add_argument("file", type=Path, nargs="?", default=Path("constellation.json"))
    export_command.add_argument("--out", type=Path, required=True, help="new output directory; never overwrites or publishes")
    review_command = commands.add_parser(
        "review", help="go through Suggestions one at a time and write the approved ones to a checklist (no network, no cost)"
    )
    review_command.add_argument("file", type=Path, nargs="?", default=Path("constellation.json"))
    review_command.add_argument("--out", type=Path, default=Path("cleanup.md"), help="the checklist to write")
    review_command.add_argument("--force", action="store_true", help="overwrite an existing checklist")
    diff_command = commands.add_parser("diff", help="list Items added, removed or changed between two saved scans (reads the files only)")
    diff_command.add_argument("old", type=Path)
    diff_command.add_argument("new", type=Path)
    diff_command.add_argument("--json", action="store_true", help="print the diff as JSON")
    preview_command = commands.add_parser(
        "preview", help="show what installing a downloaded plugin or skill folder would add (reads the folder only; nothing is run or sent)"
    )
    preview_command.add_argument("dir", type=Path)
    preview_command.add_argument("--against", type=Path, default=Path("constellation.json"), help="saved scan to compare with")
    preview_command.add_argument("--out", type=Path, help="also write the preview to this new file (private)")
    preview_command.add_argument("--force", action="store_true", help="let --out overwrite an existing file")
    preview_command.add_argument(
        "--meaning",
        action="store_true",
        help="also compare by meaning with the local embedder; its first use may download the model "
        "(BAAI/bge-small-en-v1.5) from the network",
    )
    delta_command = commands.add_parser("delta", help="what changed between two saved scans: Items, always-on tokens, new Overlaps")
    delta_command.add_argument("before", type=Path)
    delta_command.add_argument("after", type=Path)
    args = parser.parse_args(argv)
    if args.command == "preview":
        return _preview(args, embedder)  # reads the folder and saved scan only, so it skips load_env
    if args.command == "delta":
        return _delta(args)
    if args.command == "diff":
        return _diff(args)  # reads the files only, so it skips load_env
    if args.command == "export":
        return _export(args)
    if args.command == "expand":
        data = _load_scan(args.file)
        if data is None:
            return 2
        try:
            expansion_result = asyncio.run(expand(data, args.item_id, args.config_dir, expansion_query))
        except (KeyError, ValueError):
            print("Unknown Item or invalid scan/config input.", file=sys.stderr)
            return 2
        print(json.dumps(asdict(expansion_result), indent=2))
        return 0
    if args.command == "review":
        return _review(args, decide)  # reads the scan file only, so it skips load_env
    if args.command == "report":
        return _report(args)  # reads the file only, so it skips load_env
    if args.command == "open":
        return _open(args, serve, expansion_query)  # serving never needs the API key, so it skips load_env
    review_ambiguous = args.review_ambiguous and not args.dry_run
    if review_ambiguous and not sys.stdin.isatty():
        print("Ignoring --review-ambiguous: stdin is not a terminal; using the verifier.", file=sys.stderr)
        review_ambiguous = False
    load_env()  # a .env file in the working directory may hold ANTHROPIC_API_KEY

    if not args.config_dir.is_dir():
        print(f"{args.config_dir} is not a directory.", file=sys.stderr)
        return 2

    if args.project is not None and not args.project.is_dir():
        print("--project must be a directory.", file=sys.stderr)
        return 2

    lockfile = args.skill_lock or origin_sources.DEFAULT_LOCKFILE
    if not args.no_origins and lockfile.is_file():
        print(f"read origin from {lockfile} (source field only)", file=sys.stderr)
    sent: list[str] = []
    # An injected llm stands in for the key; otherwise no key means offline, as if --offline were given.
    offline = not args.dry_run and (args.offline or (llm is None and not os.environ.get("ANTHROPIC_API_KEY")))
    if offline and args.count_bodies:
        print("--count-bodies sends skill text to Anthropic, so it cannot run offline.", file=sys.stderr)
        return 2
    label_model = verifier_model = ""
    if offline:
        if not args.offline:
            print(
                "ANTHROPIC_API_KEY is not set: running offline (no labels or verifier; use --dry-run to see what a real run sends).",
                file=sys.stderr,
            )
        embedder = embedder or _local_embedder()
        if embedder is None:
            print("Clustering skipped: install the local embedder with `uv sync --extra local`.", file=sys.stderr)
    elif args.dry_run:
        # These sit behind scan()'s redaction, so what is printed is exactly what a real run would send.
        local = embedder or _local_embedder()  # the local embedder sends nothing anywhere, so the dry run may really use it
        llm, embedder, counter = _record_prompt(sent), _record_texts(sent, local), _record_counts(sent)
        verifier = _record_verify(sent)
    else:
        if llm is None:
            try:
                from .anthropic_llm import MODEL, VERIFIER_MODEL, anthropic_counter, anthropic_llm

                label_model = MODEL
                verifier_model = VERIFIER_MODEL
                llm, counter = anthropic_llm(), counter or anthropic_counter()
                verifier = verifier or anthropic_llm(model=VERIFIER_MODEL, max_tokens=2048)
            except ImportError:
                print("The anthropic package is not installed; run `uv sync --extra llm`.", file=sys.stderr)
                return 2
        if embedder is None:
            from .embeddings import fastembed_embedder

            embedder = fastembed_embedder()

    with tempfile.TemporaryDirectory() as scratch:  # a dry run must not write the real token-count cache
        cache = Path(scratch) / "counts.json" if args.dry_run else None  # likewise the label and verdict caches below
        try:
            result = scan(
                args.config_dir,
                llm=llm,
                embedder=embedder,
                counter=counter,
                count_bodies=args.count_bodies,
                cost_cache=cache,
                verifier=None if args.no_verify else verifier,
                verdict_cache=Path(scratch) / "verdicts.json" if args.dry_run else None,
                on_verify=None if args.dry_run else lambda calls, tokens: _announce(calls, tokens, possible=review_ambiguous),
                label_cache=Path(scratch) / "labels.json" if args.dry_run else None,
                label_model=label_model,
                verifier_model=verifier_model,
                offline=offline,
                usage=not args.no_usage,
                origins=not args.no_origins,
                lockfile=args.skill_lock,
                project=args.project,
                checkpoint=None if args.dry_run else scan_graph.DEFAULT_CHECKPOINT,  # a dry run writes no file
                on_progress=None if args.dry_run else lambda line: print(line, file=sys.stderr),
                ask_pairs=_ask_pair_stdin if review_ambiguous else None,
            )
        except _PairReviewStopped:
            print("Scan paused; rerun with --review-ambiguous to resume.", file=sys.stderr)
            return 130
    if args.dry_run:
        print("\n".join(sorted(sent)))  # parallel calls finish in any order; one sorted print is whole, readable and repeatable
        if local is None and not args.no_verify:
            print("No similarity-based verifier prompts can be shown: install the local embedder with `uv sync --extra local`.")
        for warning in result.warnings:
            if warning.startswith("could not cluster items"):
                print(warning, file=sys.stderr)
        return 0
    if result.items and not result.labels and not offline:  # every model call failed: report why instead of writing a half-empty file
        first = next((w for w in result.warnings if FAILED_PREFIX in w), "unknown")
        print(f"No Item could be labelled. First problem: {first}", file=sys.stderr)
        return 1
    _write(
        result, args.out, read_secrets(args.config_dir, args.project), args.config_dir, None if args.no_history else history.DEFAULT_CACHE
    )
    if not (args.no_usage or args.no_history):  # smarter-verdict 3.2: the habit ledger; S4 may give it its own flag
        for warning in habits.update(habits.DEFAULT_CACHE, args.config_dir, result.items, result.relations):
            print(warning, file=sys.stderr)
    return 0


def _load_scan(file: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(file.read_text())
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or not isinstance(
        data.get("items"), list
    ):  # shortcut: only the top-level shape is checked, not each field
        print(f"{file} is missing or not a constellation scan; run `constellation scan` first.", file=sys.stderr)
        return None
    return data


def _export(args: argparse.Namespace) -> int:
    data = _load_scan(args.file)
    if data is None:
        return 2
    try:
        write_snapshot(data, args.out)
    except FileExistsError:
        print("Output already exists; choose a new directory.", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print("Could not export: check the saved scan, frontend build and output directory.", file=sys.stderr)
        return 2
    print(f"{NOTICE}\n{LIMITS}\nWrote {args.out.resolve()}")
    return 0


def _ask_stdin(suggestion: Suggestion) -> str:
    while True:
        try:
            answer = input("[a]pprove, [s]kip, [q]uit? ").strip().lower()
        except EOFError:
            return "q"
        if answer in ("a", "s", "q"):
            return answer


def _ask_pair_stdin(_a: str, _b: str) -> str:
    while True:
        print("same (duplicate job) / different / skip (use verifier)?", file=sys.stderr)
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise _PairReviewStopped from None
        if answer in scan_graph.PAIR_CHOICES:
            return answer


def _review(args: argparse.Namespace, decide: Callable[[Suggestion], str] | None) -> int:
    data = _load_scan(args.file)
    if data is None:
        return 2
    if args.out.exists() and not args.force:
        print(f"{args.out} already exists; pass --force to overwrite it.", file=sys.stderr)
        return 2
    suggestions = suggest(data)
    if not suggestions:
        print("No Suggestions found.")
        return 0
    decide = decide or _ask_stdin
    by_id = {s.id: s for s in suggestions}
    # The thread id names this scan file's saved review; the checkpoint holds only Suggestion ids and answers.
    graph = build_review_graph(open_checkpointer())
    config: Any = {"configurable": {"thread_id": thread_id(args.file)}, "recursion_limit": len(suggestions) * 2 + 10}
    result = graph.invoke({"suggestions": list(by_id)}, config)  # keeps saved answers and replaces any stale pause
    while "__interrupt__" in result:
        pending = by_id[result["__interrupt__"][0].value]
        done = sum(i in result.get("decisions", {}) for i in by_id)
        print(f"\n[{done + 1}/{len(by_id)}] {pending.reason}")
        print(f"Saves about {pending.tokens_saved:,} always-on tokens." if pending.tokens_saved is not None else "Saving: unknown.")
        try:
            answer = decide(pending)
        except KeyboardInterrupt:
            answer = "q"
        if answer not in ("a", "s"):
            break  # leave the thread paused: the next run asks this same Suggestion
        result = graph.invoke(Command(resume="approve" if answer == "a" else "skip"), config)
    decisions = result.get("decisions", {})
    approved = [s for s in suggestions if decisions.get(s.id) == "approve"]
    write_private(args.out, render_cleanup(data, top=5, approved=approved))
    skipped = sum(decisions.get(s.id) == "skip" for s in suggestions)
    print(f"\n{len(approved)} approved, {skipped} skipped, {len(suggestions) - len(approved) - skipped} left. Checklist: {args.out}")
    return 0


def _diff(args: argparse.Namespace) -> int:
    old, new = _load_scan(args.old), _load_scan(args.new)
    if old is None or new is None:
        return 2
    d = diff_scans(old, new)
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        print(render_diff(d, color=color, width=max(40, min(shutil.get_terminal_size().columns, 100))), end="")
    return 0


def _report(args: argparse.Namespace) -> int:
    data = _load_scan(args.file)
    if data is None:
        return 2
    if args.cleanup and args.cleanup.exists() and not args.force:
        print(f"{args.cleanup} already exists; pass --force to overwrite it.", file=sys.stderr)
        return 2
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    width = max(40, min(shutil.get_terminal_size().columns, 100))
    print(render_report(data, top=args.top, color=color, width=width, show_all=args.all), end="")
    if args.cleanup:
        write_private(args.cleanup, render_cleanup(data, top=args.top))
    return 0


def _open(args: argparse.Namespace, serve: Serve | None, expansion_query: Query | None) -> int:
    if not args.file.is_file():
        print(f"{args.file} not found; run `constellation scan` first.", file=sys.stderr)
        return 2
    if args.preview and not args.preview.is_file():
        print(f"{args.preview} not found; make it with `constellation preview DIR --out FILE`.", file=sys.stderr)
        return 2
    try:
        from . import server
    except ImportError:
        print("fastapi and uvicorn are not installed; run `uv sync --extra app`.", file=sys.stderr)
        return 2
    if not (server.STATIC / "index.html").is_file():
        print(server.BUILD_HINT, file=sys.stderr)
        return 2
    try:
        app = server.create_app(
            args.file,
            checklist=args.checklist,
            config_dir=args.config_dir,
            expansion_query=expansion_query,
            history=args.history,
            preview=args.preview,
        )
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    (serve or server.serve)(app, args.port, not args.no_browser)
    return 0


def _preview(args: argparse.Namespace, embedder: Embedder | None) -> int:
    if not args.dir.is_dir():
        print(f"{args.dir} is not a directory.", file=sys.stderr)
        return 2
    if args.out and args.out.exists() and not args.force:
        print(f"{args.out} already exists; pass --force to overwrite it.", file=sys.stderr)
        return 2
    scan_data = None
    if args.against.is_file():
        if (scan_data := _load_scan(args.against)) is None:
            return 2
    else:
        print(f"No saved scan at {args.against}, so overlap with your setup was not checked. Run `constellation scan` first.")
    if scan_data is not None and embedder is None and args.meaning:
        if (embedder := _local_embedder()) is not None:
            print(
                "Using the local embedder. If its model is not cached yet, this downloads it from the network once; "
                "no Item text leaves your machine.",
                file=sys.stderr,
            )
    try:
        result = preview(args.dir, scan_data, embedder)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(render_preview(result), end="")
    if args.out:
        write_private(args.out, json.dumps(result, indent=2))
    return 0


def _delta(args: argparse.Namespace) -> int:
    before, after = _load_scan(args.before), _load_scan(args.after)
    if before is None or after is None:
        return 2
    names = {i["id"]: i["name"] for scan_data in (before, after) for i in scan_data["items"]}
    print(render_delta(delta(before, after), names), end="")
    return 0


def _write(result: Constellation, path: Path, secrets: set[str], config_dir: Path, history_path: Path | None) -> None:
    day, setup = history._today(), history.key(str(config_dir.resolve()))
    result.scanned_at, result.setup = day, setup
    result.items = [replace(i, description=redact(i.description, secrets)) for i in result.items]  # the Items hold raw text
    text = json.dumps(asdict(result), indent=2)  # serialise first: a failure must not leave an empty file behind
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)  # open() keeps the mode of a file that already existed
    with os.fdopen(fd, "w") as f:
        f.write(text)
    if history_path is not None:
        try:
            history.record(history_path, history.entry(asdict(result), setup, day))
        except OSError as error:
            print(f"could not save scan history: {error}", file=sys.stderr)


def _local_embedder() -> Embedder | None:
    if importlib.util.find_spec("fastembed") is None:
        return None
    from .embeddings import fastembed_embedder

    return fastembed_embedder()


def _announce(calls: int, input_tokens: int, *, possible: bool = False) -> None:
    from .anthropic_llm import VERIFIER_MODEL

    pairs = f"{calls} pair" + ("" if calls == 1 else "s")
    action = "maximum possible cost for" if possible else "verifying"
    print(
        f"{action} {pairs} with {VERIFIER_MODEL}, about ${estimate_cost(calls, input_tokens):.3f} (cached pairs are free)", file=sys.stderr
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
