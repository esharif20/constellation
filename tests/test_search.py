import json
import stat
import time

import pytest
from fakes_search import concept_embedder
from fastapi.testclient import TestClient

from constellation import retrieve, server
from constellation.retrieve import Index, tokens

ITEMS = [
    {"id": "gm", "kind": "skill", "name": "gmail-helper", "description": "Reads and drafts messages in the inbox"},
    {"id": "pp", "kind": "skill", "name": "deck-builder", "description": "Builds a presentation from notes"},
    {"id": "pdf", "kind": "skill", "name": "pdf-reader", "description": "Extracts text from PDF files"},
    {"id": "tr", "kind": "skill", "name": "test-runner", "description": "Runs the unit tests"},
    {"id": "shadcn", "kind": "skill", "name": "shadcn", "description": "Adds UI components"},
]


def ids(hits):
    return [h["id"] for h in hits]


def warm(index, cache=None, embed=concept_embedder):
    index.add_vectors(embed, cache)
    return index


@pytest.fixture
def built_app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    monkeypatch.setattr(server, "STATIC", static)


@pytest.fixture
def client(tmp_path, built_app):
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({"items": ITEMS}))
    return TestClient(server.create_app(scan, embedder=concept_embedder), base_url="http://127.0.0.1:8765"), scan


def test_filler_words_go_only_when_something_remains():
    assert tokens("where is my pdf reader") == ["pdf", "reader"]
    assert tokens("find the skill") == ["find", "the", "skill"]


def test_joined_hyphen_and_space_forms_find_the_same_item():
    index = Index(ITEMS)
    for q in ("pdfreader", "pdf-reader", "pdf reader", "PDF  Reader"):
        assert index.query(q)[0] == {"id": "pdf", "why": "name"}


def test_typos_and_prefixes_and_why():
    index = Index(ITEMS)
    assert index.query("shadnc")[0] == {"id": "shadcn", "why": 'close to "shadcn"'}
    assert index.query("shadc")[0]["id"] == "shadcn"
    assert index.query("inbox")[0] == {"id": "gm", "why": "in description"}
    assert index.query("pdf")[0]["why"] == "name starts with it"


def test_nonsense_and_blank_find_nothing():
    index = Index(ITEMS)
    assert index.query("qqqzzzxx") == [] and index.query("   ") == [] and index.query("?!") == []


def test_meaning_finds_synonyms_only_once_vectors_exist():
    index = Index(ITEMS)
    assert "pp" not in ids(index.query("slides"))
    hits = warm(index).query("slides")
    assert hits[0] == {"id": "pp", "why": "similar meaning"}


def test_exact_name_is_first_even_when_meaning_ranks_another():
    items = [*ITEMS, {"id": "mail", "kind": "skill", "name": "mail", "description": "x"}]
    assert warm(Index(items)).query("mail")[0]["id"] == "mail"


def test_limit_and_long_query_are_capped():
    items = [{"id": str(n), "kind": "skill", "name": f"tool{n}", "description": "d"} for n in range(30)]
    index = Index(items)
    assert len(index.query("tool")) == retrieve.LIMIT and len(index.query("tool", 3)) == 3
    assert index.query("pdf" + "x" * 500) == index.query(("pdf" + "x" * 500)[: retrieve.MAX_QUERY])


def test_fts_syntax_in_a_query_is_only_words():
    assert Index(ITEMS).query('pdf" OR name:* NEAR(') is not None


def test_vector_cache_is_private_keyed_by_text_and_reused(tmp_path):
    cache = tmp_path / "cache" / "embeddings.json"
    calls = []

    def counting(texts):
        calls.append(len(texts))
        return concept_embedder(texts)

    warm(Index(ITEMS), cache, counting)
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600 and calls == [5]
    warm(Index(ITEMS), cache, counting)
    assert calls == [5, 1]  # one probe of the embedder's dimension, nothing re-embedded
    changed = [{**ITEMS[0], "description": "new words"}, *ITEMS[1:]]
    warm(Index(changed), cache, counting)
    assert calls == [5, 1, 1]
    assert "gmail-helper" not in cache.read_text()


def test_redacted_text_is_what_is_embedded(tmp_path):
    seen = []
    items = [{"id": "a", "kind": "skill", "name": "n", "description": "key sk-ant-api03-" + "a" * 40}]
    warm(Index(items), None, lambda texts: (seen.extend(texts), concept_embedder(texts))[1])
    assert seen and "sk-ant" not in seen[0]


