from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from constellation import grouping as g
from constellation.models import Cluster, Item, Relation


def item(name, desc="", kind="skill", origin=None, id_=None):
    return Item(id_ or name, kind, name, desc, "claude-code", origin=origin)


def test_words_drop_stopwords_short_words_and_plural_s_but_keep_ai_and_ui():
    assert g._words("The Firecrawl Scrapes web pages, UI and AI! ab skill") == ["firecrawl", "scrape", "web", "page", "ui", "ai"]
    assert g._words("bus gas pass") == ["bus", "gas", "pass"]  # only words longer than four letters lose a plural s ("pass" has 4)
    assert g._words("tests") == ["test"] and g._words("css") == ["css"]


def test_prefix_is_the_first_name_word_when_it_has_four_letters():
    assert g._prefix("firecrawl-scrape") == "firecrawl"
    assert g._prefix("abc-def") is None and g._prefix("abcd-x") == "abcd" and g._prefix("") is None
    assert g._prefix("Vercel_env") == "vercel" and g._prefix("the-big") is None  # a stop word is no prefix


def test_title_keeps_known_acronyms_upper():
    assert [g._title(w) for w in ("ui", "ai", "ux", "pr", "ci", "test")] == ["UI", "AI", "UX", "PR", "CI", "Test"]


def test_caps_scale_with_the_setup():
    assert g._caps(250) == (50, 11) and g._caps(66) == (13, 6) and g._caps(10) == (4, 3) and g._caps(1) == (4, 1)


def test_category_by_keyword_prefix_and_highest_score():
    assert g.category_of(Counter({"deployment": 1})) == "Deploy & infra"  # long keywords match longer words
    assert g.category_of(Counter({"prx": 1})) == g.OTHER  # short ones must match exactly
    assert g.category_of(Counter({"pr": 1})) == "Git & PRs"
    assert g.category_of(Counter({"zzz": 5})) == g.OTHER and g.category_of(Counter()) == g.OTHER
    assert g.category_of(Counter({"tdd": 1, "obsidian": 3, "vault": 1})) == "Notes & study"
    assert g.category_of(Counter({"obsidian": 2, "test": 1})) == "Notes & study"  # counts weigh, not just presence
    assert g.category_of(Counter({"scrape": 1})) == "Web & data fetching"


FAMILIES = (
    [item(f"firecrawl-{x}", f"web {x}", origin="fc") for x in "abcd"]
    + [item(f"vercel-{x}", f"deploy {x}", origin="vc") for x in "abcd"]
    + [item(f"note-{x}", "obsidian vault note") for x in "abcd"]
)


def test_families_group_and_are_named_and_filed_by_their_words():
    clusters = g.group_items(FAMILIES, [], {})
    assert [(c.name, c.category, len(c.item_ids)) for c in clusters] == [
        ("Firecrawl Web", "Web & data fetching", 4),
        ("Note Obsidian", "Notes & study", 4),
        ("Vercel Deploy", "Deploy & infra", 4),
    ]
    assert [c.item_ids[0] for c in clusters] == ["firecrawl-a", "note-a", "vercel-a"]


def test_no_items_no_clusters_and_one_item_one_cluster():
    assert g.group_items([], [], {}) == []
    assert g.group_items([item("solo", "does a thing")], [], {}) == [Cluster("Solo Does", ("solo",), "Other")]


@settings(max_examples=60, deadline=None)
@given(order=st.permutations(FAMILIES))
def test_clusters_do_not_depend_on_the_order_items_arrive_in(order):
    assert g.group_items(list(order), [], {}) == g.group_items(FAMILIES, [], {})


def test_a_label_names_the_cluster_and_the_most_central_labelled_member_wins():
    clusters = g.group_items(FAMILIES, [], {"vercel-c": "Shipping", "vercel-a": "Releasing"})
    names = {c.item_ids[0]: c.name for c in clusters}
    assert names["vercel-a"] in {"Shipping", "Releasing"} and names["firecrawl-a"] == "Firecrawl Web"


