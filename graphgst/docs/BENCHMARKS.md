# Graph GST — Benchmarks & Evaluation Methodology

This is the honest account of what every published number means, how it is
measured, and why the V6.1 hardening changed several of them. Read it as a
technical judge would.

## Principles

1. **Ground truth is for scoring only.** No detector reads a planted label.
   Guarded by `benchmarks/evalsafe.py` + `tests/test_eval_no_leakage.py`
   (strips `scenario` / invoice `status` / EWB `phantom` from the scorer
   context; fails loudly if a label token survives).
2. **Determinism.** Seed 42 everywhere; `PYTHONHASHSEED=0` auto-set by the
   runner (Python's hash salt changes set-iteration order → NetworkX SCC /
   walk order → non-reproducible numbers otherwise).
3. **Hard data.** The headline dataset uses the hard generator (rings with
   dropped shared-vehicle/director tells, jittered timing, amount noise;
   25 % broken near-rings; legitimate cyclic-trade hard negatives). A real
   number on hard data beats a perfect number on toy data.
4. **No eval-tuned thresholds.** Where a threshold is needed, it is a fixed
   prior; the honest headline is threshold-free (Average Precision, AUC).

## Headline metrics (gated by `benchmarks/compare.py`)

| Metric | What it measures | Baseline |
|---|---|---:|
| `ring.average_precision` | Threshold-free ranking of detected cycles vs CLOSED planted rings, hard data | 0.971 |
| `ring.f1_at_thresh` | F1 at the fixed 0.45 RingScorer prior | 0.769 |
| `reconcile.micro_f1` | Cascade-aware match of MatchEvents to planted anomalies | 0.961 |
| `reconcile.micro_precision` / `_recall` | components | 0.935 / 0.988 |
| `risk.recon_auc` | Composite risk vs a RING-INDEPENDENT reconciliation-anomaly label | 0.887 |
| `risk.recon_p_at_50` | Precision@50 on the same ring-independent label | 0.74 |
| `embed.structural_hit_at_10` | Top-10 lookalikes contain a NON-adjacent (≥2-hop) same-ring member | 0.667 |
| `embed.cohesion_recall_at_10` | Mean fraction of a ring's other members in top-10 | 0.761 |

Reported but **NOT gated** (transparency): `risk.ring_auc_circular` (0.892 —
circular, re-measures ring detection), `embed.hit_at_10` (1.0 — adjacency,
near-tautological), `ring.recoverability_recall` (1.0 — Johnson finds every
cycle; an upper bound, not detection).

> **Risk band recalibration.** The `LOW`/`MED`/`HIGH`/`CRITICAL` band thresholds
> were recalibrated to the composer's score distribution. The change is
> **rank-invariant** — it moves only band boundaries, not the underlying scores
> or their order — so all 9 gated metrics above are unchanged.

## The three corrections (V6.1)

The audit (`V6_1_TECHNICAL_AUDIT.md`) found three ways the pre-6.1 headlines
were optimistic. Each was corrected, not hidden.

### 1. Ring recall 1.000 → Average Precision 0.971
`ring.recall = 1.0` was **recoverability**: Johnson's algorithm enumerates
*every* cycle, so of course all planted rings appear among the detected
cycles. That is not detection quality. The honest metric is Average Precision
over score-ranked detected cycles against the closed planted rings, measured
on hard data that also contains broken near-rings and legitimate cyclic
communities. AP = 0.971 (the scorer ranks real rings above legit cycles);
the full precision-recall sweep is in the report — at threshold 0.50,
precision 1.0 / recall 0.9 / F1 0.947 with **zero** legit-cycle false alarms.

### 2. Risk AUC 0.937 (circular) → recon-AUC 0.887 (independent)
The old risk label was ring-membership. The composite's biggest term
(RingScorer) reads detected rings, which recover planted rings ~perfectly, so
the AUC re-measured ring detection. The ablation (below) proved it: ring
alone scores AUC 1.000 on that label, and adding any other scorer only
*dilutes* it (which is why "fast mode" looked better). The honest label is
ring-INDEPENDENT: suppliers of planted reconciliation anomalies, ring members
excluded. On it the composite scores AUC 0.887, precision@50 0.74.

### 3. Lookalike Hit@10 1.000 → structural Hit@10 0.667
Ring members transact in a closed cycle, so they are direct 1-hop neighbours;
an embedding of the transaction graph clusters neighbours by construction.
The honest metric counts only same-ring members that are NOT direct
transaction partners (≥2 hops in the cycle): structural Hit@10 = 0.667.

## Ablation study — `benchmarks/ablation/`

`python -m benchmarks.ablation.ablate_risk` measures each risk scorer's
marginal contribution against both labels. It now runs the **shipped composer
weights** (Reconcile 0.35, Ring 0.30, Rules 0.20, Temporal 0.15), so the
marginal-value numbers reflect the configuration that actually ships, not a
uniform-weight probe. Key results (recon label,
leave-one-out marginal AUC): reconcile **+0.055**, rules **+0.070** (both
valuable); ml **−0.049**, propagate **−0.005** (**both hurt**); temporal ≈ 0.

**Consequence:** the default composer (`risk.api.default_composer`) is now
Reconcile + Ring + Rules + Temporal. MLScorer and PropagationScorer were
removed from the default — an "AI" scorer that subtracts signal is not
shippable. They remain importable and measured.

## Running

```bash
python -m benchmarks.run_all                 # full, hard data, gated vs baseline
python -m benchmarks.run_all --fast          # skip nothing meaningful now (ML/Prop already off)
python -m benchmarks.run_all --write-baseline  # after an intentional, verified change
python -m benchmarks.ablation.ablate_risk    # scorer marginal-value study
python -m benchmarks.run_all --difficulty 0  # legacy easy rings (demo parity)
```

Exit code 0 = all gated metrics within ±0.02 of `baseline.json`; 1 =
regression; 2 = a bench crashed.

## Reproducing the demo numbers (easy data)

The reproducible demo (`demo/`) intentionally uses `ring_difficulty = 0` so
its hero ring is byte-stable. Its numbers are NOT the headline benchmark;
they exist to make the 3-minute story deterministic.