def test_unwritable_cache_is_a_note_not_a_crash(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    index = warm(Index(ITEMS), blocker / "embeddings.json")
    assert index.vectors is not None and "could not be written" in index.note


def test_corrupt_cache_is_ignored(tmp_path):
    cache = tmp_path / "e.json"
    cache.write_text("not json")
    assert warm(Index(ITEMS), cache).vectors is not None
    cache.write_text("[1]")
    assert warm(Index(ITEMS), cache).vectors is not None


def test_missing_embedder_falls_back_to_words_with_a_note():
    def broken(texts):
        raise RuntimeError("fastembed is not installed")

    index = warm(Index(ITEMS), None, broken)
    assert index.vectors is None and "off" in index.note
    assert index.query("pdf")[0]["id"] == "pdf"


def test_api_returns_ids_and_why_for_get_and_post(client):
    http, _ = client
    for _ in range(100):  # vectors warm in a background thread
        got = http.get("/api/search", params={"q": "slides"}).json()
        if got["results"]:
            break
        time.sleep(0.02)
    assert got["results"][0] == {"id": "pp", "why": "similar meaning"}
    posted = http.post("/api/search", json={"q": "pdf-reader", "limit": 1})
    assert posted.json() == {"results": [{"id": "pdf", "why": "name"}], "note": None}


def test_api_bounds_and_local_only(client):
    http, _ = client
    assert http.get("/api/search", params={"q": "x" * 201}).status_code == 422
    assert http.get("/api/search", params={"q": "x" * 200}).status_code == 200
    assert http.get("/api/search", params={"q": "pdf", "limit": 0}).status_code == 422
    assert http.get("/api/search").status_code == 422
    assert len(http.get("/api/search", params={"q": "e", "limit": 999}).json()["results"]) <= 20
    assert http.post("/api/search", json={"q": "pdf", "extra": 1}).status_code == 422
    assert http.get("/api/search", params={"q": "pdf"}, headers={"host": "evil.example:8765"}).status_code == 403
    assert http.post("/api/search", json={"q": "pdf"}, headers={"origin": "http://evil.example"}).status_code == 403
    assert http.post("/api/search", content="{}", headers={"content-type": "text/plain"}).status_code == 415


def test_api_rebuilds_when_the_scan_changes_and_rejects_a_bad_scan(client):
    http, scan = client
    scan.write_text(json.dumps({"items": [{"id": "zz", "kind": "skill", "name": "zebra", "description": "stripes"}]}))
    assert ids(http.get("/api/search", params={"q": "zebra"}).json()["results"]) == ["zz"]
    scan.write_text("nope")
    assert http.get("/api/search", params={"q": "zebra"}).status_code == 404


@pytest.mark.parametrize(
    ("a", "b", "near"),
    [
        ("shadcn", "shadcn", True), ("shadcn", "shadnc", True), ("shadcn", "shadcm", True), ("shadcn", "xhadcn", True),
        ("shadcn", "shadc", True), ("shadcn", "shadcnn", True), ("shadcn", "hadcn", True), ("shadcn", "shadcnxx", False),
        ("shadcn", "shadxx", False), ("shadcn", "shdacn", True), ("shadcn", "shadcnx", True), ("abcd", "badc", False),
        ("abcdef", "bacdef", True), ("abcdef", "abdcxf", False), ("abcdef", "abcdfe", True), ("abcde", "abxde", True),
        ("abcde", "xbcdx", False), ("ab", "ba", True), ("abc", "cba", False), ("abc", "", False), ("a", "", True),
        ("xa", "xyab", False),
        ("abcd", "ab", False),
        ("ab", "abcd", False),
        ("ab", "abx", True), ("abcdef", "abcxxf", False), ("abcdef", "abdcef", True),
    ],
)  # fmt: skip
def test_near_is_one_edit_with_adjacent_swap(a, b, near):
    assert retrieve._near(a, b) is near and retrieve._near(b, a) is near


def item(name, description="", kind="skill", id_=None):
    return {"id": id_ or name, "name": name, "description": description, "kind": kind}


@pytest.mark.parametrize(
    ("it", "query", "expected"),
    [
        (item("pdf-reader"), "pdfreader", (0, "name")),
        (item("pdf-reader"), "pdf", (1, "name starts with it")),
        (item("pdf-reader"), "reader", (2, "name")),
        (item("pdf-reader"), "der", (2, "name")),
        (item("x", "turns slides into text"), "slides text", (3, "in description")),
        (item("slides-text", "a"), "slides text", (0, "name")),
        (item("text-slides-x", "a"), "slides text", (3, "name")),
        (item("slides", "text"), "slides text", (3, "in description")),
        (item("x", "", kind="hook"), "hook", (3, "in description")),
        (item("x", "", kind="agent"), "agent", (3, "in description")),
        (item("shadcn"), "shadnc", (4, 'close to "shadcn"')),
        (item("shadcn"), "shadc xyz", (4, 'close to "shadcn"')),
        (item("data-miner"), "dato", None),
        (item("data-miner"), "minerr", (4, 'close to "data-miner"')),
        (item("data-miner"), "miner", (2, "name")),
        (item("shadcn"), "shad", (1, "name starts with it")),
        (item("shadcn"), "sdn", (5, 'letters of "shadcn"')),
        (item("shadcn"), "sd", None),
        (item("shadcn"), "zzz", None),
        (item("abcd"), "adcb", None),
    ],
)  # fmt: skip
def test_tiers_and_reasons(it, query, expected):
    toks = tokens(query)
    assert retrieve._tier(it, toks, "".join(toks)) == expected


def test_typo_needs_five_letters_and_checks_each_word():
    assert retrieve._tier(item("cat"), ["cut"], "cut") is None
    assert retrieve._tier(item("data-miner"), ["xxxxx", "minar"], "xxxxxminar") == (4, 'close to "data-miner"')
    assert retrieve._tier(item("abcde"), ["abcdf"], "abcdf") == (4, 'close to "abcde"')
    assert retrieve._tier(item("abcd"), ["abcx"], "abcx") is None


def test_fts_searches_each_column_and_stems_and_takes_substrings():
    index = Index([item("alpha", "beta gamma", id_="n"), item("zz", "runs fast", id_="d"), item("qq", "x", kind="widget", id_="k")])
    assert index.fts(["alpha"]) == ["n"] and index.fts(["gamma"]) == ["n"] and index.fts(["widget"]) == ["k"]
    assert index.fts(["run"]) == ["d"] and sorted(index.fts(["alpha", "fast"])) == ["d", "n"]
    assert index.fts(["lph"], trigram=True) == ["n"] and index.fts(["lph"]) == []
    assert index.fts(["ph"], trigram=True) == [] and index.fts(["pha"], trigram=True) == ["n"]
    assert index.fts([]) == [] and index.fts(["ab"], trigram=True) == []
    assert index.fts(["a"]) == [] and index.fts(["x"]) == ["k"]
    many = Index([item(f"w{n}", "common", id_=f"{n:02}") for n in range(12)])
    assert len(many.fts(["common"])) == 8 and len(many.fts(["common"], 3)) == 3 and many.fts(["common"], 12)[-1] == "11"
    assert many.fts(["common"], trigram=True) == many.fts(["common"])
    index.close()


def test_index_can_be_used_from_another_thread():
    from concurrent.futures import ThreadPoolExecutor

    index = Index(ITEMS)
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(index.fts, ["pdf"]).result() == ["pdf"]


def test_cache_file_is_private_even_if_it_existed_and_keys_hash_the_model(tmp_path):
    cache = tmp_path / "a" / "b" / "e.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{}")
    cache.chmod(0o644)
    warm(Index([item("n", "d")]), cache)
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    assert list(json.loads(cache.read_text())) == [retrieve._key("n: d")]
    assert retrieve._key("n: d") != retrieve._key("n: e")