def test_a_plugin_cluster_is_named_after_the_plugin_and_contains_it():
    plugin = item("superpowers", "workflow bundle", kind="plugin", id_="plugin:sp")
    skills = [item(f"s{n}", "brainstorm plan workflow", id_=f"sk{n}") for n in range(3)]
    relations = [Relation("plugin:sp", s.id, "contains") for s in skills]
    filler = [item(f"f{n}", f"zz{n}q yy{n}q", id_=f"f{n}") for n in range(8)]
    clusters = g.group_items([plugin, *skills, *filler], relations, {})
    [cluster] = [c for c in clusters if "plugin:sp" in c.item_ids]
    assert cluster.name == "Superpowers Workflow" and cluster.item_ids == ("plugin:sp", "sk0", "sk1", "sk2")


def test_plugin_siblings_group_even_with_unrelated_words():
    words = ["alpha beta", "gamma delta", "omega sigma", "kappa lambda"]
    plugin = item("bundle", "", kind="plugin", id_="p")
    mine = [item(f"m{n}", w, id_=f"m{n}") for n, w in enumerate(words)]
    others = [item(f"o{n}", w, id_=f"o{n}") for n, w in enumerate(["zeta eta", "theta iota", "mu nu", "xi pi"])]
    relations = [Relation("p", m.id, "contains") for m in mine]
    clusters = g.group_items([plugin, *mine, *others], relations, {})
    home = {i: n for n, c in enumerate(clusters) for i in c.item_ids}
    assert len({home[m.id] for m in mine}) == 1


def test_a_related_pair_beats_an_unrelated_one():
    a, b, c = (item(n, "something", id_=n) for n in "abc")
    pair = [Relation("a", "b", "triggers")]
    base = [item(f"x{n}", f"filler{n}", id_=f"x{n}") for n in range(9)]
    clusters = g.group_items([a, b, c, *base], pair, {})
    home = {i: n for n, cl in enumerate(clusters) for i in cl.item_ids}
    assert home["a"] == home["b"]


def test_names_are_unique_even_for_identical_groups():
    twins = [item(f"fire-{n}", "scrape web", id_=f"a{n}") for n in range(4)] + [
        item(f"fire-{n}", "scrape web", id_=f"b{n}") for n in range(4)
    ]
    clusters = g.group_items(twins, [], {})
    assert len({c.name for c in clusters}) == len(clusters)


def test_no_cluster_exceeds_a_fifth_and_small_clusters_fold_in():
    same = [item(f"thing-{n}", "common words everywhere", id_=f"i{n:02}") for n in range(30)]
    clusters = g.group_items(same, [], {})
    sizes = sorted(len(c.item_ids) for c in clusters)
    assert max(sizes) <= 6 and min(sizes) >= 3 and sum(sizes) == 30


def test_threshold_override_controls_merging():
    pairs = [item("alpha-x", "scrape web", id_="a1"), item("alpha-y", "scrape web", id_="a2"), item("alpha-z", "scrape web", id_="a3")]
    pairs += [item("beta-x", "deploy", id_="b1"), item("beta-y", "deploy", id_="b2"), item("beta-z", "deploy", id_="b3")]
    pairs += [item(f"c{n}", f"filler{n} stuff{n}", id_=f"c{n}") for n in range(6)]
    loose = g.group_items(pairs, [], {}, threshold=0.0)
    tight = g.group_items(pairs, [], {}, threshold=5.0)
    assert len(loose) <= len(tight)


def test_embedding_cosine_groups_what_the_words_cannot():
    its = [item(f"n{n}", f"w{n}x", id_=f"i{n:02}") for n in range(12)]
    vecs = {i.id: ([1.0, 0.0] if n < 6 else [0.0, 1.0]) for n, i in enumerate(its)}
    halves = {frozenset(f"i{n:02}" for n in range(6)), frozenset(f"i{n:02}" for n in range(6, 12))}
    with_vectors = g.group_items(its, [], {}, vecs)
    assert all(any(frozenset(c.item_ids) <= h for h in halves) for c in with_vectors)  # never mixes the two directions
    assert [len(c.item_ids) for c in with_vectors] == [3, 3, 3, 3]
    assert any(len({int(i[1:]) < 6 for i in c.item_ids}) == 2 for c in g.group_items(its, [], {}))  # the words alone mix them


