"""How well do real embeddings group a setup? Slow (downloads a model on first run), so it is not in the fast suite.

Run with: uv run --extra local pytest -m eval -s
The groups below are synthetic, written to resemble a Claude Code setup. Edit them to match yours: the score is a regression
guard and a way to choose the threshold, not proof of quality on your real setup.
"""

from itertools import combinations

import pytest

from constellation.cluster import item_vectors
from constellation.grouping import group_items
from constellation.models import Item

GROUPS = {
    "writing": [
        ("doc-writer", "Writes and polishes documentation and long-form prose"),
        ("readme-editor", "Edits README files and improves writing style and clarity"),
        ("blog-drafter", "Drafts blog posts and articles from rough notes"),
        ("changelog-writer", "Writes release notes and changelog entries from commits"),
        ("proofreader", "Checks spelling, grammar and tone in text"),
    ],
    "testing": [
        ("test-runner", "Runs the unit tests and reports failures"),
        ("mutation-tester", "Runs mutation tests to check how good the tests are"),
        ("tdd-loop", "Drives red-green-refactor test-driven development one test at a time"),
        ("coverage-checker", "Measures test coverage and lists untested code"),
        ("flaky-test-hunter", "Finds and diagnoses flaky or intermittently failing tests"),
    ],
    "deployment": [
        ("vercel-deploy", "Deploys the app to Vercel production"),
        ("release-pusher", "Pushes a release build to the hosting platform"),
        ("rollback-helper", "Rolls back a bad deployment to the previous version"),
        ("env-manager", "Manages environment variables across preview and production"),
        ("ci-watcher", "Watches the CI pipeline and reports when a deploy finishes"),
    ],
    "research": [
        ("web-research", "Searches the web and summarises sources with citations"),
        ("paper-reader", "Reads academic papers and extracts the key findings"),
        ("doc-fetcher", "Fetches and indexes documentation pages for later questions"),
        ("competitor-scan", "Compares similar tools and products and lists their differences"),
        ("fact-checker", "Checks claims against primary sources"),
    ],
    "code-review": [
        ("diff-reviewer", "Reviews a code diff for bugs, style problems and risky changes"),
        ("security-audit", "Audits code for security vulnerabilities and unsafe patterns"),
        ("refactor-advisor", "Suggests refactors to simplify and deepen modules"),
        ("lint-fixer", "Runs the linter and fixes the style problems it finds"),
        ("type-checker", "Runs the type checker and fixes type errors"),
    ],
    "git": [
        ("commit-helper", "Writes clear commit messages from the staged changes"),
        ("branch-cleaner", "Deletes merged branches and tidies the repository"),
        ("pr-opener", "Opens a pull request with a summary of the change"),
        ("merge-resolver", "Resolves merge conflicts between two branches"),
        ("history-explorer", "Explores git history to find when a change was introduced"),
    ],
}


def _pairs(groups):
    return {frozenset(p) for members in groups for p in combinations(sorted(members), 2)}


def _scores(embed, threshold):
    items = [Item(f"{g}/{n}", "skill", n, d, "claude-code") for g, rows in GROUPS.items() for n, d in rows]
    vectors, centred = item_vectors(items, embed)
    found = _pairs(c.item_ids for c in group_items(items, [], {}, vectors if centred else None, threshold))
    truth = _pairs([f"{g}/{n}" for n, _ in rows] for g, rows in GROUPS.items())
    precision = len(found & truth) / len(found) if found else 1.0
    recall = len(found & truth) / len(truth)
    return precision, recall, 2 * precision * recall / (precision + recall) if precision + recall else 0.0


@pytest.mark.eval
def test_real_embeddings_group_a_setup_well_at_the_default_threshold():
    from constellation.embeddings import fastembed_embedder

    embed = fastembed_embedder()
    print("\nthreshold  precision  recall   f1")
    for threshold in (0.0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5):
        p, r, f = _scores(embed, threshold)
        print(f"  {threshold:.2f}      {p:.2f}      {r:.2f}   {f:.2f}")
    _, _, f1 = _scores(embed, None)
    assert f1 >= 0.3  # a regression guard under the measured score at the default (0.37), not a target: see the shortcut note in cluster.py