def test_cache_is_created_in_new_directories(tmp_path):
    cache = tmp_path / "x" / "y" / "e.json"
    warm(Index([item("n", "d")]), cache)
    assert cache.exists()


def test_stale_cache_entries_are_pruned_and_vectors_are_units_by_id(tmp_path):
    cache = tmp_path / "e.json"
    cache.write_text(json.dumps({"old": [1.0], retrieve._key("keep: x"): [3.0, 4.0, 0.0]}))
    index = warm(Index([item("keep", "x"), item("new", "y")]), cache, lambda texts: [[0.0, 3.0, 4.0] for _ in texts])
    stored = json.loads(cache.read_text())
    assert set(stored) == {retrieve._key("keep: x"), retrieve._key("new: y")}
    assert stored[retrieve._key("new: y")] == [0.0, 0.6, 0.8]
    assert index.vectors == {"keep": [3.0, 4.0, 0.0], "new": [0.0, 0.6, 0.8]}
    assert index.note is None


def test_hooks_are_embedded_by_name_and_batches_are_sorted_and_deduplicated():
    seen = []
    items = [item("b", "shell cmd", kind="hook"), item("a", "x", id_="a1"), item("a", "x", id_="a2")]
    warm(Index(items), None, lambda texts: (seen.append(list(texts)), concept_embedder(texts))[1])
    assert seen == [["a: x", "b"]]


