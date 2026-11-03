from hypothesis import given, settings
from hypothesis import strategies as st

from constellation.cluster import cluster, item_vectors
from constellation.models import Item

VECTORS = st.lists(st.floats(-1, 1, allow_nan=False, allow_infinity=False), min_size=3, max_size=3)


@settings(max_examples=300, deadline=None)
@given(vectors=st.lists(VECTORS, min_size=2, max_size=8), data=st.data())
def test_clusters_do_not_depend_on_the_order_items_arrive_in(vectors, data):
    items = [Item(f"id{i}", "skill", f"n{i}", "d", "claude-code") for i in range(len(vectors))]
    by_text = {f"n{i}: d": v for i, v in enumerate(vectors)}

    def embed(texts):
        return [by_text[t] for t in texts]

    shuffled = data.draw(st.permutations(items))

    def shape(order):
        return {frozenset(c.item_ids): c.name for c in cluster(order, {}, *item_vectors(order, embed), 0.6)}

    assert shape(items) == shape(list(shuffled))
