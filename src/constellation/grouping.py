"""Group Items into clusters and categories without a model. The similarity combines free local signals: word overlap (TF-IDF cosine
over name and description, plus embedding cosine when a local embedder ran), same plugin or origin, a shared name prefix such as
firecrawl-*, the same kind family and any non-"contains" relation. Items are merged agglomeratively (average linkage) under a size cap
so no cluster swallows the setup; tiny clusters fold into their nearest neighbour; each cluster is named from its most distinctive
words and filed under a coarse category. Pure and deterministic: sorted by id, ties broken by position."""

import math
import re
from collections import Counter
from collections.abc import Collection

from .cluster import dot
from .models import Cluster, Item, Relation

WORDS_ONLY_WARNING = "Clusters were built from words and plugin structure; install the local model for better groups: "
THRESHOLD = 0.15  # average-linkage similarity to merge; chosen on the invented eval in tests/eval/test_grouping_quality.py
LOOSE = 0.02  # a tiny cluster joins its closest neighbour at or above this; below it, up to UNASSIGNED of Items may stay alone
SAME_OWNER = 0.35  # bonus: both live in one plugin, or share an origin
SAME_PREFIX = 0.3  # bonus: names start with the same word, e.g. firecrawl-*
RELATED = 0.2  # bonus: joined by a relation other than "contains"
SAME_FAMILY = 0.03  # bonus: same kind family
EMBED_THRESHOLD = 0.35  # merge threshold when embeddings ran (bge cosines sit high, so the word-only 0.15 over-merges)
EMBED_WEIGHT = 0.4  # embedding cosine (clipped at 0) added to the word cosine when a local embedder ran
NAME_WEIGHT = 2  # a name word counts like this many description words
MAX_SHARE = 0.2  # no cluster may hold more than this share of the Items (but at least MIN_CAP)
MIN_CAP = 4
MIN_SIZE = 3  # smaller clusters fold into their nearest neighbour
UNASSIGNED = 0.05  # at most this share of Items may stay in no cluster (shown as Other)
OTHER = "Other"

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "use", "used", "using", "when", "are", "can", "will", "all",
    "any", "not", "into", "its", "has", "have", "how", "out", "skill", "skills", "claude", "code", "tool", "tools", "user", "files",
    "setup", "plugin", "bundle", "helper", "agent", "agents", "mcp", "server", "new", "more", "also", "than", "then", "each", "one",
}  # fmt: skip
# words that make a poor cluster name; only the naming step skips them (similarity still uses them)
FILLER = {
    "involve", "involves", "help", "helps", "task", "tasks", "work", "works", "keep", "keeps", "small", "lite", "mini", "pro", "two",
    "plus", "make", "makes", "get", "gets", "set", "run", "runs", "needs", "need", "want", "like", "thing", "things", "way",
    "good", "best", "well", "just", "some", "other", "about", "should", "would", "could", "which", "their", "there", "been", "was",
}  # fmt: skip
FILLER_SHARE = 0.8  # a word used by more than this share of the clusters (at least 4 of them) names none of them
_FAMILY = {"skill": "prompt", "command": "prompt", "agent": "prompt", "mcp_server": "server", "connector": "server"}
CATEGORIES = {
    "Design & UI": "design ui ux frontend css layout typography palette figma component shadcn tailwind visual animation style font brand",
    "Web & data fetching": "scrape crawl firecrawl search fetch web url extract http api data sitemap download research",
    "Writing & docs": "writing write docs documentation prose readme blog edit draft grammar slop essay dissertation latex paper",
    "Code review & testing": "review test tdd lint mutation coverage bug debug diagnose refactor quality audit security verify type",
    "Git & PRs": "git commit pr pull branch merge worktree rebase github issue changelog",
    "Notes & study": "obsidian note vault anki flashcard lecture study exam notebooklm revision",
    "Deploy & infra": "deploy vercel ci cicd docker infra env cloud release rollback cron build hosting",
    "Agents & orchestration": "agent subagent orchestrate plan planning workflow parallel brainstorm task gsd milestone phase superpowers",
    "Browser & automation": "browser click screenshot automation playwright chrome puppeteer computer",
}


def _words(text: str) -> list[str]:
    found = (
        w[:-1] if w.endswith("s") and not w.endswith(("ss", "us", "as", "is")) and len(w) > 4 else w
        for w in re.findall(r"[a-z0-9]+", text.lower())
    )
    return [w for w in found if (len(w) >= 3 or w in ("ai", "ui")) and w not in _STOP]


def _prefix(name: str) -> str | None:
    first = next(iter(_words(name)), None)
    return first if first and len(first) >= 4 else None


def _title(word: str) -> str:
    return word.upper() if word in ("ai", "ui", "ux", "pr", "ci") else word.capitalize()


