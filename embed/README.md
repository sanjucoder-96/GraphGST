# embed — Graph ML embeddings + vendor lookalike (Phase 5)

Turns the GSTIN → Invoice → GSTIN projection graph into dense per-GSTIN
vectors, then answers "which vendors behave like this one?" via cosine
k-NN in constant time per query.

## Method

**Random walks → PMI matrix → truncated SVD.**

1. `build_adjacency(edges)` — folds the directed edge list into a
   weighted undirected graph. Weight = invoice count + amount kicker.
2. `biased_walks(neighbours, p, q)` — node2vec § 3.2 biased random
   walker with `p` (return) and `q` (in-out) hyperparameters. Alias
   tables give O(1) per-step sampling.
3. `_cooccurrence(walks, window)` — symmetric co-occurrence counts
   within the sliding window.
4. `_build_sppmi(pair, node, neg_k)` — Shifted Positive PMI matrix.
   Levy & Goldberg (2014, NIPS) showed that SGNS (Skip-Gram Negative
   Sampling — what node2vec optimises) implicitly factorises this
   matrix, so SVD of it yields node2vec-quality embeddings.
5. `_truncated_svd(M, dim)` — top-`dim` singular vectors, scaled by
   √σ, then L2-normalized so cosine sim = dot product.

**Why not gensim.** Pure numpy is one fewer heavyweight dependency
(50+ MB) and PMI-SVD is provably equivalent to SGNS at the objective
level. Training on 500 GSTINs / 5000 edges finishes in < 300 ms.
When we need FAISS-scale (V > 50 K) we swap the `LookalikeIndex`
implementation, not the training.

## Public API

```python
from embed import EmbedConfig, train, lookalike

model = train(graph_source={"edges": edge_list}, config=EmbedConfig(dim=64))
top5 = lookalike(model, "27AAPFU0939F1ZV", k=5)
# → [("29AABCT1332L1ZU", 0.87), ...]
```

## HTTP

- `POST /api/embed/train` — retrains from live graph (admin-only).
- `GET /api/embed/lookalike/{gstin_id}?k=5` — returns top-K neighbours.
- `GET /api/embed/status` — model trained? when? on what dataset shape?

## Benchmark

`benchmarks/bench_embed_lookalike.py` scores the trained index on the
"ring cohesion" task: for every planted-ring member, does its top-K
lookalike list contain OTHER members of the same ring? Reported
metrics: `ring_cohesion_recall@K`, `hit_at_K`. Real numbers live in
`IMPLEMENTATION_LOG.md`.
