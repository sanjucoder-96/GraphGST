# Graph ML — Embeddings & Vendor Lookalike ("Related Vendors")

This subsystem turns the `GSTIN → Invoice → GSTIN` invoice-projection graph into
one dense vector per GSTIN, then answers *"which vendors behave like this one?"*
with a cosine k-NN lookup. It powers the **Related Vendors** strip in the
investigator UI. Code: `embed/`.

It is a research prototype on **synthetic** data. The embedding is a pure-numpy
implicit matrix factorization — **no torch, no gensim, no external service**
(`embed/__init__.py`). Everything below is what the code actually does; where a
claim is an inference rather than a line of code, it is marked as such.

## Pipeline

```
edges ─► build_adjacency ─► biased_walks ─► _cooccurrence ─► _build_sppmi ─► _truncated_svd ─► EmbedModel
        (embed/walks.py)    (embed/walks.py) (embed/train)    (embed/train)   (embed/train)   (L2-normed rows)
                                                                                     │
                                              LookalikeIndex.similar_to ◄────────────┘  cosine k-NN
                                              (embed/lookalike.py)
```

The method is **random walks → co-occurrence → shifted-PMI matrix → truncated
SVD → unit vectors → cosine k-NN**. This is the Levy & Goldberg (2014) result
that Skip-Gram with Negative Sampling — the objective node2vec/DeepWalk optimise
— is an *implicit factorization of a shifted PMI matrix*, so factorizing that
matrix directly yields node2vec-quality vectors without any SGD. The claim of
equivalence is stated in code at `embed/train.py:1-16` and `embed/README.md:9-27`.

## Step 1 — graph construction (`embed/walks.py:25`, `build_adjacency`)