def category_of(words: Counter[str]) -> str:
    """The category whose keywords the cluster's words hit most (a keyword of five or more letters also matches longer words)."""
    best, best_score = OTHER, 0
    for name, keys in CATEGORIES.items():
        wanted = keys.split()
        score = sum(c for w, c in words.items() if any(w == k or (len(k) >= 5 and w.startswith(k)) for k in wanted))
        if score > best_score:
            best, best_score = name, score
    return best


def _caps(n: int) -> tuple[int, int]:
    """(largest allowed cluster, fewest clusters to stop merging at)."""
    return max(MIN_CAP, int(MAX_SHARE * n)), math.ceil(math.sqrt(n) / 1.5)


def _key(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def _docs(items: list[Item]) -> list[Counter[str]]:
    """Name words (weighted) plus description words; a hook's description is a shell command, so only its name counts."""
    return [Counter({w: NAME_WEIGHT for w in _words(i.name)}) + Counter(_words("" if i.kind == "hook" else i.description)) for i in items]


def _tfidf(docs: list[Counter[str]]) -> list[dict[str, float]]:
    """Unit TF-IDF vectors; an empty document gets an empty vector."""
    n = len(docs)
    df = Counter(w for d in docs for w in d)
    out = []
    for d in docs:
        v = {w: c * (math.log((1 + n) / (1 + df[w])) + 1) for w, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values()))
        out.append({w: x / norm for w, x in v.items()})  # an empty document has norm 0 but nothing to divide
    return out


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def _similarities(
    items: list[Item], relations: list[Relation], tfidf: list[dict[str, float]], vectors: dict[str, list[float]] | None
) -> dict[tuple[int, int], float]:
    """Combined similarity of every pair (low index first): words, embedding cosine, same owner, name prefix, relation, kind family."""
    index = {i.id: k for k, i in enumerate(items)}
    owner = {r.target: r.source for r in relations if r.kind == "contains"}
    key = [owner.get(i.id) or (i.id if i.kind == "plugin" else i.origin) for i in items]
    prefix = [_prefix(i.name) for i in items]
    family = [_FAMILY.get(i.kind, i.kind) for i in items]
    related = {
        frozenset((index[r.source], index[r.target])) for r in relations if r.kind != "contains" and r.source in index and r.target in index
    }

    def sim(a: int, b: int) -> float:
        score = _cosine(tfidf[a], tfidf[b])
        if vectors:
            score += EMBED_WEIGHT * max(0.0, dot(vectors[items[a].id], vectors[items[b].id]))
        score += SAME_OWNER * (key[a] is not None and key[a] == key[b]) + SAME_PREFIX * (prefix[a] is not None and prefix[a] == prefix[b])
        return score + RELATED * (frozenset((a, b)) in related) + SAME_FAMILY * (family[a] == family[b])

    return {(a, b): sim(a, b) for a in range(len(items)) for b in range(a + 1, len(items))}


def _agglomerate(base: dict[tuple[int, int], float], n: int, threshold: float) -> list[list[int]]:
    """Average-linkage merging of n points under a size cap, then tiny clusters fold into their nearest neighbour. Returns sorted
    member lists in order of first member; up to UNASSIGNED of the points may be left in no cluster."""
    cap, lo = _caps(n)
    min_size = MIN_SIZE if n >= 3 * MIN_SIZE else 1  # a handful of Items cannot all be in threes
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    link = dict(base)  # average linkage between live clusters, keyed (low, high)

    def merge(a: int, b: int) -> None:  # b folds into a
        for c in members:
            if c not in (a, b):
                ka, kb = _key(a, c), _key(b, c)
                link[ka] = (link[ka] * len(members[a]) + link.pop(kb) * len(members[b])) / (len(members[a]) + len(members[b]))
        link.pop((a, b))
        members[a] += members.pop(b)

    def best_pair(of: int | None = None) -> tuple[tuple[int, int], float] | None:
        fits = [(k, v) for k, v in link.items() if len(members[k[0]]) + len(members[k[1]]) <= cap and (of is None or of in k)]
        return min(fits, key=lambda kv: (-kv[1], kv[0]), default=None)  # best similarity, then the lowest pair

    while len(members) > lo:
        top = best_pair()
        if top is None or top[1] < threshold:
            break
        merge(*top[0])
    outside = 0
    while (small := min((c for c in members if len(members[c]) < min_size), default=None)) is not None:
        top = best_pair(small)
        if top is None or (top[1] < LOOSE and outside + len(members[small]) <= int(UNASSIGNED * n)):
            outside += len(members.pop(small))  # in no cluster: shown as Other
            for k in [k for k in link if small in k]:
                del link[k]
        else:
            merge(*sorted(top[0]))
    return [sorted(m) for m in members.values()]  # cluster keys stay the lowest member, so this is already in order of first member