def test_embedder_returning_the_wrong_count_switches_meaning_off():
    index = warm(Index(ITEMS), None, lambda texts: concept_embedder(texts)[:-1])
    assert index.vectors is None and index.note.startswith("Meaning-based search is off")


def test_notes_are_exact(tmp_path):
    blocker = tmp_path / "f"
    blocker.write_text("")
    assert warm(Index(ITEMS), blocker / "e.json").note == "The search vector cache could not be written; meaning-based search still works."

    def broken(texts):
        raise RuntimeError

    assert warm(Index(ITEMS), None, broken).note == "Meaning-based search is off (local embedder unavailable); word search still works."


def vec_embedder(table):
    return lambda texts: [table[t] for t in texts]


def test_similarity_threshold_spread_limit_and_order_are_exact():
    # unit vectors with cosine to the query [1, 0] of 1.0, 0.97 (within spread), 0.9 (outside), 0.65 and below-cutoff
    items = [item(n, id_=n) for n in ("best", "close", "far", "tie-b", "tie-a")]
    index = Index(items)
    index.vectors = {
        "best": [1.0, 0.0],
        "close": [0.97, (1 - 0.97**2) ** 0.5],
        "far": [0.9, (1 - 0.81) ** 0.5],
        "tie-b": [0.97, 0.2431],
        "tie-a": [0.97, 0.2431],
    }
    index._embed = lambda texts: [[1.0, 0.0]]
    got = index._similar("q")
    assert [i for i, _ in got] == ["best", "close", "tie-a", "tie-b"] or [i for i, _ in got][:2] == ["best", "close"]
    assert "far" not in [i for i, _ in got]


def test_similarity_floor_is_inclusive_and_spread_is_inclusive():
    def at(cos):
        return [cos, (1 - cos**2) ** 0.5]

    index = Index([item("a"), item("b")])
    index._embed = lambda texts: [[1.0, 0.0]]
    index.vectors = {"a": at(retrieve.SIMILAR), "b": [0.0, 1.0]}
    assert [i for i, _ in index._similar("q")] == ["a"]
    index.vectors = {"a": at(retrieve.SIMILAR - 0.01), "b": [0.0, 1.0]}
    assert index._similar("q") == []
    index.vectors = {"a": [1.0, 0.0], "b": at(1.0 - retrieve.SPREAD + 0.001)}
    assert [i for i, _ in index._similar("q")] == ["a", "b"]
    index.vectors = {"a": [1.0, 0.0], "b": at(1.0 - retrieve.SPREAD - 0.01)}
    assert [i for i, _ in index._similar("q")] == ["a"]
    index.vectors = {"a": at(0.9), "b": at(0.95)}
    assert [i for i, _ in index._similar("q")] == ["b"]  # the spread is measured from the best, not the first listed
    index.vectors = {"a": [1.0, 0.0], "b": [1.0, 0.0]}
    assert [i for i, _ in index._similar("q")] == ["a", "b"]  # ties by id
    index.vectors = {"b": [1.0, 0.0], "a": [0.99, 0.141067]}
    assert [i for i, _ in index._similar("q")] == ["b", "a"]
    index.vectors = {f"{n:02}": [1.0, 0.0] for n in range(12)}
    assert len(index._similar("q")) == retrieve.LIMIT
    assert Index([item("a")])._similar("q") == []