def test_opposed_vectors_never_pull_items_together():
    its = [item(f"n{n}", f"w{n}x", id_=f"i{n:02}") for n in range(12)]
    opposed = {i.id: ([1.0, 0.0] if n < 6 else [-1.0, 0.0]) for n, i in enumerate(its)}
    for c in g.group_items(its, [], {}, opposed):
        assert len({int(i[1:]) < 6 for i in c.item_ids}) == 1


# ---- exact pins for the pure helpers (found by mutation testing) ----
import math  # noqa: E402

import pytest  # noqa: E402


def test_key_orders_a_pair():
    assert g._key(5, 2) == (2, 5) and g._key(2, 5) == (2, 5)


def test_docs_weight_name_words_and_ignore_a_hooks_description():
    assert g._docs([item("Scrape-web", "scrape page", kind="hook")]) == [Counter({"scrape": 2, "web": 2})]
    assert g._docs([item("Scrape-web", "scrape page")]) == [Counter({"scrape": 3, "web": 2, "page": 1})]


def test_tfidf_is_unit_length_and_rarer_words_weigh_more():
    docs = [Counter(x=1, y=1), Counter(x=1), Counter()]
    ix, iy = math.log(4 / 3) + 1, math.log(4 / 2) + 1
    norm = math.sqrt(ix**2 + iy**2)
    got = g._tfidf(docs)
    assert got[0] == {"x": pytest.approx(ix / norm), "y": pytest.approx(iy / norm)}
    assert got[1] == {"x": pytest.approx(1.0)} and got[2] == {}
    assert g._tfidf([Counter(a=3)]) == [{"a": pytest.approx(1.0)}]  # one document: idf is log(2/2)+1


def test_cosine_counts_shared_words_only_and_is_symmetric():
    assert g._cosine({"a": 0.6, "b": 0.8}, {"a": 1.0}) == pytest.approx(0.6)
    assert g._cosine({"a": 1.0}, {"a": 0.6, "b": 0.8}) == pytest.approx(0.6)
    assert g._cosine({"a": 1.0}, {"b": 1.0}) == 0.0 and g._cosine({}, {"a": 1.0}) == 0.0


def sims(a, b, relations=(), tfidf=None, vectors=None):
    return g._similarities([a, b], list(relations), tfidf or [{}, {}], vectors)[(0, 1)]


def test_each_signal_adds_its_own_weight():
    s, s2 = item("aa", id_="a"), item("bb", id_="b")
    assert sims(s, s2) == pytest.approx(0.03)  # same kind family
    assert sims(s, item("bb", kind="hook", id_="b")) == 0.0
    assert sims(s, item("bb", kind="command", id_="b")) == pytest.approx(0.03)  # skill and command share a family
    assert sims(item("aa", kind="mcp_server", id_="a"), item("bb", kind="connector", id_="b")) == pytest.approx(0.03)
    assert sims(item("aa", kind="hook", id_="a"), item("bb", kind="hook", id_="b")) == pytest.approx(0.03)
    assert sims(item("aa", origin="o", id_="a"), item("bb", origin="o", id_="b")) == pytest.approx(0.38)
    assert sims(item("aa", origin="o", id_="a"), item("bb", origin="p", id_="b")) == pytest.approx(0.03)
    assert sims(item("firecrawl-a", id_="a"), item("firecrawl-b", id_="b")) == pytest.approx(0.33)
    assert sims(item("fire-a", id_="a"), item("fire-b", id_="b")) == pytest.approx(0.33)
    assert sims(item("abc-a", id_="a"), item("abc-b", id_="b")) == pytest.approx(0.03)
    assert sims(item("firecrawl-a", origin="o", id_="a"), item("firecrawl-b", origin="o", id_="b")) == pytest.approx(0.68)


def test_a_plugin_and_what_it_contains_share_an_owner():
    plugin, skill = item("p", kind="plugin", id_="plug"), item("s", id_="sk")
    assert sims(plugin, skill, [Relation("plug", "sk", "contains")]) == pytest.approx(0.35)  # no family bonus: plugin vs skill
    two = sims(item("a", id_="x"), item("b", id_="y"), [Relation("plug", "x", "contains"), Relation("plug", "y", "contains")])
    assert two == pytest.approx(0.38)


