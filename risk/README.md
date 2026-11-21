# risk — Composable Risk Engine (Phase 4)

Every scorer (rules, rings, reconcile, temporal, ML, propagation) is a
class implementing the `Scorer` protocol. Each takes a `ScorerContext`
plus a GSTIN and returns a `ScorerResult(subscore ∈ [0,1], reasons=[Reason])`.
`RiskComposer` runs all scorers, normalizes weights, and produces one
final GSTIN-level risk with a flat, sortable `Reason[]` list that the
investigator UI reads directly.

## Why bother

V5's risk was a single additive integer computed inside one function.
Adding a new signal meant editing that function. Removing one meant
rewriting it. Explaining a score meant reading the code. Phase 4
replaces that with:

- **One `Reason` schema shared across three engines** (`rings/scoring`,
  `reconcile/matcher`, `risk/scorers/*`). Adding a signal = add a
  scorer. Removing one = drop it from the composer's list.
- **Per-scorer, per-reason contribution attribution.** Every visible
  number in the UI Evidence Panel can be traced to the specific
  scorer that produced it and to a Cypher-addressable subgraph.
- **No feature leakage.** The ML scorer uses only structural features
  derived from graph shape and invoice statistics — never the
  rule-based `risk_score` (V5's silent bug).

## Composer

```python
from risk import RiskComposer, ComposerConfig, build_context_from_graph_source
from risk.scorers import RuleScorer, RingScorer, ReconcileScorer, \
                            TemporalScorer, MLScorer, PropagationScorer

composer = RiskComposer(ComposerConfig(scorers=[
    RingScorer(weight=0.35),
    ReconcileScorer(weight=0.20),
    RuleScorer(weight=0.15),
    PropagationScorer(weight=0.15),
    TemporalScorer(weight=0.10),
    MLScorer(weight=0.10),
]))

ctx = build_context_from_graph_source(
    graph_source,
    match_events=events_from_reconcile,
    detected_rings=[r.__dict__ for r in run_pipeline(...)],
)

top = composer.compose_all(ctx)
top[0].score      # 0.87
top[0].band       # 'CRITICAL'
top[0].contributions
# {'rings': 0.30, 'reconcile': 0.14, 'rules': 0.15, 'propagate': 0.12, ...}
top[0].reasons    # list of dicts, sorted by contribution desc
```

## HTTP

- `GET /api/risk/gstin/{gstin_id}` — full composition for one GSTIN
  (score, band, contributions, top reasons).
- `GET /api/risk/summary?limit=50` — top-N GSTINs by composed score,
  plus band histogram.

## Benchmark

`benchmarks/bench_risk_discrimination.py` scores every GSTIN in a
synthetic dataset then computes ROC-AUC + Precision@K on the binary
task "is this GSTIN a planted-ring member". Current numbers live in
`IMPLEMENTATION_LOG.md`.
