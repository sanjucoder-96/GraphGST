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
6. A **triage band** (LOW / MED / HIGH / CRITICAL) is looked up from the score
   via `band_for` — see *Triage bands* below.

A scorer that raises is logged and skipped — one bad scorer cannot take down the
composite (`composer.py:73`).

## Triage bands (recalibrated in V6.4) — `risk/reasons.py:band_for`

The bands are **triage brackets, not absolute fraud probabilities** — the amber
"look at this now" queue an officer works down, not a calibrated P(fraud). V6.4
moved every threshold:

| Band | pre-6.4 | V6.4 |
|---|---|---|
| LOW | `< 0.30` | `< 0.15` |
| MED | `< 0.55` | `< 0.30` |
| HIGH | `< 0.80` | `< 0.45` |
| CRITICAL | `≥ 0.80` | `≥ 0.45` |

**Why they moved.** The composer normalizes weights to sum 1.0, so a subscore of
`1.0` on the *heaviest* scorer (reconcile, weight 0.35) contributes only `0.35`
to the final — a single scorer can never push the composite near 1.0. Across a
realistic graph the score maxes around **~0.6** and its median sits near `0`.
Against that distribution the old thresholds were miscalibrated: CRITICAL
(`≥ 0.80`) was **unreachable**, and ~**97%** of true positives were stranded in
LOW. The engine had a genuinely good ranking (recon-AUC ~0.89) but threw the
triage value away by labelling almost everything "low"; the new brackets put the
worst multi-signal entities in HIGH/CRITICAL while keeping the benign mass in
LOW.

**The recalibration is rank-invariant.** It changes no subscore, no weight, and
no gated benchmark metric: AP, AUC, and precision@k are all **threshold-free**
and read the raw score, so they are identical before and after. The model's
ordering of GSTINs is untouched — V6.4 only relabels the brackets drawn over
that ordering.

## The default composer is the ablation's verdict (`risk/api.py`)

```python
ReconcileScorer(0.35)  RingScorer(0.30)  RuleScorer(0.20)  TemporalScorer(0.15)
```

The pre-6.1 default had **six** scorers including ML and Propagation. The
ablation study (`benchmarks/ablation/ablate_risk.py`) measures each scorer's
marginal contribution. As of V6.4 the harness runs the **shipped** composer
weights (reconcile 0.35, ring 0.30, rules 0.20, temporal 0.15) rather than an
older ring-heavy set, so its headline reflects the config that actually ships
(the old weights understated the shipped 4-scorer recon-AUC). The leave-one-out
marginals against the ring-independent reconciliation-anomaly label (`recon`)
are:

| Scorer | Leave-one-out marginal (recon-AUC) | Note |
|---|---:|---|
| reconcile | **+0.078** | strongest non-ring signal (single recon-AUC 0.97) |
| rules | **+0.056** | filing / supplier-status red flags |
| temporal | **−0.002** | ≈ 0 — coverage prior, see below |
| ring | **−0.040** | but **+0.351** on the `ring` label — it owns ring detection |
| propagate | **−0.005** | excluded |
| ml | **−0.046** | excluded (single recon-AUC 0.63) |

`ring` subtracts a hair on the ring-*independent* label (it cannot see non-ring
fraud) yet dominates the `ring` label it exists to catch (+0.351) — that split
is why it earns 0.30 in the default while being scored on both labels.

ML and Propagation *subtracted* discrimination. They were removed from the
default. This is the single most important correctness decision in the risk
engine: **we do not ship an "AI" scorer that makes the answer worse just because
it is called ML.** Both remain importable and are still measured in every
ablation run, so the decision is continuously re-checked, not baked in. They are
also **not** made conditional — there is no "turn ML on when X" heuristic:
MLScorer alone reaches only recon-AUC **0.63** with a leave-one-out marginal of
**−0.046**, and PropagationScorer is **−0.005**; no measured regime exists in
which either improves the composite, so a conditional path would add surface
area with no payoff.

### TemporalScorer stays at 0.15 — a coverage prior, not a fitted weight
Temporal's measured leave-one-out marginal is ≈ 0 (**−0.002** on recon), yet it
is **kept** in the default at weight 0.15. This is a deliberate **coverage
prior**, not a tuned weight: it guards burst-issuance fraud — many invoices
fired in a tight window / off-hours — that the *synthetic generator
under-plants*, so the eval set barely exercises the signal. Its weight is a
prior on a threat we expect in production, explicitly **not** grid-searched
against the eval set (grid-searching would zero it out and blind the engine to a
real-world pattern the benchmark happens not to contain). Because the composer
normalizes, carrying a near-zero-marginal prior costs the other scorers only a
small, bounded share.

### Why ML/Propagation hurt — and the "fast mode" mystery, solved
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
confirmed circular structure, rules capture filing/status red flags, and
temporal is a coverage prior for burst behaviour (see *TemporalScorer stays at
0.15* above). They are **not** grid-searched on the eval set —
tuning weights on the benchmark would be the exact overfitting the audit warns
against. Because the composer normalizes, only their ratios matter.

## Reasons are the product (`risk/reasons.py`)

Every scorer speaks in `Reason(name, weight, detail, evidence)` where `evidence`
points at a concrete node/path (e.g. `GSTIN→FILED→GSTR3B`). This is what makes a
risk score defensible: an officer sees *"7/12 outgoing invoices lack a GSTR-1
filing"* with the graph path, not an opaque 0.83.