def test_relations_other_than_contains_add_a_bonus_and_unknown_ids_are_ignored():
    a, b = item("aa", id_="a"), item("bb", id_="b")
    assert sims(a, b, [Relation("a", "b", "triggers")]) == pytest.approx(0.23)
    assert sims(a, b, [Relation("b", "a", "triggers")]) == pytest.approx(0.23)
    assert sims(a, b, [Relation("zz", "b", "triggers")]) == pytest.approx(0.03)
    assert sims(a, b, [Relation("a", "zz", "triggers")]) == pytest.approx(0.03)
    assert sims(a, b, [Relation("a", "b", "contains")]) == pytest.approx(0.03)


def test_words_and_vectors_add_to_the_score_and_opposed_vectors_do_not_subtract():
    a, b = item("aa", id_="a"), item("bb", id_="b")
    assert sims(a, b, tfidf=[{"x": 0.6, "y": 0.8}, {"x": 1.0}]) == pytest.approx(0.63)
    assert sims(a, b, tfidf=[{"x": 1.0}, {"x": 0.6, "y": 0.8}]) == pytest.approx(0.63)
    assert sims(a, b, vectors={"a": [1.0, 0.0], "b": [0.6, 0.8]}) == pytest.approx(0.27)
    assert sims(a, b, vectors={"a": [1.0, 0.0], "b": [-1.0, 0.0]}) == pytest.approx(0.03)
    with pytest.raises(ValueError):
        sims(a, b, vectors={"a": [1.0], "b": [1.0, 0.0]})


def test_all_pairs_are_scored_low_index_first():
    its = [item(n, id_=n) for n in "abc"]
    assert sorted(g._similarities(its, [], [{}, {}, {}], None)) == [(0, 1), (0, 2), (1, 2)]


def pairs_of(n, strong, value=1.0, rest=0.0):
    return {(a, b): (value if (a, b) in strong else rest) for a in range(n) for b in range(a + 1, n)}


def test_agglomerate_merges_strong_groups_and_stops_at_the_threshold():
    triples = {(a, b) for t in range(4) for a in range(3 * t, 3 * t + 3) for b in range(a + 1, 3 * t + 3)}
    assert g._agglomerate(pairs_of(12, triples, 0.9), 12, 0.5) == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]
    assert g._agglomerate(pairs_of(4, {(0, 1)}, 0.5), 4, 0.5) == [[0, 1], [2], [3]]  # a similarity equal to the threshold merges
    assert g._agglomerate(pairs_of(4, {(0, 1)}, 0.5), 4, 0.5000001) == [[0], [1], [2], [3]]


def test_agglomerate_ties_go_to_the_lowest_pair_and_better_similarity_wins():
    assert g._agglomerate(pairs_of(3, {(0, 1), (0, 2), (1, 2)}), 3, 0.5) == [[0, 1], [2]]
    base = pairs_of(3, {(0, 1), (0, 2)})
    base[(1, 2)] = 2.0
    assert g._agglomerate(base, 3, 0.5) == [[0], [1, 2]]
    assert g._agglomerate(pairs_of(4, {(0, 3), (1, 2)}), 4, 0.5) == [[0, 3], [1, 2]]


def test_agglomerate_respects_the_size_cap_and_the_minimum_cluster_count():
    everything = pairs_of(30, {(a, b) for a in range(30) for b in range(a + 1, 30)})
    sizes = sorted(len(m) for m in g._agglomerate(everything, 30, 0.5))
    assert sizes == [6] * 5  # a fifth of 30
    tens = {(a, b): (1.0 if a // 10 == b // 10 else 0.9) for a in range(100) for b in range(a + 1, 100)}
    sizes = sorted(len(m) for m in g._agglomerate(tens, 100, 0.5))
    assert sizes == [10, 10, 10, 10, 20, 20, 20]  # stops at ceil(sqrt(100) / 1.5) = 7 clusters; two groups fit a cap of 20


def test_agglomerate_folds_tiny_clusters_into_the_nearest_neighbour():
    pairs = {(a, b) for a in range(4) for b in range(a + 1, 4)} | {(a, b) for a in range(4, 8) for b in range(a + 1, 8)}
    base = pairs_of(11, pairs, 1.0, 0.0)
    base[(8, 9)] = 1.0
    assert g._agglomerate(base, 11, 0.5) == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10]]
    # nothing can absorb the last point (every cluster is at the cap), so it stays in no cluster
    pairs |= {(a, b) for a in range(8, 12) for b in range(a + 1, 12)}
    assert g._agglomerate(pairs_of(13, pairs), 13, 0.5) == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]]