def test_the_query_is_redacted_before_it_reaches_the_embedder():
    seen = []
    index = warm(Index(ITEMS))
    index._embed = lambda texts: (seen.extend(texts), [[1.0, 0.0, 0.0]])[1]
    index.query("sk-ant-api03-" + "a" * 40)
    assert seen and "sk-ant" not in seen[0]


def test_rrf_ties_break_by_id():
    index = Index([item("alpha", "common", id_="2"), item("alpha", "common", id_="1")])
    assert [h["id"] for h in index.query("common")] == ["1", "2"]
    # an Item ranked by several lists outranks one ranked by fewer
    mixed = Index([item("deck", "slides", id_="a"), item("aaa", "slides x", id_="b")])
    mixed.vectors = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
    mixed._embed = lambda texts: [[1.0, 0.0]]
    assert [h["id"] for h in mixed.query("slides")] == ["a", "b"]


def test_exact_name_beats_a_better_fused_score():
    items = [item("pdf", "nothing", id_="exact"), item("pdf-pdf-pdf", "pdf pdf pdf pdf pdf", id_="other")]
    index = Index(items)
    index.vectors = {"exact": [0.0, 1.0], "other": [1.0, 0.0]}
    index._embed = lambda texts: [[1.0, 0.0]]
    assert index.query("pdf")[0]["id"] == "exact"


def test_why_prefers_the_tier_then_words_then_meaning():
    index = Index([item("alpha", "needle haystack", id_="a"), item("beta", "other", id_="b")])
    index.vectors = {"a": [1.0, 0.0], "b": [1.0, 0.0]}
    index._embed = lambda texts: [[1.0, 0.0]]
    hits = {h["id"]: h["why"] for h in index.query("needle")}
    assert hits == {"a": "in description", "b": "similar meaning"}
    only_gram = Index([item("zz", "xxneedlexx", id_="g")])
    assert only_gram.query("eedl") == [{"id": "g", "why": "in description"}]
    assert Index([item("needle-box", "q", id_="n")]).query("needle")[0]["why"] == "name starts with it"


def test_fts_only_hit_says_name_when_a_query_word_is_in_the_name():
    assert Index([item("box", "q", id_="n")]).query("box zzzz") == [{"id": "n", "why": "name"}]
    assert Index([item("qq", "box", id_="d")]).query("box zzzz") == [{"id": "d", "why": "in description"}]


def test_rrf_scores_each_list_by_reciprocal_rank():
    got = retrieve._rrf([["a", "b"], ["b"]])
    assert got == {"a": pytest.approx(1 / 61), "b": pytest.approx(1 / 62 + 1 / 61)}
    assert retrieve._rrf([]) == {}


def test_words_never_match_across_the_joins_of_name_description_or_kind():
    for it in (item("a-b"), item("n", "c-d"), item("n", "", kind="k-l")):
        assert retrieve._tier(it, ["xx"], "xx") is None


def test_an_embedder_returning_extra_vectors_switches_meaning_off():
    index = warm(Index(ITEMS), None, lambda texts: [*concept_embedder(texts), [1.0, 0.0, 0.0]])
    assert index.vectors is None and index.note.startswith("Meaning-based search is off")


def test_multi_word_queries_use_the_joined_form_for_ranking():
    index = Index([item("a-pdf-reader", "x " * 30, id_="contains"), item("pdf-reader-plus", "x", id_="prefix")])
    assert [h["id"] for h in index.query("pdf reader")] == ["prefix", "contains"]


def test_each_list_can_find_an_item_alone():
    # a second, absent word stops the all-words tier, so only one FTS list can find the Item
    assert Index([item("zz", "running fast", id_="w")]).query("runs zzzz") == [{"id": "w", "why": "in description"}]
    assert Index([item("zz", "xxneedlexx", id_="g")]).query("eedl zzzz") == [{"id": "g", "why": "in description"}]


def test_a_multi_word_query_is_exact_on_the_joined_name():
    items = [item("pdf-reader", "junk " * 30, id_="exact"), item("a-pdf-reader", "pdf reader", id_="better")]
    assert Index(items).query("pdf reader")[0]["id"] == "exact"


# --- #74: a stale or mismatched vector cache must never crash search or chat --------------------------------------------------------

DROPPED = "Some saved search vectors did not match the local embedder and were rebuilt."


