"""Hand-labelled search quality on invented Items. Precision@3 = share of the top 3 hits that are relevant (for a query with nothing
relevant, any hit counts against it). Run with: uv run --all-extras pytest -m eval -s tests/eval/test_search_quality.py"""

import pytest

from constellation.embeddings import fastembed_embedder
from constellation.retrieve import Index

ITEMS = {
    "gmail": ("gmail-helper", "Reads the inbox and drafts replies to messages"),
    "slides": ("deck-builder", "Builds a presentation from rough notes"),
    "pdf": ("pdf-reader", "Extracts text and tables from PDF files"),
    "tests": ("test-runner", "Runs the unit tests and reports failures"),
    "shadcn": ("shadcn", "Adds and composes UI components"),
    "deploy": ("vercel-deploy", "Deploys the app to production hosting"),
    "docs": ("doc-writer", "Writes and polishes documentation and prose"),
    "cal": ("calendar-sync", "Creates meetings and schedules events on the calendar"),
    "sql": ("sql-tuner", "Explains slow database queries and suggests indexes"),
    "git": ("commit-helper", "Writes commit messages from the staged diff"),
    "review": ("code-review", "Reviews a pull request for bugs and style"),
    "sec": ("secret-scanner", "Finds leaked passwords and API keys in the repository"),
    "img": ("image-resizer", "Resizes and compresses pictures"),
    "trans": ("translator", "Translates text between languages"),
    "sheet": ("spreadsheet-analyst", "Summarises data in Excel and CSV files"),
    "web": ("web-research", "Searches the internet and cites sources"),
    "dock": ("docker-debugger", "Diagnoses failing containers and images"),
    "lint": ("lint-fixer", "Fixes formatting and style warnings automatically"),
    "mem": ("memory-keeper", "Remembers project decisions between sessions"),
    "chart": ("chart-maker", "Draws graphs and plots from numbers"),
}
# query -> relevant item keys (empty: nothing should match)
QUERIES = {
    "email": {"gmail"},
    "mail": {"gmail"},
    "inbox": {"gmail"},
    "make slides": {"slides"},
    "powerpoint": {"slides"},
    "presentation": {"slides"},
    "read a pdf": {"pdf"},
    "pdfreader": {"pdf"},
    "pdf reader": {"pdf"},
    "run unit tests": {"tests"},
    "shadnc": {"shadcn"},
    "shadcm": {"shadcn"},
    "ui components": {"shadcn"},
    "put it live": {"deploy"},
    "ship to production": {"deploy"},
    "write docs": {"docs"},
    "documentaton": {"docs"},
    "schedule a meeting": {"cal"},
    "calender": {"cal"},
    "slow queries": {"sql"},
    "database": {"sql"},
    "commit message": {"git"},
    "check my pull request": {"review"},
    "leaked api key": {"sec"},
    "shrink pictures": {"img"},
    "translate": {"trans"},
    "excel": {"sheet"},
    "look something up online": {"web"},
    "where is my docker skill": {"dock"},
    "graph my numbers": {"chart"},
    "qqqzzzxx": set(),
    "banana smoothie recipe": set(),
    "xkcd": set(),
}


def precision_at_3(index):
    scores = {}
    for query, relevant in QUERIES.items():
        top = [ids for ids in (h["id"] for h in index.query(query, 3))]
        scores[query] = (len([i for i in top if i in relevant]) / len(top)) if top else (0.0 if relevant else 1.0)
    return scores


@pytest.mark.eval
def test_hybrid_beats_words_only(tmp_path):
    items = [{"id": k, "kind": "skill", "name": n, "description": d} for k, (n, d) in ITEMS.items()]
    words = Index(items)
    hybrid = Index(items)
    hybrid.add_vectors(fastembed_embedder(), tmp_path / "e.json")
    assert hybrid.vectors is not None, hybrid.note
    a, b = precision_at_3(words), precision_at_3(hybrid)
    mean = lambda s: sum(s.values()) / len(s)  # noqa: E731
    print(f"\nprecision@3 over {len(QUERIES)} queries: words-only {mean(a):.3f}, hybrid {mean(b):.3f}")
    for q in QUERIES:
        print(f"  {a[q]:.2f} -> {b[q]:.2f}  {q!r}  {[h['id'] for h in hybrid.query(q, 3)]}")
    assert mean(b) > mean(a)
    assert all(not hybrid.query(q) for q, rel in QUERIES.items() if not rel)