def test_a_few_points_may_stay_unassigned_but_only_when_nothing_is_close():
    n = 40  # five percent of 40 is two points
    assert sum(map(len, g._agglomerate(pairs_of(n, set(), rest=0.01), n, 0.5))) == 38
    assert sum(map(len, g._agglomerate(pairs_of(n, set(), rest=0.05), n, 0.5))) == 40
    assert sum(map(len, g._agglomerate(pairs_of(n, set(), rest=0.02), n, 0.5))) == 40  # exactly LOOSE still joins
    assert sum(map(len, g._agglomerate(pairs_of(12, set(), rest=0.01), 12, 0.5))) == 12  # 5% of 12 rounds down to none


def test_central_is_the_member_most_similar_to_the_rest_lowest_index_on_a_tie():
    base = {(0, 1): 0.2, (0, 2): 0.2, (1, 2): 0.9}
    assert g._central([0, 1, 2], base) == 1
    assert g._central([0, 1, 2], {(0, 1): 1.0, (0, 2): 1.0, (1, 2): 1.0}) == 0
    assert g._central([2, 1], {(1, 2): 0.5}) == 1


def test_distinctive_words_need_two_members_and_unshared_words_outrank_common_ones():
    docs = [Counter(alpha=2, beta=1, gamma=1), Counter(alpha=2, beta=1), Counter(delta=1)]
    spread = Counter(alpha=1, beta=2, gamma=1, delta=1)
    assert g._distinctive([0, 1], docs, spread, 2) == ["alpha", "beta"]  # gamma is in one member only; alpha is in fewer groups
    assert g._distinctive([2], docs, spread, 2) == ["delta"]  # a single member may name its own cluster
    tie = [Counter(bb=1, aa=1), Counter(bb=1, aa=1)]
    assert g._distinctive([0, 1], tie, Counter(aa=1, bb=1), 1) == ["aa", "bb"]
    # idf: log((1 + k) / (1 + spread)) + 1 with k=3 groups; frequency is averaged over the members
    ranked = g._distinctive([0, 1], [Counter(p=3, q=1), Counter(p=3, q=1)], Counter(p=3, q=1), 3)
    assert ranked == ["p", "q"]
    low = g._distinctive([0, 1], [Counter(p=1, q=1), Counter(p=1, q=1)], Counter(p=3, q=1), 3)
    assert low == ["q", "p"]  # equal use, but p appears in more groups


def test_unique_appends_spare_words_then_a_number():
    assert g._unique("Fire", ["web"], set()) == "Fire"
    assert g._unique("Fire", ["web", "page"], {"Fire"}) == "Fire Web"
    assert g._unique("Fire", ["web", "page"], {"Fire", "Fire Web"}) == "Fire Web Page"
    assert g._unique("Fire", [], {"Fire"}) == "Fire 2"
    assert g._unique("Fire", [], {"Fire", "Fire 2"}) == "Fire 3"
    assert g._unique("Fire", ["ui"], {"Fire"}) == "Fire UI"


def named(items, groups, relations=(), labels=None):
    items = sorted(items, key=lambda i: i.id)
    base = {(a, b): 0.1 for a in range(len(items)) for b in range(a + 1, len(items))}
    return g._name(items, groups, g._docs(items), list(relations), base, labels or {})


def test_name_uses_the_two_most_distinctive_words_and_files_the_category():
    its = [item(n, d, id_=n) for n, d in (("scrape-a", "web pages"), ("scrape-b", "web pages"), ("deploy-a", "ship"), ("deploy-b", "ship"))]
    assert named(its, [[0, 1], [2, 3]]) == [
        Cluster("Deploy Ship", ("deploy-a", "deploy-b"), "Deploy & infra"),
        Cluster("Scrape Page", ("scrape-a", "scrape-b"), "Web & data fetching"),
    ]