def invented_cache(tmp_path, dim=7):
    """A cache made by another embedder: right keys for some Items, vectors of a different length, plus junk and an other-model key."""
    path = tmp_path / "stale.json"
    keys = [retrieve._key(f"{i['name']}: {i['description']}") for i in ITEMS]
    stored = {k: [0.5] * dim for k in keys[:3]}
    stored.update({"sha-of-another-model": [0.1] * dim, keys[3]: "junk", keys[4]: [True, None]})
    path.write_text(json.dumps(stored))
    path.chmod(0o644)
    return path


def wait_for(http, predicate):
    for _ in range(200):  # vectors warm in a background thread
        got = http.get("/api/search", params={"q": "slides"}).json()
        if predicate(got):
            return got
        time.sleep(0.02)
    raise AssertionError(got)


def test_api_search_survives_a_cache_of_the_wrong_dimension_and_cleans_it(client, tmp_path, monkeypatch):
    http, _ = client
    stale = invented_cache(tmp_path)
    monkeypatch.setattr(retrieve, "DEFAULT_CACHE", stale)
    got = wait_for(http, lambda g: g["note"] is not None)
    assert got["note"] == DROPPED
    got = wait_for(http, lambda g: g["results"])
    assert got["results"][0] == {"id": "pp", "why": "similar meaning"}
    stored = json.loads(stale.read_text())
    assert len(stored) == 5 and {len(v) for v in stored.values()} == {3} and "sha-of-another-model" not in stored
    assert stat.S_IMODE(stale.stat().st_mode) == 0o600


def test_api_chat_survives_a_cache_of_the_wrong_dimension(client, tmp_path, monkeypatch):
    http, _ = client
    monkeypatch.setattr(retrieve, "DEFAULT_CACHE", invented_cache(tmp_path))
    wait_for(http, lambda g: g["note"] is not None)
    answered = http.post("/api/chat", json={"question": "should I keep gmail-helper"})
    assert answered.status_code == 200, answered.text


def test_fully_cached_wrong_dimension_is_rebuilt_without_a_mixed_file(tmp_path):
    stale = tmp_path / "all.json"
    stale.write_text(json.dumps({retrieve._key(f"{i['name']}: {i['description']}"): [1.0, 0.0] for i in ITEMS}))
    index = warm(Index(ITEMS), stale)
    assert index.note == DROPPED and index.query("slides")[0]["id"] == "pp"
    assert {len(v) for v in json.loads(stale.read_text()).values()} == {3}
    assert warm(Index(ITEMS), stale).note is None  # clean now: no warning, no rewrite needed


def test_a_matching_cache_gives_no_warning(tmp_path):
    cache = tmp_path / "ok.json"
    warm(Index(ITEMS), cache)
    assert warm(Index(ITEMS), cache).note is None


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ([1, 2.5], True),
        ([], False),
        ("ab", False),
        ([1, "x"], False),
        ([1, None], False),
        ([True], False),
        ({"a": 1}, False),
        (None, False),
    ],
)
def test_only_a_non_empty_list_of_numbers_is_a_cached_vector(value, ok):
    assert retrieve._is_vector(value) is ok


def test_an_embedder_with_ragged_lengths_switches_meaning_off_and_writes_nothing(tmp_path):
    cache = tmp_path / "r.json"
    index = warm(Index(ITEMS), cache, lambda texts: [[1.0] * (2 + n % 2) for n, _ in enumerate(texts)])
    assert index.vectors is None and "Meaning-based search is off" in index.note and not cache.exists()


def test_origin_is_searchable_and_named_as_the_reason():
    items = [{"id": "a", "kind": "skill", "name": "ask-one", "description": "Asks", "origin": "mattpocock/skills"}, *ITEMS]
    assert Index(items).query("mattpocock") == [{"id": "a", "why": "from mattpocock/skills"}]
    assert Index(items).query("mattpocock skills") == [{"id": "a", "why": "from mattpocock/skills"}]
    assert Index(ITEMS).query("mattpocock") == []


def test_an_origin_hit_outranks_a_typo_hit():
    items = [
        {"id": "b", "kind": "skill", "name": "shadcm", "description": "Other"},
        {"id": "a", "kind": "skill", "name": "zeta", "description": "Asks", "origin": "acme/shadcn"},
    ]
    assert ids(Index(items).query("shadcn")) == ["a", "b"]
