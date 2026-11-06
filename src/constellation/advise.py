"""Project advisor (#45): match a project's top-level docs and manifests against the installed Items of the latest scan.

Local and free: word/TF-IDF matching with grouping's helpers; no model, no network. Only ARCHITECTURE.md, docs/architecture.md,
README.md, package.json and pyproject.toml of the named folder are read, and their text never leaves this process or reaches the
output except as a few matched words, dependency names, script names and the redacted draft.
"""

import json
import re
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from .grouping import _cosine, _docs, _tfidf, _words
from .models import Item
from .redact import redact

DOCS = ("ARCHITECTURE.md", "docs/architecture.md", "README.md")
MAX_READ = 20_000  # characters of each file
MIN_SCORE = 0.05
TOP = 8
NOISE_TOP = 5
DEP_WEIGHT = 3  # a dependency name counts like this many prose words
KINDS = ("skill", "agent", "mcp_server")
NOISE_TIERS = ("redundant", "off", "keep_rare")
SKILLS_IN_DRAFT = 5
COMMANDS_IN_DRAFT = 6
DEP_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def _read(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        return ""
    return path.read_text(errors="replace")[:MAX_READ]


def read_project(root: Path) -> dict[str, Any]:
    """Name, prose, dependency names and commands from the fixed top-level files; broken manifests are skipped."""
    prose = "\n".join(_read(root / d) for d in DOCS)
    deps: list[str] = []
    commands: list[str] = []
    name = root.resolve().name
    try:
        pkg = json.loads(_read(root / "package.json") or "{}")
        name = pkg.get("name") or name
        for key in ("dependencies", "devDependencies"):
            deps += list(pkg.get(key, {}))
        commands += [f"npm run {s}" for s in pkg.get("scripts", {})]
    except (ValueError, AttributeError, TypeError):
        pass
    try:
        py = tomllib.loads(_read(root / "pyproject.toml"))
        project = py.get("project", {})
        name = project.get("name") or name
        specs = list(project.get("dependencies", []))
        for group in (*project.get("optional-dependencies", {}).values(), *py.get("dependency-groups", {}).values()):
            specs += group
        deps += [m[0] for s in specs if isinstance(s, str) and (m := DEP_NAME.match(s))]
        commands += list(project.get("scripts", {}))
    except (tomllib.TOMLDecodeError, AttributeError, TypeError):
        pass
    return {"name": str(name), "prose": prose, "deps": sorted(set(deps)), "commands": commands}


def _conventions(deps: list[str]) -> list[str]:
    have = {d.lower() for d in deps}
    table = (
        ("pytest", "Tests: pytest"),
        ("vitest", "Tests: vitest"),
        ("jest", "Tests: jest"),
        ("ruff", "Lint and format: ruff"),
        ("mypy", "Types: mypy"),
        ("typescript", "Language: TypeScript"),
        ("eslint", "Lint: eslint"),
        ("prettier", "Format: prettier"),
    )
    return [text for key, text in table if key in have]


def advise(project: dict[str, Any], items: list[Item], costs: dict[str, Any], assessments: dict[str, Any]) -> dict[str, Any]:
    """Ranked fits and noise for one project. `costs` and `assessments` are the saved scan's maps (either may be empty)."""
    pool = [i for i in items if i.kind in KINDS and not i.disabled]
    words = Counter(_words(project["prose"]))
    for dep in project["deps"]:
        for w in _words(dep.replace("@", " ").replace("/", " ")):
            words[w] += DEP_WEIGHT
    vectors = _tfidf([*_docs(pool), words])
    target = vectors[-1]
    rows: list[dict[str, Any]] = []
    for item, vec in zip(pool, vectors, strict=False):
        shared = sorted((w for w in vec if w in target), key=lambda w: (-vec[w] * target[w], w))[:3]
        cost = (costs.get(item.id) or {}).get("always_on")
        rows.append(
            {
                "id": item.id,
                "name": item.name,
                "kind": item.kind,
                "score": round(_cosine(vec, target), 3),
                "shared": shared,
                "always_on": cost,
            }
        )
    fits = sorted((r for r in rows if r["score"] >= MIN_SCORE), key=lambda r: (-r["score"], r["name"]))[:TOP]
    for r in fits:
        r["reason"] = "matches " + ", ".join(r["shared"])
    fit_ids = {r["id"] for r in fits}
    rest = [r for r in rows if r["id"] not in fit_ids]
    if assessments:
        flagged = [r for r in rest if (assessments.get(r["id"]) or {}).get("tier") in NOISE_TIERS]
        for r in flagged:
            r["reason"] = "no match here; scan verdict: " + str(assessments[r["id"]].get("label", "review")).lower()
    else:  # no verdicts: fall back to what costs tokens every session without matching
        flagged = [r for r in rest if r["always_on"]]
        for r in flagged:
            r["reason"] = "no match here and always on"
    noise = sorted(flagged, key=lambda r: (-(r["always_on"] or 0), r["name"]))[:NOISE_TOP]
    for r in (*fits, *noise):
        del r["id"], r["shared"]
    return {
        "project": project["name"],
        "fits": fits,
        "noise": noise,
        "always_on_fits": sum(r["always_on"] or 0 for r in fits),
        "draft": draft(project, fits),
    }


def draft(project: dict[str, Any], fits: list[dict[str, Any]]) -> str:
    """A tiny CLAUDE.md (well under 25 lines), redacted like everything else that is printed."""
    lines = [f"# {project['name']}", ""]
    if project["deps"]:
        lines.append("Stack: " + ", ".join(project["deps"][:8]))
    conventions = _conventions(project["deps"])
    if conventions:
        lines += ["Conventions:", *(f"- {c}" for c in conventions[:4])]
    if project["commands"]:
        lines += ["Commands:", *(f"- {c}" for c in project["commands"][:COMMANDS_IN_DRAFT])]
    if fits:
        lines += ["Skills worth using here:", *(f"- {r['name']}: {r['reason']}" for r in fits[:SKILLS_IN_DRAFT])]
    return redact("\n".join(lines)) + "\n"


def _row(r: dict[str, Any]) -> str:
    cost = f", {r['always_on']} tokens always on" if r["always_on"] else ""
    return f"  {r['name']} ({r['kind']}): {r['reason']}{cost}"


def render(result: dict[str, Any]) -> str:
    out = [f"Advice for {result['project']} (local words only; nothing sent)", "", "Installed Items that fit, best first:"]
    out += [_row(r) for r in result["fits"]] or ["  none matched"]
    out += ["", "Likely noise for this project:"]
    out += [_row(r) for r in result["noise"]] or ["  nothing flagged"]
    out += ["", "Draft CLAUDE.md (--write saves it as a new file):", *(f"  {line}" for line in result["draft"].splitlines())]
    return "\n".join(out)
