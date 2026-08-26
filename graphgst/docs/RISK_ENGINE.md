# Composable Risk Engine

Per-GSTIN risk is not one model — it is a composition of independent
**scorers**, each of which emits a subscore in [0,1] plus a list of
**Reasons** (structured, evidence-linked explanations). A `RiskComposer`
runs them against a shared context and blends them into one score with full
attribution. Code: `risk/`.

## Why composition, not a monolith

A single black-box classifier over graph features would be (a) unexplainable to
an investigator who must justify a notice, and (b) trained on labels we control,
inviting leakage. Composition keeps each piece of evidence first-class: the UI
can show *which* scorer contributed *what* fraction and *why*, and each scorer
can be ablated independently to prove it earns its weight.

## The Scorer protocol (`risk/scorers/base.py`)

```python
class Scorer(Protocol):
    name: str
    weight: float
    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult: ...
```

`ScorerResult = (subscore ∈ [0,1], reasons: list[Reason])`. A scorer that finds
nothing returns `(0.0, [])`. Scorers are pure functions of the shared
`ScorerContext` — no I/O of their own.

### The scorers

| Scorer | Reads (from context) | Subscore |
|---|---|---|
| `ReconcileScorer` | MatchEvent outcomes for the GSTIN's invoices | severity-weighted mean of anomaly outcomes |
| `RingScorer` | detected rings containing the GSTIN | max ring score the GSTIN participates in |
| `RuleScorer` | filing keys, supplier status, self-loops | mean of fired rule-reason weights |
| `TemporalScorer` | invoice timestamps | burstiness / off-hours concentration |
| `MLScorer` | graph embedding neighborhood | **(not in default — see below)** |
| `PropagationScorer` | ring-propagation scores | **(not in default — see below)** |

## Composition semantics (`risk/composer.py`)

1. Registered weights are **normalized to sum 1.0** up front → weights are
   relative priors, not absolute magnitudes.
2. Each subscore is clamped to [0,1] and multiplied by its normalized weight.
3. Contributions are summed into the final `score`.
4. Every Reason is tagged `contribution = reason.weight × scorer.weight`, so the
   UI ranks reasons by their true share of the final.
5. Reasons are deduped by (scorer, name, evidence node) and the top-N returned.
6. A band (LOW / MED / HIGH / CRITICAL) is looked up from the score.

A scorer that raises is logged and skipped — one bad scorer cannot take down the
composite (`composer.py:73`).

## The default composer is the ablation's verdict (`risk/api.py`)

```python
ReconcileScorer(0.35)  RingScorer(0.30)  RuleScorer(0.20)  TemporalScorer(0.15)
```

The pre-6.1 default had **six** scorers including ML and Propagation. The
ablation study (`benchmarks/ablation/ablate_risk.py`) measured each scorer's
marginal contribution against the ring-independent reconciliation-anomaly label:

| Scorer | Leave-one-out marginal recon-AUC |
|---|---:|
| rules | **+0.070** |
| reconcile | **+0.055** |
| temporal | ≈ 0 |
| propagate | **−0.005** |
| ml | **−0.049** |

ML and Propagation *subtracted* discrimination. They were removed from the
default. This is the single most important correctness decision in the risk
engine: **we do not ship an "AI" scorer that makes the answer worse just because
it is called ML.** Both remain importable and are still measured in every
ablation run, so the decision is continuously re-checked, not baked in.

### Why they hurt — and the "fast mode" mystery, solved
The old headline risk-AUC used a ring-**membership** label. `RingScorer` recovers
planted rings almost perfectly, so on that label ring alone scored AUC 1.000 and
**any** added scorer only diluted a perfect detector — which is exactly why
turning scorers off ("fast mode") *raised* the AUC from ~0.937 to ~0.957. The
number was an artifact of a circular label, not a real improvement. Switching to
the ring-independent label (`risk.recon_auc = 0.887`) makes the composite's
value real and measurable, and makes ML/Propagation's negative marginal visible.
Full story in `docs/BENCHMARKS.md` and `docs/V6_1_TECHNICAL_AUDIT.md`.

## Weights are priors, not fitted

The 0.35/0.30/0.20/0.15 weights are **principled priors**: reconciliation is the
strongest single evidence of a concrete compliance failure, ring membership is
confirmed circular structure, rules capture filing/status red flags, temporal
captures burst behaviour. They are **not** grid-searched on the eval set —
tuning weights on the benchmark would be the exact overfitting the audit warns
against. Because the composer normalizes, only their ratios matter.

## Reasons are the product (`risk/reasons.py`)

Every scorer speaks in `Reason(name, weight, detail, evidence)` where `evidence`
points at a concrete node/path (e.g. `GSTIN→FILED→GSTR3B`). This is what makes a
risk score defensible: an officer sees *"7/12 outgoing invoices lack a GSTR-1
filing"* with the graph path, not an opaque 0.83.
