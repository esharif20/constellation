"""Quality of the model-free grouping on an invented, hand-labelled setup (no model, no network, fast, so it runs in the default suite)."""

import json
from itertools import combinations
from pathlib import Path

from constellation.grouping import FILLER, group_items
from constellation.models import Item, Relation

# (group, kind, name, description, origin)
ROWS = [
    ("design", "skill", "frontend-design", "Guidance for distinctive visual design when building new UI", "designkit"),
    ("design", "skill", "ui-ux-pro-max", "Palettes, font pairings and UX guidelines for web interfaces", "designkit"),
    ("design", "skill", "scroll-craft", "Craft smooth scroll animation and easing for landing pages", "designkit"),
    ("design", "skill", "shadcn", "Add and compose shadcn components with Tailwind styling", "designkit"),
    ("design", "skill", "dataviz", "Colour and layout rules for charts and dashboards", None),
    ("design", "skill", "design-taste", "Anti-slop art direction and typography for landing pages", None),
    ("firecrawl", "skill", "firecrawl-scrape", "Scrape a web page into clean markdown", "firecrawl"),
    ("firecrawl", "skill", "firecrawl-crawl", "Crawl a whole website and save every page", "firecrawl"),
    ("firecrawl", "skill", "firecrawl-search", "Search the web and return full page content", "firecrawl"),
    ("firecrawl", "skill", "firecrawl-map", "Map every URL on a website quickly", "firecrawl"),
    ("firecrawl", "skill", "firecrawl-download", "Download a site as local files", "firecrawl"),
    ("firecrawl", "skill", "firecrawl-agent", "Extract structured data from websites as JSON", "firecrawl"),
    ("git", "skill", "commit-helper", "Write clear commit messages from the staged changes", None),
    ("git", "skill", "pr-opener", "Open a pull request with a summary of the change", None),
    ("git", "skill", "branch-cleaner", "Delete merged branches and tidy the git repository", None),
    ("git", "skill", "merge-resolver", "Resolve git merge conflicts between two branches", None),
    ("git", "skill", "worktree-setup", "Create an isolated git worktree for a branch", None),
    ("git", "skill", "pr-writer", "Write a pull request body from the commits", None),
    ("notes", "skill", "obsidian-markdown", "Write Obsidian flavoured markdown notes with wikilinks", "obsidian"),
    ("notes", "skill", "obsidian-bases", "Create Obsidian bases to query notes in the vault", "obsidian"),
    ("notes", "skill", "obsidian-cli", "Use the Obsidian command line to manage the vault", "obsidian"),
    ("notes", "skill", "anki-flashcards", "Generate Anki flashcards from lecture notes for revision", None),
    ("notes", "skill", "lecture-notes", "Turn lecture slides into structured study notes", None),
    ("notes", "skill", "exam-pipeline", "Analyse past exam papers for revision priorities", None),
    ("vercel", "skill", "vercel-deploy", "Deploy the app to Vercel production", "vercel"),
    ("vercel", "skill", "vercel-env", "Manage Vercel environment variables for a project", "vercel"),
    ("vercel", "skill", "vercel-cron", "Configure Vercel cron jobs for scheduled functions", "vercel"),
    ("vercel", "skill", "vercel-storage", "Pick Vercel blob or edge config storage for data", "vercel"),
    ("vercel", "skill", "vercel-rollback", "Roll back a bad Vercel deployment", "vercel"),
    ("vercel", "skill", "vercel-flags", "Add Vercel feature flags to a Next.js app", "vercel"),
    ("testing", "skill", "tdd", "Test driven development with red green refactor loops", None),
    ("testing", "skill", "mutation-tester", "Run mutation tests to measure how good the tests are", None),
    ("testing", "skill", "coverage-checker", "Measure test coverage and list untested code", None),
    ("testing", "skill", "flaky-test-hunter", "Find and diagnose flaky failing tests", None),
    ("testing", "skill", "diagnosing-bugs", "Diagnosis loop for hard bugs and failing tests", None),
    ("testing", "skill", "verification", "Verify the tests pass before claiming a change is done", None),
    ("writing", "skill", "doc-writer", "Write and polish documentation and long form prose", None),
    ("writing", "skill", "readme-editor", "Edit README files and improve writing clarity", None),
    ("writing", "skill", "stop-slop", "Remove AI writing patterns from prose", None),
    ("writing", "skill", "academic-writing", "Academic writing assistant for dissertation chapters", None),
    ("writing", "skill", "proofreader", "Check spelling grammar and tone in writing", None),
    ("writing", "skill", "latex-document", "Create and compile LaTeX documents into PDF", None),
    ("agents", "agent", "planner", "Creates executable plans with task breakdown for a phase", "gsdkit"),
    ("agents", "agent", "executor", "Executes plans with atomic commits and workflow state", "gsdkit"),
    ("agents", "agent", "verifier", "Verifies that a phase goal was achieved by the plan", "gsdkit"),
    ("agents", "agent", "roadmapper", "Creates project roadmaps with phase breakdown", "gsdkit"),
    ("agents", "agent", "plan-checker", "Checks a plan will achieve the phase goal", "gsdkit"),
    ("agents", "agent", "debugger-agent", "Investigates bugs with the scientific method for a phase", "gsdkit"),
    ("browser", "skill", "agent-browser", "Browser automation CLI to click, fill forms and take screenshots", "browserkit"),
    ("browser", "skill", "chrome-browser", "Drive the Chrome browser to navigate pages and click", "browserkit"),
    ("browser", "skill", "computer-use", "Computer use to control the screen with screenshots and clicks", "browserkit"),
    ("browser", "skill", "browser-verify", "Verify dev server output in the browser with screenshots", "browserkit"),
    ("browser", "skill", "built-in-browser", "Built in browser automation for navigation and clicking", "browserkit"),
    ("browser", "mcp_server", "playwright-browser", "Browser automation server to click and screenshot pages", None),
    ("review", "skill", "code-review", "Review a code diff for bugs, style problems and risky changes", None),
    ("review", "skill", "security-review", "Audit code for security vulnerabilities and unsafe patterns", None),
    ("review", "skill", "simplify", "Review changed code for reuse, simplification and cleanups", None),
    ("review", "skill", "refactor-advisor", "Suggest refactors that simplify and deepen modules", None),
    ("review", "skill", "lint-fixer", "Run the linter and fix the style problems it finds", None),
    ("review", "skill", "type-checker", "Run the type checker and fix type errors in code", None),
]
ITEMS = [Item(f"{g}/{name}", kind, name, desc, "claude-code", origin=origin) for g, kind, name, desc, origin in ROWS]
TRUTH = {frozenset(p) for g in {r[0] for r in ROWS} for p in combinations(sorted(f"{g}/{r[2]}" for r in ROWS if r[0] == g), 2)}


