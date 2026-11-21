# benchmarks — Measurement harness (Phase 7)

Every algorithmic claim in Graph GST is backed by a bench in this
directory. All benches share the same deterministic synthetic dataset
(seed 42, 500 GSTINs, 8 planted rings) so their numbers are directly
comparable and reproducible.

## Individual benches (each runnable standalone)

| Bench | Metric | What it measures |
|---|---|---|
| `bench_ring_recall.py` | recall + F1 | Planted rings recovered by SCC → Johnson pipeline |
| `bench_reconcile_prf.py` | micro P/R/F1 per outcome | Reconciliation classifier accuracy |
| `bench_risk_discrimination.py` | ROC-AUC + Precision@K | Composed risk score discrimination of ring members |
| `bench_embed_lookalike.py` | hit@K + cohesion recall@K | Ring members that surface each other in top-K |

## Unified runner

```bash
python -m benchmarks.run_all
# → generates dataset ONCE, runs all 4 benches, writes latest.json,
#   prints diff vs baseline.json, exits 0/1 based on regression
```

Options:

- `--n-gstins 500 --seed 42 --n-rings 8` — resize the dataset
- `--tolerance-abs 0.02` — how big an absolute drop counts as a regression
- `--write-baseline` — overwrite `baseline.json` with the current run
  (use only after you've verified the numbers deliberately improved)
- `--out latest.json` / `--baseline baseline.json` — path overrides

Exit codes: **0** = all metrics within tolerance, **1** = at least one
regression, **2** = a bench crashed.

## The gated metrics

Any regression on these fails the run:

| Key | Owner |
|---|---|
| `ring.recall` | Phase 3 rings/engine.py |
| `reconcile.micro_f1` | Phase 2 reconcile/matcher.py |
| `reconcile.micro_precision` | Phase 2 |
| `reconcile.micro_recall` | Phase 2 |
| `risk.roc_auc` | Phase 4 risk/composer.py |
| `risk.precision_at_50` | Phase 4 |
| `risk.precision_at_100` | Phase 4 |
| `embed.hit_at_10` | Phase 5 embed/train.py |
| `embed.cohesion_recall_at_10` | Phase 5 |

## HTTP surface

The `/api/benchmarks/*` router (mounted in `main.py`) exposes:

- `GET /latest` — the last recorded report
- `GET /baseline` — the checked-in baseline
- `GET /diff` — headline-metric comparison (JSON version of the CLI table)
- `GET /model-card` — investigator-UI-friendly card list, one per
  headline claim, with `{module, headline, value, unit, baseline,
  delta, status, notes}`
- `POST /run` (admin) — run the bench, write latest, return diff

The React Investigator Console's Model Card page (see `web/src/pages/
ModelCard/`) fetches `/model-card` and renders it as a page of one
data-dense card per claim.

## Regression protocol

When you change a scorer / model / algorithm:

1. Run the affected individual bench for fast feedback.
2. Run `python -m benchmarks.run_all` to see the full diff.
3. If a headline metric REGRESSED, either:
    a. Fix the regression, OR
    b. Explicitly justify the trade-off (e.g. "recall −2% for
        precision +8%") and update the baseline with
        `--write-baseline`, noting the reason in the commit message.
4. Never run `--write-baseline` blindly — the baseline is what
   downstream claims quote.

## Determinism

- `GenerationConfig(seed=42)` — datagen is byte-deterministic.
- `IsolationForest(random_state=42)` — MLScorer is deterministic.
- NetworkX PageRank is deterministic given a fixed graph.
- Python dict iteration order (3.7+) is deterministic.

If you introduce a source of nondeterminism (a new RNG, a
concurrent-map iteration order), tolerance is your only defense —
prefer determinism.
