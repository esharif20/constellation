"""The one local retrieval backend, shared by chat and /api/search. Nothing here is sent anywhere (privacy invariant unchanged).

Exact, joined/hyphenated and typo-tolerant name matching (same behaviour as frontend/src/graph/search.ts), SQLite FTS5 (word and
trigram) over name/description/kind, and meaning-based vectors from the local embedder, fused with reciprocal-rank fusion."""

import hashlib
import json
import os
import re
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .cluster import _unit, dot
from .embeddings import MODEL
from .models import Embedder
from .redact import redact

DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "embeddings.json"
MAX_QUERY = 200
LIMIT = 8
RRF_K = 60
SIMILAR = 0.65  # raw bge-small cosine: unrelated Items sit at 0.5-0.65, matches above it; picked on tests/eval/test_search_quality.py
SPREAD = 0.03  # keep only hits this close to the best one, so one real match is not buried in weaker lookalikes
_FILLER = set("where is are the my find show me a an of to for do i which what skill skills plugin plugins agent agents hook hooks".split())


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def tokens(query: str) -> list[str]:
    """Query words; filler words go only when something else remains."""
    everything = _words(query)
    return [w for w in everything if w not in _FILLER] or everything


def _near(a: str, b: str) -> bool:
    """Within one edit (substitution, insertion, deletion or adjacent swap)."""
    i = len(os.path.commonprefix([a, b]))
    x, y = a[i:], b[i:]
    return a == b or x[1:] == y[1:] or x[1:] == y or x == y[1:] or (x[:2] == y[1::-1] and x[2:] == y[2:])


def _subsequence(q: str, s: str) -> bool:
    it = iter(s)
    return all(c in it for c in q)


def _tier(item: dict[str, Any], toks: list[str], joined: str) -> tuple[int, str] | None:
    """0 exact name, 1 name prefix, 2 name contains, 3 every token in name/description/kind, 4 typo, 5 letters of the name."""
    name_words = _words(item["name"])
    name = "".join(name_words)
    if name == joined:
        return 0, "name"
    if name.startswith(joined):
        return 1, "name starts with it"
    if joined in name:
        return 2, "name"
    # pragma: no mutate (the separators below cannot matter: tokens are lowercase letters and digits)
    name_hay = f" {' '.join(name_words)} "  # pragma: no mutate
    hay = f"{name_hay}{' '.join(_words(item['description']))} {' '.join(_words(item['kind']))} "  # pragma: no mutate
    if all(t in hay for t in toks):
        return 3, "name" if all(t in name_hay for t in toks) else "in description"
    for q in (joined, *toks):
        if len(q) >= 5 and any(_near(q, c) for c in (name, *name_words)):
            return 4, f'close to "{item["name"]}"'
    if len(joined) >= 3 and _subsequence(joined, name):
        return 5, f'letters of "{item["name"]}"'
    return None


def _match(toks: Sequence[str]) -> str:
    return " OR ".join('"' + t + '"' for t in toks)  # quoted, so user text is never FTS syntax


