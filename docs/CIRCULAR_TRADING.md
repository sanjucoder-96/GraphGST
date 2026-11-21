# Circular Trading Detection

Circular ("carousel" / bill-trading) fraud is the case where a set of GSTINs
issue invoices around a closed loop A→B→C→…→A. Goods may never move; the point
is to manufacture Input Tax Credit (ITC) and paper turnover. This document
describes exactly how Graph GST finds those loops and scores how ring-like they
are. Code: `rings/`.

## Pipeline

```
edges ─► build_digraph ─► compute_sccs ─► enumerate_cycles_in_scc ─► canonicalize
        (rings/enumerate) (rings/scc)    (bounded Johnson)          (rings/canonical)
   ─► materialize_and_filter ─► score_ring (six signals) ─► counterfactual break-edge
      (rings/temporal)          (rings/scoring)             (rings/counterfactual)
   ─► temporal_descriptors ─► DetectedRing
      (rings/temporal_signals)
```

### 1. SCC gate (`rings/scc.py`)
A directed cycle lives entirely inside one strongly-connected component. We
compute SCCs first (Tarjan, via NetworkX) and keep only those of size ≥ 2.
This is the load-bearing optimization: cycle enumeration is exponential in the
worst case, so we never run it on the whole graph — only inside each SCC, which
in real supply graphs are small. A graph with no SCC of size ≥ 2 (a DAG) is
provably ring-free and short-circuits to an empty result.

### 2. Bounded cycle enumeration (`rings/enumerate.py`)
Inside each SCC we enumerate simple cycles with a **hop cap** (`hop_max`,
default 8). This is Johnson's algorithm with a length bound: it lists every
simple directed cycle up to the cap. The cap matters for two reasons —
tractability (unbounded enumeration can blow up on a dense SCC) and semantics
(a 40-hop "ring" is not the fraud typology we are modeling). Cycles longer than
the cap are not reported; `ring.recoverability_recall` in the benchmark checks
that all planted rings fall within the cap.

### 3. Canonicalization (`rings/canonical.py`)
The same loop can be discovered starting from any member (A→B→C→A ==
B→C→A→B). We rotate each cycle to start at its lexicographically-smallest
member and use that as `ring_id`, so a loop is counted once regardless of entry
point. Deduplication happens on this canonical id.

### 4. Materialize + window filter (`rings/temporal.py`)
Each canonical cycle is materialized against the real invoice edges between its
consecutive members, and filtered to a time window (`window_days`, default 30):
a genuine carousel closes quickly. Pairs with no invoice inside the window drop
the cycle.

## The six signals (`rings/scoring.py`)

Every surviving cycle is scored on six signals, each normalized to [0, 1] so
weights compare on equal footing. The final score is a weighted sum (default
weight 1/6 each). **No signal reads a ground-truth label** — every one is a
structural or economic property of the loop itself.

| | Signal | Definition | Fraud intuition |
|---|---|---|---|
| **C** | closure_strength | returned GST ÷ originated GST (seed edge excluded from numerator), clamped [0,1] | A tight refund loop returns ~all the tax it originated |
| **V** | value_similarity | 1 − stdev(amounts)/mean(amounts) | Carousel legs carry near-identical amounts |
| **T** | temporal_compactness | 1 − date_span/window_days | The loop closes fast |
| **R** | recurrence | 1 − exp(−n_prior/τ), τ=3 | This member-multiset has looped before |
| **N** | network_signal | ¼·(shared_vehicle + shared_director + shared_pin_prefix + shared_HSN) | Shared truck/director/pincode/goods across "independent" firms |
| **H** | historical_prior | fraction of members ever seen in a prior ring | Repeat offenders |

### Closure — the one that had a bug, now fixed
The original formula summed **all** edge GST over the seed edge's GST, but the
seed edge was itself in the numerator, forcing the ratio ≥ 1 and clamping every
valid ring to C=1.0 (a dead, binary signal). The corrected formula (documented
at `rings/scoring.py:9`) excludes the seed from the numerator:

```
C = clamp( Σ gst(e≠seed) / gst(seed), 0, 1 )
```

so a balanced k-cycle scores near 1.0 while a leaky loop where downstream hops
carry less GST scores < 1.0 — a real gradient, not a constant.

### network_signal — the "all-unique" trap, now fixed
`_mode_fraction` rescales `(top−1)/(n−1)` instead of `top/n`, so *n distinct
vehicles across n edges* contributes **0**, not 1/n. The naive version silently
injected a false shared-vehicle signal into every ring (`rings/scoring.py:123`).

## Explainability

Every signal's contribution and % share of the final score is returned
(`score_ring` → `contribution`, `share`). The **counterfactual break-edge**
(`rings/counterfactual.py`) reports which single invoice, if removed, drops the
score most — i.e. the edge an investigator should subpoena first. Temporal
descriptors (velocity ₹/day, inter-hop cadence regularity;
`rings/temporal_signals.py`) are attached for investigation but deliberately
**not** folded into the score, to avoid tuning a new term on the eval data.

## Why the honest benchmark is not 1.0

On easy synthetic data every planted ring is a perfect, tell-laden loop and the
scorer trivially separates it. The hardened generator (`datagen/rings_hard.py`)
drops shared-vehicle/director tells per ring, jitters timing, adds amount noise,
plants **broken near-rings** (one edge missing — should NOT fire) and
**legitimate cyclic communities** (real businesses that genuinely trade in a
loop — a hard negative). Against that, threshold-free Average Precision is
**0.971**, and at a fixed 0.50 prior the detector holds precision 1.0 / recall
0.9 with zero legitimate-cycle false alarms. See `docs/BENCHMARKS.md`.

## Reference

- Enumeration: Johnson, "Finding all the elementary circuits of a directed
  graph", SIAM J. Comput. 4(1), 1975.
- SCC: Tarjan, "Depth-first search and linear graph algorithms", 1972.
