# Graph GST — V6.1 Technical & Research Audit

**Auditor role:** senior Python engineer · graph-algorithms researcher · ML
engineer · fraud-detection researcher · GST-domain reviewer · security
engineer · hackathon technical judge.

**Method:** read the actual implementation (not README claims), reproduce
each concern against the deterministic seed-42 dataset, classify, then fix.

**Verdict up front:** the pipeline has **no ground-truth-label leakage into
features** (verified: no scorer reads `scenario`/`CIRCULAR_FRAUD`). The real
weaknesses are (a) **benchmark circularity** — the risk-AUC label is
ring-membership and the dominant scorer *is* ring detection, so the number
re-measures ring recall rather than independent composite value; (b) an
**unrealistically easy synthetic generator** that inflates every downstream
metric; and (c) **latent label columns** carried (unused) into the scorer
context. All three are corrected in this pass. Where a corrected metric is
lower, the old number was inflated and is replaced, not hidden.

Status legend: ✅ fixed · 🟡 partially fixed / documented · ⬜ open (tracked).

---

## Findings

### F1 — Risk-discrimination AUC is benchmark-circular — **HIGH** ✅

1. **What is wrong.** `bench_risk_discrimination` defines the label as
   *"is this GSTIN a planted-ring member"* and the score as the composed
   risk. The composer's largest term is `RingScorer(weight=0.35)`, which
   reads `ctx.detected_rings` — the rings recovered by the ring engine.
   The ring engine recovers planted rings at ~100 % member recall, so
   `RingScorer(gstin) ≈ 1[gstin ∈ detected ring] ≈ 1[gstin ∈ planted ring]`
   = the label. The AUC therefore largely re-measures ring detection.
2. **Why it matters.** `risk.roc_auc` is presented as evidence that *the
   composite* discriminates fraud. It mostly re-states `ring.recall`, which
   is already a separate headline. It is not an independent measurement.
3. **Effect on Graph GST.** Over-credits the risk composite; makes the
   marginal value of reconciliation/temporal/ML/propagation invisible.
4. **Reproduce.** `python -m benchmarks.run_all` vs `--fast`. Fast mode
   (fewer scorers) yields a *higher* AUC (0.957 vs 0.937) — impossible if
   every scorer added signal; consistent with the ring term dominating and
   the extra scorers diluting it.
5. **Fix.** (a) Add an **ablation harness** (`benchmarks/ablation/`) that
   measures each scorer's *marginal* AUC. (b) Report the risk composite on a
   **ring-independent label** as well (reconciliation-anomaly severity), so
   the composite is judged on signal it doesn't trivially own. (c) Annotate
   the Model Card so `risk.roc_auc` is labelled "ring-dominated" and paired
   with the ablation table. (d) Keep ML/Propagation **off by default** in the
   headline composer until an ablation shows positive marginal value.
6. **Affects a published metric?** Yes — `risk.roc_auc`,
   `risk.precision_at_50/100`. Re-reported with ablation context.

### F2 — ML & Propagation scorers reduce AUC yet ship on by default — **MEDIUM** ✅

1. **What is wrong.** Dropping `MLScorer` + `PropagationScorer` *raises* AUC
   (0.937 → 0.957). They are enabled by default in `risk.api.default_composer`.
2. **Why it matters.** "AI-powered" scorers that measurably subtract signal
   on the only labelled task are the exact anti-pattern the brief forbids.
3. **Effect.** Slower composition (IsolationForest fit + full-graph PPR) for
   a worse number.
4. **Reproduce.** Ablation harness (F1 fix) quantifies each in isolation.
5. **Fix.** Make the **headline/default composer** the 4-scorer set
   (Ring + Reconcile + Rules + Temporal). Keep ML/Propagation available and
   measured; only re-enable in the default when an ablation on the *hardened*
   generator shows they help. Document the decision.
6. **Affects a published metric?** Yes — the reported `risk.roc_auc` becomes
   the honest 4-scorer number, and the ablation records the ML/Prop delta.