The directed invoice edge list is folded into an **undirected weighted** graph
(a supplier's neighbourhood includes both its buyers and its sellers). For each
unordered pair `(a, b)`:

```
weight(a, b) = Σ [ 1.0 + amount_kicker × amount ]  over all invoices between a and b
```

So the weight is the **invoice count** plus a small amount-derived kicker
(`amount_kicker = 0.0001`, `walks.py:27`). The kicker's stated purpose
(`walks.py:9-13`) is that "a supplier with 1000 tiny invoices to a shell isn't
equal to a supplier with 5 large invoices to real companies." Neighbour lists
are sorted (`walks.py:48-49`) for determinism.

## Step 2 — biased random walks (`embed/walks.py:86`, `biased_walks`)

node2vec's biased walker (§3.2 of the paper) with two hyperparameters:

| Param | Name | Effect (`walks.py:96-98`) |
|---|---|---|
| `p` | return | high → walk avoids backtracking to the previous node |
| `q` | in-out | high → walk stays local (BFS-like); low → explores outward (DFS-like) |

At **defaults `p = q = 1.0` the walk reduces to plain DeepWalk** (an unbiased,
weight-proportional walk) — this is the configured default, so node2vec's bias
machinery is present but not actually engaged unless `p`/`q` are changed. Each
step is O(1) via **Vose alias tables** (`_alias_setup`, `walks.py:53`): a node
alias table for the first step (weight-proportional), and lazily-built edge alias
tables for subsequent steps that fold in the `p`/`q` bias (`walks.py:119-140`).
Start order is reshuffled each pass with the seeded RNG (`walks.py:143-146`).

## Step 3 — co-occurrence → shifted-PMI matrix (`embed/train.py:57`, `:80`)

`_cooccurrence` slides a symmetric window (`window = 5`) along each walk and
counts center/context pairs and per-node occurrences. `_build_sppmi` then builds
a `V × V` matrix whose non-zero entries are the **Shifted Positive PMI**:

```
sppmi(w, c) = max( 0,  log(n · total_words / (node[w] · node[c]))  −  log k )
```

where `n` = pair count, `node[·]` = occurrence count, `k = neg_k = 5` is the
negative-sampling shift, and only strictly-positive entries are stored
(`train.py:98-101`). The positivity threshold is what makes the matrix sparse
(measured density ≈ **0.158** on the headline run).

> **Honest note on the PMI normalization.** The implemented formula uses
> `total_words` as a *single* normalizer (`train.py:98`, and the code's own
> comment "using pair counts"). Textbook PMI with `P(w,c) = n / n_pairs` would
> carry a second `log(total_words)` and a `−log(n_pairs)` term. The difference is
> a **corpus-wide additive constant**, so it composes with the `−log k` shift: it
> moves the effective sparsification threshold but does **not** change the
> *relative* ordering of co-occurrence strengths. It is an approximation of the
> clean SPPMI in the docstring, not an exact reproduction of it.

## Step 4 — truncated SVD → vectors (`embed/train.py:105`, `_truncated_svd`)

The SPPMI matrix is factorized and each node's vector is the top-`dim` left
singular vectors scaled by `√σ`:

```
vecs = U[:, :dim] · sqrt(σ[:dim])     then L2-normalized (unit rows)
```

`dim = 64`, capped at `V − 1`. Rows are L2-normalized (`train.py:121-124`) so
that **cosine similarity is a plain dot product** downstream.

> **Honest note on "randomised SVD".** The comment at `train.py:110-111` says
> "Deterministic randomised SVD," but the executed path calls the **exact** dense
> `numpy.linalg.svd(M, full_matrices=False)` (`train.py:113-115`). A Gaussian
> random-projection is only the `except`-branch fallback if the exact SVD raises
> (`train.py:116-120`). At the benchmark scale (V ≈ 500) the exact SVD is cheap
> and fully deterministic; the "randomised" label is stale.

## Step 5 — cosine k-NN lookalike (`embed/lookalike.py`)

`LookalikeIndex.similar_to(gstin, k)` computes `matrix @ matrix[idx]` (= cosine,
since rows are unit-length), then uses `argpartition` to grab the top-`(k + |excluded|)`
and `argsort` only that head (`lookalike.py:33-48`). The query node and any
`exclude` set are removed; it returns `(gstin_id, cosine)` pairs. Cost is
O(V · dim) per query — the code notes FAISS can be swapped behind the same
interface at larger scale (`lookalike.py:3-6`).

## Hyperparameters (as found in code)

The library defaults and the config that produced the **headline benchmark
numbers** differ — the benchmark overrides walks/length. Both are shown honestly.

| Param | `EmbedConfig` default (`train.py:32-43`) | Headline benchmark run (`bench_embed_lookalike.py:154-157`, `run_all.py:86-88`) |
|---|---:|---:|
| `dim` (embedding size) | 64 | 64 |
| `walks_per_node` | 10 | **15** |
| `walk_len` | 20 | **25** |
| `window` | 5 | 5 |
| `neg_k` (SPPMI shift `k`) | 5 | 5 |
| `p` (return) | 1.0 | 1.0 |
| `q` (in-out) | 1.0 | 1.0 |
| `seed` | 42 | 42 |
| `min_count` | 1 | 1 |
| `amount_kicker` | 0.0001 | 0.0001 |
| `k` (lookalike neighbours) | — | 10 (the gated K) |

The HTTP `POST /train` body (`embed/api.py:25-33`) defaults to the **library**
values (walks 10 / len 20), *not* the benchmark's 15 / 25. The **live demo**
path, though, pins the benchmark config: `_train_embeddings`
(`risk/materialize.py:319-320`) hard-codes `dim 64 / walks 15 / len 25 / seed 42`,
so a demo reset reproduces the headline structural/cohesion numbers rather than
the lighter library defaults.

## Determinism

Every source of order is pinned, so the same graph reproduces the same vectors —
and, since V6.4, the same **bytes** on disk:

- Seeded RNG for walks — `random.Random(42)` (`walks.py:100`); the SVD path is
  exact (`numpy.linalg.svd`, `train.py:117`) and therefore deterministic (the
  fallback uses `np.random.default_rng(seed)`).
- Node ordering is **sorted** (`walks.py:101`, `train.py:84`) and adjacency lists
  are sorted (`walks.py:48-49`), so matrix row order is stable. The SPPMI matrix
  is filled by **assignment** to a unique `(row, col)` per co-occurring pair
  (`train.py:93-101`), so co-occurrence iteration order can't perturb it either.
- **Fixed edge-accumulation order (V6.4).** `build_adjacency` sums float weights
  in edge-arrival order (`walks.py:41`), and float addition isn't associative, so
  the arrival order must be pinned for the `.npy` to be byte-identical run to run.
  The training edge query now ends `ORDER BY src, dst, inv` (invoice id)
  (`embed/api.py:99-104`, `_hydrate_edges_from_neo4j`), fixing that order → a
  byte-reproducible artifact.
- **Hash-seed-invariant (V6.4).** Given a fixed edge list the whole embedding
  pipeline is independent of Python's hash salt — node keys and adjacency lists
  are sorted, the start-order shuffle is seeded, and the only sets (`prev_nbs`,
  `walks.py:125`) are used purely for membership tests. V6.4's `ORDER BY` makes
  the edge list itself hash-seed-invariant in the live path, so
  `_train_embeddings` is deterministic with **no** special `PYTHONHASHSEED`
  (its docstring, `materialize.py:307-312`). The benchmark runner still exports
  `PYTHONHASHSEED=0` (`docs/BENCHMARKS.md`) for the rest of its *in-memory*
  pipeline — the ring engine's NetworkX SCC iteration order, and edge ordering
  into `build_adjacency` before a query has sorted it — not for the embedding
  walks themselves.

*(Inference, not a code comment: because the vectors come from a closed-form
matrix factorization rather than SGD-trained SGNS, there is no learning rate,
epoch count, or negative-sampling noise to tune — the "no training instability"
motivation follows from using an exact SVD, and the pure-numpy / no-heavy-deps
motivation is stated in `embed/README.md:25-27`.)*

## Persistence & API

- **Persist** (`embed/persist.py`): `embeddings.npy` (the matrix) + a JSON
  sidecar (`embeddings.meta.json`) with `ids`, `config`, `stats`, `saved_at`,
  `shape`, and — since V6.4 — a **`graph_fingerprint`**: the *same*
  `risk.materialize.current_fingerprint()` (counts + cheap content aggregates of
  the graph) captured at training time, so a reader can tell whether the graph has
  moved since (`persist.py:29-38`).
- **`POST /api/embed/train`** — admin-only (`Depends(require_admin)`), hydrates
  edges from Neo4j and persists artifacts, now also stamping the graph
  fingerprint (`api.py:36-48`). Its request body still defaults to the **library**
  config (walks 10 / len 20), not the benchmark's 15 / 25.
- **`GET /api/embed/lookalike/{gstin_id}?k=`** — top-K neighbours as
  `{gstin_id, similarity}` (`api.py:51-59`).
- **`GET /api/embed/status`** — `trained`, `n_indexed`, `config`, `stats`,
  `saved_at`, `shape`, plus (V6.4) the stored `graph_fingerprint`, the live
  `current_fingerprint`, and a **`stale`** verdict (`api.py:62-79`): `True` when
  nothing is trained, when the artifact predates fingerprint tracking (empty
  stored fingerprint), or when stored ≠ current. A changed graph is therefore
  flagged, not silently served as fresh neighbours — mirroring risk-materialization
  staleness.

### Live training — Related Vendors is LIVE in the demo (V6.4)

Before V6.4 the only ways to populate the index were the admin `POST /train` or the
benchmark, so a freshly-reset demo had no persisted artifact, the lookalike
endpoint 404'd, and Related Vendors had nothing to show (it fell back to an
empty/mock state). V6.4 folds training into the canonical refresh:
`refresh_intelligence(persist=True)` (`risk/materialize.py:307-322`,
`_train_embeddings`) trains **and** persists the index **once per refresh** —
against the exact graph state it just materialized risk over — stamping that same
fingerprint. Because both the demo reset (`demo/reset.py:118`) and the datagen
load endpoint (`datagen/api.py:92`) call `refresh_intelligence`, the strip is
backed by a live, per-reset index — not a per-request train, and not a UI mock.