def _pairs(clusters):
    return {frozenset(p) for c in clusters for p in combinations(sorted(c.item_ids), 2)}


def test_pairwise_quality_and_size_distribution():
    clusters = group_items(ITEMS, [], {})
    found = _pairs(clusters)
    precision, recall = len(found & TRUTH) / len(found), len(found & TRUTH) / len(TRUTH)
    sizes = sorted(len(c.item_ids) for c in clusters)
    assert precision >= 0.7 and recall >= 0.65, (precision, recall, sizes)
    assert max(sizes) <= 0.2 * len(ITEMS)
    assert 8 <= len(clusters) <= 14
    assert sizes[0] >= 3
    assert len({c.name for c in clusters}) == len(clusters)


def test_plugin_families_stay_together():
    clusters = group_items(ITEMS, [], {})
    where = {i: n for n, c in enumerate(clusters) for i in c.item_ids}
    for family in ("firecrawl", "vercel", "agents"):
        homes = {where[f"{r[0]}/{r[2]}"] for r in ROWS if r[0] == family}
        assert len(homes) == 1, family


def test_demo_250_has_no_giant_cluster():
    data = json.loads((Path(__file__).parents[2] / "docs/design/demo-250.json").read_text())
    items = [Item(**{k: v for k, v in i.items() if k in Item.__dataclass_fields__}) for i in data["items"]]
    clusters = group_items(items, [Relation(**r) for r in data["relations"]], {})
    sizes = [len(c.item_ids) for c in clusters]
    assert max(sizes) <= 0.2 * len(items)
    assert 11 <= len(clusters) <= 35
    assert min(sizes) >= 3
    assert sum(sizes) >= 0.95 * len(items)


def _demo_clusters():
    data = json.loads((Path(__file__).parents[2] / "docs/design/demo-250.json").read_text())
    items = [Item(**{k: v for k, v in i.items() if k in Item.__dataclass_fields__}) for i in data["items"]]
    return group_items(items, [Relation(**r) for r in data["relations"]], {})


def test_names_have_no_filler_and_distinct_heads():
    for clusters in (group_items(ITEMS, [], {}), _demo_clusters()):
        named = [c.name for c in clusters]
        words = [w.lower() for n in named for w in n.split()]
        assert not [w for w in words if w in FILLER], named
        heads = [n.split()[0] for n in named]
        assert len(set(heads)) >= 0.9 * len(heads), heads