### F3 — Embedding Hit@K is near-tautological — **MEDIUM** 🟡

1. **What is wrong.** Planted ring members transact in a closed cycle
   (A→B→C→A), so they are **direct 1-hop neighbours**. An embedding of the
   transaction graph clusters direct neighbours by construction; "ring
   members are each other's nearest lookalikes" is therefore near-trivial.
2. **Why it matters.** The claim sold by `embed.hit_at_10` is *behavioural*
   similarity ("find vendors that behave like a suspect even without a direct
   link"). The current benchmark measures *adjacency*, not behaviour.
3. **Effect.** Overstates the lookalike engine's investigative value.
4. **Reproduce.** Inspect `datagen/rings.py` (head-to-tail edges) and
   `bench_embed_lookalike._cohesion_at_k` (queries same-ring members, which
   are 1-hop).
5. **Fix.** Add a **held-out-edge variant**: remove each queried member's
   direct ring edges from the training graph, retrain, and re-measure. If the
   member still surfaces co-members, that is genuine structural similarity
   (shared counterparties / vehicles), not adjacency. Report both numbers;
   headline the harder one.
6. **Affects a published metric?** Yes — `embed.hit_at_10`,
   `embed.cohesion_recall_at_10` gain a harder companion; the easy number is
   kept but relabelled "adjacency baseline".

### F4 — Planted rings are trivially easy — **HIGH** ✅ (Phase E)

1. **What is wrong.** Every planted ring has perfect closure (C=1.0), a
   shared vehicle, a single shared director, a tight 1-day-per-hop window,
   and geometric per-hop inflation. Real circular trading is noisier and
   partial.
2. **Why it matters.** Ring recall = 1.0 and downstream AUC/Hit@K are
   inflated by data that any rule trivially separates. A perfect score on an
   unrealistic benchmark is worse than a real score on a hard one.
3. **Effect.** All headline numbers are optimistic; ablations can't reveal
   which signals matter because the easy case saturates every signal.
4. **Reproduce.** `datagen/rings.py` — one code path, all tells present.
5. **Fix.** Add difficulty knobs and hard scenarios to the generator
   (partial closure, no-shared-vehicle rings, distinct directors, jittered
   timing, variable amounts, near-rings, broken rings, overlapping rings,
   camouflage/noise edges, legitimate dense communities). Ground truth stays
   deterministic. Re-baseline on the hardened data.
6. **Affects a published metric?** Yes — all of them; re-baselined honestly.

### F5 — Label columns carried (unused) into the scorer context — **MEDIUM** ✅

1. **What is wrong.** `bench_*._load_graph_source` passes full CSV rows into
   `ScorerContext`. Those rows include `gstins.scenario` and
   `invoices.scenario` / `invoices.status = "CIRCULAR_FRAUD"` — direct
   labels. No scorer reads them **today**, but nothing prevents a future
   scorer from doing so, which would be silent leakage.
2. **Why it matters.** Defence in depth for evaluation integrity.
3. **Effect.** Latent; none observed.
4. **Reproduce.** `grep scenario datagen/emitters.py` (column present);
   `grep scenario risk/ embed/` (unused).
5. **Fix.** Strip label columns (`scenario`, ring `status`) in the loaders
   before building the context, and add a **guard test** that fails if any
   label token appears in a `ScorerContext` the benchmark builds.
6. **Affects a published metric?** No (unused today); prevents future
   regressions.

### F6 — RingScorer threshold chosen with eval awareness — **LOW** 🟡

1. **What is wrong.** `RingScorer(min_ring_score=0.45)` references the Phase-3
   F1-vs-threshold sweep (peak at 0.55). A hyperparameter picked while looking
   at the eval curve is mild overfitting to the benchmark.
2. **Fix.** Document it as a fixed, justified prior (not tuned per-run), and
   confirm it is not re-selected on evaluation data. Left as a documented
   constant; revisit if the hardened generator shifts the optimum.
3. **Affects a published metric?** Marginally; noted.

### F7 — Correctness spot-checks (graph/temporal) — **LOW** 🟡

Re-verified in this pass: SCC gate + bounded Johnson canonicalisation
(rotational, SHA-1 stable id), closure signal excludes the seed edge,
counterfactual re-canonicalises per hypothetical, recurrence reads a
persisted `sighting_count`. No new algorithmic defects found. Temporal
signals are shallow (peak-week/median-week ratio) — strengthened in Phase D
rather than "fixed".

---

## Fix log (updated as work lands)

- ✅ F5 — loaders strip label columns; `tests/test_eval_no_leakage.py` guards it.
- ✅ F1/F2 — `benchmarks/ablation/` harness + ring-independent label; default
  composer reduced to the 4 measured-positive scorers.
- ✅ F4 — `datagen` difficulty knobs + hard scenarios (Phase E).
- 🟡 F3 — held-out-edge embedding variant added and reported.
- Re-baselined `baseline.json` / Model Card on hardened data; corrected any
  inflated number in place.

See `IMPLEMENTATION_LOG.md` for the dated, step-by-step record.

---

## Evidence: ablation study (Phase C) — `benchmarks/ablation/risk_ablation.json`

Measured on seed-42 data, PYTHONHASHSEED pinned. Two labels: **ring**
(circular — RingScorer owns it) and **recon** (ring-INDEPENDENT reconciliation
anomaly, 146 positives).

| scorer alone | ring AUC | recon AUC |
|---|---:|---:|
| ring | **1.000** | 0.460 |
| reconcile | 0.459 | **0.974** |
| rules | 0.486 | 0.772 |
| ml | 0.628 | 0.630 |
| propagate | 0.338 | 0.531 |
| temporal | 0.526 | 0.538 |

**Leave-one-out marginal on the recon label** (full − without): removing
`reconcile` = **+0.055** (valuable), `rules` = **+0.070** (valuable), `ml`
= **−0.049** (ML *hurts*), `propagate` = **−0.005** (hurts), `temporal` ≈ 0.

**Add-one-in ladder on the ring label:** starts at 1.000 (ring alone) and
*decreases monotonically* to 0.937 as scorers are added — the fast-mode
"anomaly" fully explained: the extra scorers dilute a trivially-perfect ring
detector. There was never hidden signal; there was hidden dilution.

**Actions taken:** default composer reduced to Reconcile + Ring + Rules +
Temporal (weights 0.35/0.30/0.20/0.15, principled not eval-tuned). ML and
Propagation removed from the default (kept, still measured).

## Corrected metrics (Phase B/E) — old → new, and why

| Metric | Old (inflated) | New (honest) | Why the old was wrong |
|---|---|---|---|
| Ring detection | `ring.recall = 1.000` | `ring.average_precision = 0.971`, `ring.f1@0.45 = 0.769` | Member-multiset recall is a recoverability upper bound (Johnson finds every cycle), not detection. New metric is threshold-free AP on HARD data (dropped tells, broken rings, legit-cycle negatives). Full PR sweep published: at 0.50, precision 1.0 / recall 0.9 / F1 0.947 with zero legit-cycle false alarms. |
| Risk discrimination | `risk.roc_auc = 0.937` | `risk.recon_auc = 0.887`, `risk.recon_p@50 = 0.74` | Old label was ring-membership, which RingScorer trivially owns (circular). New label is ring-independent reconciliation anomalies. Circular AUC still reported as `risk.ring_auc_circular`, NOT gated. |
| Lookalike | `embed.hit_at_10 = 0.912` | `embed.structural_hit_at_10 = 0.667` | Ring members transact in a cycle → direct neighbours → trivially cluster. New metric counts only NON-adjacent (≥2-hop) co-members. Adjacency hit still reported, labelled trivial. |

Net: every headline is now measured on realistic, hard data against a
non-circular label, or is threshold-free. Numbers fell where the old ones
were inflated. That is the correct outcome.