It trains with the **benchmark-headline config** — `EmbedConfig(dim=64,
walks_per_node=15, walk_len=25, seed=42)` (`materialize.py:319-320`), *not* the
`POST /train` library defaults — so the demo reproduces the documented
`structural_hit@10 = 0.667` and `cohesion_recall@10 = 0.761`. Training is
best-effort: an empty edge set returns `0` indexed and the refresh still
completes (`materialize.py:288-292`, `_train_embeddings:314-318`), and the count
the refresh reports (`embeddings_indexed`) is `len(model.ids)`.
`tests/test_neo4j_integration.py:398-431` asserts the artifact exists with a
fingerprint after a refresh and that `/status` flips `stale` when graph content
changes.

## Evaluation — the honest version

Read `docs/BENCHMARKS.md` for the full framing; this is the same account. The
naive lookalike metric is **near-tautological and is NOT a gated headline**:

> **Why `hit@10 = 1.0` proves almost nothing.** Ring members transact around a
> closed cycle, so they are each other's **direct 1-hop neighbours** in the
> transaction graph. Any embedding of that graph clusters 1-hop neighbours *by
> construction*. So "the top-10 lookalikes of a ring member contain another ring
> member" is true essentially for free — it re-measures adjacency, not learned
> structural similarity. It is reported for transparency (`hit_at_10 = 1.0`) and
> deliberately left **out of the gated set**.