def test_a_labelled_member_names_the_cluster_preferring_the_most_central_one():
    its = [item(n, "x", id_=n) for n in "abc"]
    base = {(0, 1): 0.9, (0, 2): 0.1, (1, 2): 0.1}
    [c] = g._name(its, [[0, 1, 2]], g._docs(its), [], base, {"a": "Alpha", "b": "Beta", "c": "Gamma"})
    assert c.name in {"Alpha", "Beta"}
    [c] = g._name(its, [[0, 1, 2]], g._docs(its), [], {(0, 1): 0.1, (0, 2): 0.1, (1, 2): 0.9}, {"c": "Gamma", "a": "Alpha"})
    assert c.name == "Alpha"  # b is the centre but unlabelled; the others are tried in order
    [c] = g._name(its, [[0, 1, 2]], g._docs(its), [], {(0, 1): 0.1, (0, 2): 0.1, (1, 2): 0.9}, {"c": "Gamma", "b": "Beta"})
    assert c.name == "Beta"  # the centre wins over an earlier-labelled member
    [c] = g._name(its, [[0, 1, 2]], g._docs(its), [], {(0, 1): 0.1, (0, 2): 0.1, (1, 2): 0.9}, {"c": "Gamma"})
    assert c.name == "Gamma"


def test_a_group_with_no_shared_words_takes_its_central_members_name():
    its = [item("aaaa", "one", id_="a"), item("bbbb", "two", id_="b"), item("cccc", "three", id_="c")]
    [c] = g._name(its, [[0, 1, 2]], g._docs(its), [], {(0, 1): 0.1, (0, 2): 0.1, (1, 2): 0.9}, {})
    assert c.name == "bbbb"


def test_a_plugin_group_leads_with_the_plugin_name_and_one_distinct_word():
    plugin = item("Workflow-Kit", "bundle", kind="plugin", id_="p")
    skills = [item(f"s{n}", "workflow brainstorm", id_=f"s{n}") for n in range(3)]
    rel = [Relation("p", s.id, "contains") for s in skills]
    [c] = named([plugin, *skills], [[0, 1, 2, 3]], rel)
    assert c.name == "Workflow Kit Brainstorm"  # "workflow" is already in the plugin's name


def test_the_bigger_group_claims_a_name_first_and_the_other_gets_a_spare_word():
    its = [item(f"fire-{n}", "web page", id_=f"a{n}") for n in range(3)] + [item(f"fire-{n}", "web page", id_=f"b{n}") for n in range(2)]
    clusters = named(its, [[0, 1, 2], [3, 4]])
    assert [(c.name, len(c.item_ids)) for c in clusters] == [("Fire Page", 3), ("Fire Page Web", 2)]


def test_more_exact_pins_from_mutation_testing():
    assert g.category_of(Counter({"auditor": 1})) == "Code review & testing"  # a five-letter keyword matches longer words
    assert sims(item("aa", kind="hook", id_="a"), item("bb", kind="plugin", id_="b")) == 0.0  # unknown kinds are their own family
    assert sims(
        item("aa", id_="a"), item("bb", id_="b"), tfidf=[{"x": 1.0}, {"x": 1.0}], vectors={"a": [1.0], "b": [1.0]}
    ) == pytest.approx(1.43)
    nine = pairs_of(9, set(), rest=0.05)
    assert [len(m) for m in g._agglomerate(nine, 9, 0.5)] == [
        4,
        4,
    ]  # nine Items fold into groups (one is left over: every cluster is at the cap)
    reverse = {(1, 2): 1.0, (0, 2): 1.0, (0, 1): 1.0}  # the lowest tied pair wins whatever order the pairs arrive in
    assert g._agglomerate(reverse, 3, 0.5) == [[0, 1], [2]]


def test_group_items_passes_its_threshold_on(monkeypatch):
    seen = []
    monkeypatch.setattr(g, "_agglomerate", lambda base, n, threshold: seen.append(threshold) or [[0]])
    g.group_items([item("a")], [], {})
    g.group_items([item("a")], [], {}, threshold=0.4)
    g.group_items([item("a")], [], {}, threshold=0.0)
    assert seen == [g.THRESHOLD, 0.4, 0.0]