def _rrf(rankings: list[list[str]]) -> dict[str, float]:
    """Reciprocal-rank fusion: an Item scores 1 / (k + rank) in every list that has it."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for rank, id_ in enumerate(ranking):
            score[id_] = score.get(id_, 0.0) + 1 / (RRF_K + rank + 1)
    return score


def _write_private(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # pragma: no mutate (equivalent: chmod follows)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(text)
    path.chmod(0o600)


DROPPED = "Some saved search vectors did not match the local embedder and were rebuilt."


def _is_vector(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, int | float) and not isinstance(x, bool) for x in v)


def _key(text: str) -> str:
    return hashlib.sha256(f"{MODEL}\n{text}".encode()).hexdigest()


class Index:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.note: str | None = None  # why meaning-based search is off, when it is
        self.vectors: dict[str, list[float]] | None = None
        self._embed: Embedder | None = None  # pragma: no mutate (equivalent: guarded together with vectors)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(":memory:", check_same_thread=False)  # pragma: no mutate (equivalent: None is falsy)
        rows = [(i["id"], i["name"], i["description"], i["kind"]) for i in items]
        for table, tokenizer in (("words", "porter"), ("trigrams", "trigram")):  # pragma: no mutate (SQL names are case-insensitive)
            columns = "id UNINDEXED, name, description, kind"  # pragma: no mutate
            self._connection.execute(f"CREATE VIRTUAL TABLE {table} USING fts5({columns}, tokenize='{tokenizer}')")  # pragma: no mutate
            self._connection.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?)", rows)  # pragma: no mutate

    def close(self) -> None:
        self._connection.close()

    def fts(self, toks: Sequence[str], limit: int = LIMIT, trigram: bool = False) -> list[str]:
        table = "trigrams" if trigram else "words"  # pragma: no mutate (SQL names are case-insensitive)
        if not toks:
            return []
        with self._lock:
            rows = self._connection.execute(
                f"SELECT id FROM {table} WHERE {table} MATCH ? ORDER BY bm25({table}), id LIMIT ?",  # pragma: no mutate
                (_match(toks), limit),
            ).fetchall()
        return [row[0] for row in rows]

    def add_vectors(self, embed: Embedder, cache: Path | None = None) -> None:
        """Embed redacted name and description once, reusing the 0600 cache keyed by the hash of that text. Run in a thread."""
        try:
            texts = {i["id"]: redact(i["name"] if i["kind"] == "hook" else f"{i['name']}: {i['description']}") for i in self.items}
            stored: dict[str, list[float]] = {}
            if cache is not None:
                try:
                    loaded = json.loads(cache.read_text())
                    stored = loaded if isinstance(loaded, dict) else {}
                except (OSError, ValueError):
                    pass
            keys = {t: _key(t) for t in texts.values()}
            usable = {k: v for k, v in stored.items() if _is_vector(v)}
            missing = sorted(t for t, k in keys.items() if k not in usable)
            probe = embed(missing or sorted(keys)[:1])  # with nothing missing, one cached text still tells the embedder's dimension
            dim = len(probe[0])
            bad = {t for t, k in keys.items() if k in usable and len(usable[k]) != dim}
            todo = missing + sorted(bad)
            vectors = probe if missing else []
            if bad:
                vectors = [*vectors, *embed(sorted(bad))]
            fresh = {t: _unit(v) for t, v in zip(todo, vectors, strict=True)}
            if {len(v) for v in fresh.values()} - {dim}:
                raise ValueError  # pragma: no mutate (the message is swallowed below)
            # entries of another size or model are dropped, never mixed in; the file is rewritten whole so it stays one dimension
            dropped = bool(bad) or any(k in stored and k not in usable for k in keys.values())
            if dropped:
                self.note = DROPPED
            if missing or dropped:
                stored = {keys[t]: usable[keys[t]] for t in keys if keys[t] in usable and t not in bad}
                stored.update({keys[t]: v for t, v in fresh.items()})
                if cache is not None:
                    try:
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        _write_private(cache, json.dumps(stored))
                    except OSError:
                        self.note = "The search vector cache could not be written; meaning-based search still works."
            else:
                stored = usable
            self._embed = embed
            self.vectors = {id_: stored[_key(t)] for id_, t in texts.items()}
        except Exception:  # noqa: BLE001 - a missing or blocked embedder must only switch meaning-based search off
            self.note = "Meaning-based search is off (local embedder unavailable); word search still works."

    def _similar(self, query: str) -> list[tuple[str, float]]:
        if self.vectors is None or self._embed is None:  # pragma: no mutate (equivalent: both are set together)
            return []
        with self._lock:
            vector = _unit(self._embed([redact(query)])[0])
        scored = sorted(((dot(vector, v), id_) for id_, v in self.vectors.items()), key=lambda s: (-s[0], s[1]))
        return [(id_, s) for s, id_ in scored if s >= SIMILAR and s >= scored[0][0] - SPREAD][:LIMIT]

    def query(self, text: str, limit: int = LIMIT) -> list[dict[str, str]]:
        """Ranked `{id, why}` hits; ids are existing Item ids."""
        text = redact(text[:MAX_QUERY])
        toks = tokens(text)
        if not toks:
            return []
        joined = "".join(toks)
        tiers = sorted((t, item["name"], item["id"], why) for item in self.items if (r := _tier(item, toks, joined)) for t, why in [r])
        similar = self._similar(text)
        whys: dict[str, str] = {id_: why for _, _, id_, why in tiers}
        by_id = {i["id"]: i for i in self.items}
        words, grams = self.fts(toks), self.fts(toks, trigram=True)
        for id_ in [*words, *grams]:
            item = by_id[id_]
            whys.setdefault(id_, "name" if any(t in _words(item["name"]) for t in toks) else "in description")
        for id_, _ in similar:
            whys.setdefault(id_, "similar meaning")
        score = _rrf([[t[2] for t in tiers], words, grams, [s[0] for s in similar]])
        exact = {t[2] for t in tiers if t[0] == 0}  # an exact name is always first
        ranked = sorted(score, key=lambda id_: (id_ not in exact, -score[id_], by_id[id_]["name"], id_))
        return [{"id": id_, "why": whys[id_]} for id_ in ranked[:limit]]
