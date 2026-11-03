# Clustering quality: what the eval found

`uv run --extra local pytest -m eval -s` scores clustering on 30 synthetic Items in 6 groups (pairwise precision and recall of
same-cluster pairs, real `bge-small-en-v1.5` embeddings, Items in the production order: sorted by id). The groups are my guess at a
setup like the author's, so treat the numbers as a regression guard and a direction, not proof.

| Approach | Best F1 | Where |
|---|---|---|
| Raw cosine, greedy leader (shipped) | 0.33 | threshold 0.75 to 0.78; 0.68 merges all 30 into one cluster |
| Raw cosine, average linkage | 0.54 | threshold 0.66; order-independent but O(n^3) in plain Python |
| Mean-centred cosine, greedy leader | 0.67 | threshold 0.0 |
| Mean-centred cosine, average linkage | 0.54 | threshold 0.02 |

Why: raw cosines are squeezed (about 0.70 inside a group, 0.61 across groups), so no threshold separates them. Subtracting the mean
vector of the scanned Items widens the gap (0.16 inside, -0.07 across).

Follow-up if clusters look poor on a real setup: centre the vectors in `cluster()` and use threshold 0.0. It needs a minimum number of
Items to be meaningful (two or three Items centre to noise), so gate it on size, and the existing small-vector unit tests would need
vectors designed for centred cosine. Also worth trying then: a threshold slider in the graph UI (#10).
