"""About twenty hand-labelled pairs of invented Items for scoring the Overlap verifier. Nothing here comes from a real setup.

Each row: (name_a, description_a, name_b, description_b, expected verdict). For a wrapper, A is the one that hands off to B."""

import math
import re
from collections import Counter

from constellation.models import LLM, Item
from constellation.overlaps import VERDICTS, ambiguity, check_one, pair_job

PAIRS: list[tuple[str, str, str, str, str]] = [
    # duplicate: the same job under different names
    (
        "tidy-prose",
        "Removes filler and AI-sounding phrasing from written text",
        "plain-writing",
        "Strips filler words and AI-sounding phrases from prose",
        "duplicate",
    ),
    (
        "commit-msg",
        "Writes a conventional commit message from the staged diff",
        "git-commit-writer",
        "Writes a conventional commit message from the staged diff",
        "duplicate",
    ),
    ("pdf-summary", "Summarises a PDF file into key points", "pdf-digest", "Summarises a PDF document into its key points", "duplicate"),
    (
        "sql-explainer",
        "Explains what a SQL query does in plain English",
        "query-explain",
        "Explains in plain English what a SQL query does",
        "duplicate",
    ),
    (
        "todo-sweep",
        "Finds TODO comments across the repo and lists them",
        "todo-finder",
        "Lists every TODO comment found across the repo",
        "duplicate",
    ),
    # wrapper: one only hands off to the other (A is the wrapper)
    ("quick-review", "Reviews my changes", "code-review", "Reviews a pull request for bugs, style and test gaps", "wrapper"),
    ("ship-it", "Ships the current branch", "release-branch", "Tags, builds and publishes the current branch", "wrapper"),
    ("deep-read", "Reads a paper in depth", "paper-reader", "Reads an academic paper and extracts claims, methods and limits", "wrapper"),
    ("lint-all", "Lints the project", "lint-runner", "Runs every configured linter and groups the findings", "wrapper"),
    ("db-check", "Checks the database", "schema-audit", "Audits a database schema for missing indexes and bad types", "wrapper"),
    # overlap: partly the same job
    ("review-pr", "Reviews a pull request for bugs and style", "review-prose", "Reviews written prose for clarity and style", "overlap"),
    ("test-writer", "Writes unit tests for a function", "test-fixer", "Fixes failing unit tests and writes missing ones", "overlap"),
    ("doc-writer", "Writes API documentation from code", "readme-writer", "Writes a README and API documentation for a project", "overlap"),
    (
        "log-reader",
        "Reads application logs and finds errors",
        "trace-reader",
        "Reads stack traces and application logs to find the cause of errors",
        "overlap",
    ),
    (
        "web-search",
        "Searches the web and cites sources",
        "deep-research",
        "Searches many web pages, cross-checks sources and writes a cited report",
        "overlap",
    ),
    # distinct: different jobs, some with similar words
    ("pdf-summary", "Summarises a PDF file into key points", "pdf-split", "Splits a PDF into one file per chapter", "distinct"),
    (
        "review-pr",
        "Reviews a pull request for bugs and style",
        "merge-pr",
        "Merges an approved pull request and deletes the branch",
        "distinct",
    ),
    (
        "sql-explainer",
        "Explains what a SQL query does in plain English",
        "sql-migrator",
        "Generates and applies SQL schema migrations",
        "distinct",
    ),
    ("bake-bread", "Walks through baking a loaf of bread", "bake-cake", "Walks through baking a layered cake", "distinct"),
    (
        "docker-build",
        "Builds a Docker image for the project",
        "docker-prune",
        "Removes unused Docker images and containers to free disk space",
        "distinct",
    ),
]


def _bodies(name_a: str, desc_a: str, name_b: str, desc_b: str, expected: str) -> dict[str, str]:
    """Bodies are only used to compute local signals, so they are plausible but never judged."""
    body_a = (
        f"Run /{name_b} and report what it says." if expected == "wrapper" else f"Steps for {name_a}: {desc_a}. " + "Work carefully. " * 20
    )
    return {name_a: body_a, name_b: f"Steps for {name_b}: {desc_b}. " + "Work carefully. " * 40}


def evaluate(verifier: LLM) -> tuple[Counter[tuple[str, str]], float, float]:
    """Run `verifier` (already guarded, if real) over PAIRS. Returns {(expected, predicted): count}, and the precision and recall
    of flagging a pair (any verdict but distinct). A pair with no usable verdict counts as predicted 'none'."""
    confusion: Counter[tuple[str, str]] = Counter()
    for index, (name_a, desc_a, name_b, desc_b, expected) in enumerate(PAIRS):
        a, b = Item(f"a{index}", "skill", name_a, desc_a, "eval"), Item(f"b{index}", "skill", name_b, desc_b, "eval")
        bodies = {
            a.id: _bodies(name_a, desc_a, name_b, desc_b, expected)[name_a],
            b.id: _bodies(name_a, desc_a, name_b, desc_b, expected)[name_b],
        }
        found = check_one(pair_job(a, b, bodies, (), ""), verifier).get("overlaps", [])  # no cache: every pair is judged afresh
        confusion[expected, found[0].verdict if found else "none"] += 1
    flagged = {key: n for key, n in confusion.items() if key[1] not in ("distinct", "none")}
    true_positives = sum(n for (expected, _), n in flagged.items() if expected != "distinct")
    precision = true_positives / sum(flagged.values()) if flagged else 0.0
    recall = true_positives / sum(n for (expected, _), n in confusion.items() if expected != "distinct")
    return confusion, precision, recall


def report(confusion: Counter[tuple[str, str]], precision: float, recall: float) -> str:
    columns = [*VERDICTS, "none"]
    lines = ["expected \\ predicted  " + "  ".join(f"{c:>9}" for c in columns)]
    lines += [f"{row:<21} " + "  ".join(f"{confusion[row, c]:>9}" for c in columns) for row in VERDICTS]
    return "\n".join([*lines, f"flagged precision {precision:.2f}, recall {recall:.2f}"])


def _word_cosine(a: str, b: str) -> float:
    x, y = Counter(re.findall(r"[a-z0-9]+", a.lower())), Counter(re.findall(r"[a-z0-9]+", b.lower()))
    return sum(x[k] * y[k] for k in x) / math.sqrt(sum(v * v for v in x.values()) * sum(v * v for v in y.values()))


def ambiguity_scores() -> list[tuple[str, float]]:
    """(expected verdict, ambiguity) per labelled pair, with no embedder: similarity is the description word cosine, floored at the
    0.5 every proposed pair already has."""
    scores = []
    for name_a, desc_a, name_b, desc_b, expected in PAIRS:
        bodies = _bodies(name_a, desc_a, name_b, desc_b, expected)
        a, b = Item(name_a, "skill", name_a, desc_a, "eval"), Item(name_b, "skill", name_b, desc_b, "eval")
        scores.append((expected, ambiguity(a, b, max(0.5, _word_cosine(desc_a, desc_b)), bodies[name_a], bodies[name_b])))
    return scores