def group_items(
    items: list[Item],
    relations: list[Relation],
    labels: dict[str, str],
    vectors: dict[str, list[float]] | None = None,
    threshold: float | None = None,
) -> list[Cluster]:
    items = sorted(items, key=lambda i: i.id)
    if not items:
        return []
    docs = _docs(items)
    base = _similarities(items, relations, _tfidf(docs), vectors)
    groups = _agglomerate(base, len(items), (EMBED_THRESHOLD if vectors else THRESHOLD) if threshold is None else threshold)
    return _name(items, groups, docs, relations, base, labels)


def _central(group: list[int], base: dict[tuple[int, int], float]) -> int:
    """The member most similar to the rest (the lowest index on a tie)."""
    return max(group, key=lambda a: (sum(base[_key(a, b)] for b in group if b != a), -a))


def _bigram(group: list[int], items: list[Item], banned: set[str]) -> str | None:
    """The adjacent word pair, from item names, that at least half the members share (e.g. 'sort tally'); commonest, then alphabetical."""
    names = [_words(items[a].name) for a in group]
    pairs = Counter(p for w in names for p in set(zip(w, w[1:], strict=False)) if p[0] not in banned and p[1] not in banned)
    best = min(pairs, key=lambda p: (-pairs[p], p), default=None)
    return f"{_title(best[0])} {_title(best[1])}" if best and len(group) >= 3 and pairs[best] * 2 >= len(group) else None


def _distinctive(group: list[int], docs: list[Counter[str]], spread: Counter[str], k: int, banned: Collection[str] = ()) -> list[str]:
    """Words of the group ranked by how often its members use them, discounted by how many of the k groups use them at all.
    A word must be in at least two members (one, for a group of one); banned filler words never qualify unless nothing else does."""
    words = Counter(w for a in group for w in docs[a])
    if any(w not in banned for w in words):
        words = Counter({w: c for w, c in words.items() if w not in banned})
    score = {
        w: sum(docs[a][w] for a in group) * (math.log((1 + k) / (1 + spread[w])) + 1)  # a constant factor of len(group) cannot reorder
        for w, c in words.items()
        if c >= min(2, len(group))
    }
    return sorted(score, key=lambda w: (-score[w], w))


def _unique(name: str, extra: list[str], used: set[str]) -> str:
    """The name with spare distinctive words appended until no earlier cluster has it, then a number."""
    spare = iter(extra)
    while name in used:
        more = next(spare, None)
        name = f"{name} {_title(more)}" if more else f"{name} {sum(u.startswith(name) for u in used) + 1}"
    return name


def _name(
    items: list[Item],
    groups: list[list[int]],
    docs: list[Counter[str]],
    relations: list[Relation],
    base: dict[tuple[int, int], float],
    labels: dict[str, str],
) -> list[Cluster]:
    """Name each group (a model label if a member has one, else its plugin and most distinctive words), file it under a category,
    and return the clusters ordered by their first member."""
    spread = Counter(w for g in groups for w in {w for a in g for w in docs[a]})
    banned = FILLER | {w for w, c in spread.items() if len(groups) >= 6 and c >= 4 and c > FILLER_SHARE * len(groups)}
    owner = {r.target: r.source for r in relations if r.kind == "contains"}
    plugin_name = {i.id: i.name for i in items if i.kind == "plugin"}
    clusters: list[Cluster] = []
    used: set[str] = set()
    for g in sorted(groups, key=lambda g: (-len(g), g[0])):  # bigger groups claim a name first
        centre = _central(g, base)
        terms = _distinctive(g, docs, spread, len(groups), banned)
        shared = {owner.get(items[a].id, items[a].id) for a in g}  # the plugin holding each member (a plugin or a loner: itself)
        plugin = plugin_name.get(next(iter(shared)), "") if len(shared) == 1 else ""  # one plugin holds the whole cluster
        head = [w.capitalize() for w in re.split(r"[-_ .:/]+", plugin) if w]
        terms = [w for w in terms if _title(w) not in head]
        chosen = next((labels[items[a].id] for a in sorted(g, key=lambda a: a != centre) if items[a].id in labels), None)
        pair = None if head else _bigram(g, items, banned)
        name = chosen or pair or " ".join(head + [_title(w) for w in terms[: 1 if head else 2]]) or items[centre].name
        name = _unique(name, terms[1 if head else 2 :], used)
        used.add(name)
        category = category_of(Counter({w: c for a in g for w, c in docs[a].items()}))
        clusters.append(Cluster(name, tuple(items[a].id for a in g), category))
    return sorted(clusters, key=lambda c: c.item_ids)
