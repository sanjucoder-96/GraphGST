# Phase 3 — Circular Trading Intelligence Engine (Revised)

## What we're building

A composable ring-detection pipeline in `rings/`. It goes cheap-to-expensive:
one $O(V+E)$ SCC pass to shortlist candidate strongly-connected subgraphs;
then bounded Johnson's algorithm inside each SCC to enumerate elementary
cycles up to `hop_max`; then a rotational canonicaliser + SHA-1 hash to
kill duplicates; a temporal window filter; a six-signal scorer; a purely
in-memory counterfactual ("which edge breaks this ring?"); optional
persistence to Neo4j; and optional propagation via personalised PageRank.

## Why SCC first

An SCC guarantees every pair of nodes in it is mutually reachable, so a
cycle can only live *inside* one SCC. Running Johnson on the whole graph
is wasteful; running it on each non-trivial SCC's induced subgraph keeps
the search space tight. We prefer `gds.scc.stream` (Tarjan in-database)
and fall back to `networkx.strongly_connected_components` behind a
capability probe — no `ImportError` gymnastics. The GDS projection
lifecycle is wrapped in try/finally so failures never leak stale graphs.

## Why Johnson (not APOC path expansion, not raw BFS)

Johnson's algorithm enumerates each elementary cycle **exactly once**
using a blocking set to prune already-explored prefixes. NetworkX
exposes it as `simple_cycles(H, length_bound=K)` — the hop bound is
enforced *inside* the recursion, so we never pay for over-length paths.
APOC's `apoc.path.expand` was rejected because it (a) emits every rotation
of a cycle separately, (b) has no elementary guarantee, and (c) has no
native length bound cheap enough to make it competitive.

## Canonicalisation

Johnson can still emit a cycle in any rotation depending on the starting
node. We rotate every cycle to begin at its lexicographically smallest
member, join with `|`, and take the first 16 hex chars of SHA-1 as the
`ring_id`. We use SHA-1 (not `hash()`, which Python salts per-process)
so the id is stable across processes and sessions — a hard requirement
for MERGE-idempotency in Neo4j.

## Why six signals, not one

Any single number can be gamed. C alone flags coincidental refunds; V
alone flags any uniform-priced supplier chain; T alone flags monthly
close-out; N alone flags family-owned business clusters. Six weakly-
correlated signals in [0,1] force a fraud pattern to satisfy several
independent tells before the weighted sum breaks 0.5. The scorer also
returns per-signal contributions so the UI can say *70% of this ring's
score is closure+temporal* — that's what makes it auditable rather than
a black box.

## Closure signal (fixed)

Original bug: `closure_strength = sum(edge.gst_amount) / originated_gst`
included the seed edge in the numerator, making the ratio ≥ 1 for any
ring with a valid seed and always clamping to 1.0. The signal was
effectively binary and did not discriminate real cycles from fraud.

Fix: the numerator now excludes the seed edge — `returned = sum(gst for
e in edges if e is not seed)`. A perfect cycle where all k edges carry
equal GST scores exactly (k-1)/1 clamped to 1.0; a leaky cycle where
downstream edges carry less GST scores <1. The signal now genuinely
measures "of the GST originated, how much came back around".

## Counterfactual break-the-ring (fixed)

For a k-cycle we produce k hypothetical rings, each with one edge
removed, and rescore C, V, T, N under the same weights.

Original bug: closure_strength keyed on the seed edge (leaving
members[0]). Removing the seed always sent C to 0; removing any other
edge left the (broken) closure at 1.0. So the "recommended enforcement
edge" was deterministically the seed edge — a function of lex-order,
not fraud pattern.

Fix (double-barrelled): (a) closure_strength itself is symmetric now
(finding 1). (b) In analyse_break we also re-canonicalise for each
hypothetical: we pick the lex-smallest remaining member whose outgoing
edge is still in the reduced set, and rotate members to start there.
Every removal is scored under the same rules the original ring was
scored under — no residual bias against the seed.

Runtime is O(k²) per ring; trivial for k ≤ 8. **No Neo4j mutation** —
the whole thing runs on an in-memory copy of the edge list.

## Recurrence signal (fixed)

Original bug: `ring_id` is deterministic and MERGE-idempotent, so at
most one Ring node ever exists per pattern. `n_prior` lived in {0, 1},
capping R at ~0.28 and defeating the docstring's claim of "saturating
count of prior sightings".

Fix: the Ring node carries a `sighting_count` property. On MERGE we
`ON CREATE SET sighting_count = 1` and `ON MATCH SET sighting_count =
coalesce(sighting_count, 1) + 1`. `count_prior_multiset` now reads that
property BEFORE upsert, so a ring detected for the k-th time sees
n_prior = k-1. R now saturates as intended: r(3) ≈ 0.63, r(10) ≈ 0.96.

## Duplicate-edge fix in Neo4j load

Original bug: the load query had OPTIONAL MATCH into EWayBill→Vehicle
with no aggregation, producing one row per (invoice, vehicle) pair.
Multi-vehicle invoices duplicated edges, inflating denominators, skewing
value_similarity stdev, blowing the Cartesian product cap, and
double-counting total_gst.

Fix: aggregate with `WITH a, b, i, head(collect(DISTINCT v.vehicle_number))
AS vehicle_id` before RETURN, guaranteeing one row per invoice.

## Persistence errors surface, don't hide

Original bug: every persist call was wrapped in `try: … except
Exception: pass`, so schema violations, wrong types, missing
constraints, or Neo4j downtime looked like success to the caller.

Fix: persistence exceptions are now `logger.exception(...)`-logged with
ring_id context. The API layer re-raises persistence failures so the
HTTP response reflects reality. Read-only helpers (`fetch_seen_members`,
`count_prior_multiset`) still return safe defaults on Neo4j unavailable
because the signals they feed have well-defined "no data" values (0),
but they log the exception so operators see the fallback.

## Persistence + propagation

`persist.py` MERGEs `(:Ring {ring_id})` with scoring components and
sighting_count, then `INCLUDES` each member GSTIN and `CONTAINS` each
ring invoice. Break-edge lives as flat properties on the ring node
because the "removed" edge is a hypothetical, not a real relationship.

`propagate.py` seeds personalised PageRank from confirmed ring members.
The fallback path now returns `{}` when no seeds overlap the graph
rather than silently substituting a plain PageRank — downstream scores
would otherwise carry no relationship to any detected ring.

## Minor fixes

- `sccs_gds`/`_gds_propagate`: projection creation and drop are now
  wrapped in try/finally so failures don't leak stale GDS graphs.
- `_pick_best_combination` greedy fallback: date sort is None-safe
  (`(e['date'] is None, e['date'])`) so materialisation doesn't
  TypeError when some edges lack dates.