def test_distinctive_exact_ordering_and_two_member_words_in_a_group_of_three():
    docs = [Counter(p=2, q=1), Counter(p=2, q=1), Counter(p=1, q=1)]
    assert g._distinctive([0, 1, 2], docs, Counter(p=3, q=1), 3) == ["q", "p"]  # 3 * 1.693 beats 5 * 1.0 only with the right idf
    assert g._distinctive([0, 1, 2], [Counter(x=1), Counter(x=1), Counter()], Counter(x=1), 1) == ["x"]


def test_name_uses_spread_claim_order_centre_and_plugin_rules():
    its = [item(n, d, id_=n) for n, d in (("a1", "alpha beta"), ("a2", "alpha beta"), ("b1", "alpha gamma"), ("b2", "alpha gamma"))]
    names = {c.item_ids: c.name for c in named(its, [[0, 1], [2, 3]])}
    assert names[("a1", "a2")] == "Beta Alpha" and names[("b1", "b2")] == "Gamma Alpha"  # a word in fewer groups ranks higher
    big = [item(f"fire-{n}", "web page", id_=f"{n}") for n in range(5)]
    assert [(c.name, c.item_ids) for c in named(big, [[0, 1], [2, 3, 4]])] == [
        ("Fire Page Web", ("0", "1")),
        ("Fire Page", ("2", "3", "4")),
    ]
    abc = [item(n, "x", id_=n) for n in "abc"]
    base = {(0, 1): 0.1, (0, 2): 0.9, (1, 2): 0.1}  # a and c are the centre pair; a wins ties
    assert g._name(abc, [[0, 1, 2]], g._docs(abc), [], base, {"b": "Beta", "c": "Gamma"})[0].name == "Beta"
    base = {(0, 1): 0.1, (0, 2): 0.1, (1, 2): 0.9}
    assert g._name(abc, [[0, 1, 2]], g._docs(abc), [], base, {"a": "Alpha", "b": "Beta"})[0].name == "Beta"
    base = {(0, 1): 0.1, (0, 2): 0.9, (1, 2): 0.9}
    assert g._name(abc, [[0, 1, 2]], g._docs(abc), [], base, {"a": "Alpha", "c": "Gamma"})[0].name == "Gamma"
    p1, p2 = item("kit-one", "x", kind="plugin", id_="p1"), item("kit-two", "x", kind="plugin", id_="p2")
    mixed = named([p1, p2], [[0, 1]])
    assert mixed[0].name == "Kit"  # two plugins in one cluster: no plugin names it


def test_two_plugin_clusters_with_the_same_name_get_spare_words():
    def bundle(pid, tag):
        plugin = item("Kit", "bundle", kind="plugin", id_=pid)
        skills = [item(f"{tag}{n}", "alpha beta gamma", id_=f"{tag}{n}") for n in range(3)]
        return [plugin, *skills], [Relation(pid, s.id, "contains") for s in skills]

    (i1, r1), (i2, r2) = bundle("p1", "a"), bundle("p2", "b")
    clusters = named(i1 + i2, [[0, 1, 2, 6], [3, 4, 5, 7]], r1 + r2)  # ids sort as a0 a1 a2 b0 b1 b2 p1 p2
    assert [c.name for c in clusters] == ["Kit Alpha", "Kit Alpha Beta"]


# ---- naming: filler words and bigrams ----
def test_stems_keep_ss_us_as_is_endings():
    assert g._words("compass canvas status basis tests") == ["compass", "canvas", "status", "basis", "test"]


def test_bigram_needs_half_the_members_three_members_and_skips_banned():
    its = [item(n, id_=n) for n in ("sort-tally-a", "sort-tally-b", "sort-lattice-c", "sort-tally-d")]
    assert g._bigram([0, 1, 2, 3], its, set()) == "Sort Tally"
    assert g._bigram([0, 1, 2, 3], its, {"tally"}) is None  # banned words form no pair; 'sort lattice' has one of four
    assert g._bigram([0, 1], its, set()) is None  # fewer than three members
    half = [item(n, id_=n) for n in ("sort-tally", "sort-tally", "x-y", "p-q")]
    assert g._bigram([0, 1, 2, 3], half, set()) == "Sort Tally"  # exactly half is enough
    third = [item(n, id_=n) for n in ("sort-tally", "sort-tally", "x-y", "p-q", "u-v")]
    assert g._bigram([0, 1, 2, 3, 4], third, set()) is None  # two of five is under half