The **honest, gated** metrics (`benchmarks/bench_embed_lookalike.py:63`,
`_cohesion_at_k`) are:

| Metric | Definition | Value |
|---|---|---:|
| `embed.structural_hit_at_10` | top-10 contains a same-ring member that is **NOT** a direct transaction partner (≥2 hops in the cycle) | **0.667** |
| `embed.cohesion_recall_at_10` | mean fraction of a ring's *other* members present in the top-10 | **0.761** |

The **structural** metric is the real claim: it excludes each member's direct
counterparties (`bench_embed_lookalike.py:96-101`) so a "hit" must be a
co-conspirator the query never directly traded with — genuine graph-structural
similarity, not adjacency. Note it is measured only over the **30 of 42** planted
members that even *have* a ≥2-hop co-member; in a directed cycle a member's two
counterparties are its cycle-neighbours, so non-adjacent co-members exist only in
rings of length ≥ 4.

**k-sweep** (recorded in `benchmarks/latest.json`, headline hard-data run):

| k | cohesion_recall_mean | naive hit@k | structural hit@k | random-baseline recall |
|---:|---:|---:|---:|---:|
| 3 | 0.500 | 0.833 | 0.233 | 0.000 |
| 5 | 0.588 | 0.952 | 0.433 | 0.000 |
| **10** | **0.761** | **1.000** | **0.667** | 0.000 |
| 25 | 0.958 | 1.000 | 1.000 | 0.034 |

The random baseline (sample k random other GSTINs) recovers ~0 co-members at
k ≤ 10, so the embedding is doing far better than chance — but the honest
structural number at the gated k=10 is **0.667**, not 1.0. Dataset for this run:
497 indexed GSTINs, 3,749 edges, 10 closed planted rings / 42 members, seed 42;
recorded `train_embed ≈ 3.68 s` (the README's sub-second figure refers to a
lighter config).

**Related to the risk engine.** The graph embedding was also wired into an
`MLScorer` for per-GSTIN risk, but the V6.1 ablation found it *subtracted*
discrimination (leave-one-out marginal recon-AUC **−0.049**) and it was **removed
from the default risk composer** (`docs/RISK_ENGINE.md`, `docs/BENCHMARKS.md`).
The embedding earns its place as a **lookalike/discovery aid**, not as a scored
risk signal.

## What "Related Vendors" surfaces in the product

The UI strip (`web/src/components/RelatedVendors/RelatedVendors.tsx`) calls
`GET /api/embed/lookalike/{seed}?k=5` and lists the top-K cosine-similar GSTINs,
each with its similarity (to 3 dp) and a bar, each row clicking through to that
entity's investigation (`/entity/{gstin_id}`). Since V6.4 that endpoint is backed
by the per-reset index (see *Live training* above), so in the demo the strip
resolves live instead of 404-ing to an empty state. When a `ringMembers` set is
supplied, neighbours that are also ring members are highlighted and a
`hits/total ring co-members` badge is shown.

Investigative use: given one suspicious vendor, surface others that occupy a
**similar position in the trade graph** — candidates to pull into the same
investigation, even before any ring is formally detected. The component's own
presenter note frames this as "the embedding found the ring by graph behaviour
alone." Read honestly against the metrics above: that framing is exactly the
near-tautological adjacency effect for *direct* ring partners; the defensible,
non-trivial version of the claim is the **structural** recovery of ≥2-hop
co-members at 0.667. Treat the strip as a **triage/discovery lens**, not proof.

## References

- Grover & Leskovec, "node2vec: Scalable Feature Learning for Networks," KDD 2016
  (biased walker, `p`/`q`; cited as "§3.2" in `walks.py`).
- Perozzi, Al-Rfou & Skiena, "DeepWalk," KDD 2014 (the `p = q = 1` special case).
- Levy & Goldberg, "Neural Word Embedding as Implicit Matrix Factorization,"
  NIPS 2014 (the SGNS ≡ shifted-PMI factorization result this build relies on).
- Vose, "A Linear Algorithm For Generating Random Numbers With a Given
  Distribution," IEEE TSE 1991 (the O(1) alias sampler in `walks.py`).
