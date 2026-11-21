# Graph GST — Documentation Index

Written for a strong beginner CS student and a skeptical technical reviewer.
Every claim is grounded in code; where a number was once optimistic, the
correction is stated openly rather than hidden.

## Start here

- **[V6_1_TECHNICAL_AUDIT.md](./V6_1_TECHNICAL_AUDIT.md)** — the audit that drove
  the V6.1 hardening: findings by severity, the three metric corrections, the
  ablation evidence, and the old→new metric table.
- **[BENCHMARKS.md](./BENCHMARKS.md)** — what every published number means, how
  it is measured, why three headlines changed, and the ablation methodology.

## Architecture & investigation model

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — request-flow layering: React →
  FastAPI → Case API → domain services → Neo4j + engines; read-vs-compute split.
- **[INVESTIGATION_MODEL.md](./INVESTIGATION_MODEL.md)** — the Case API, why the
  frontend shouldn't reconstruct investigations, and canonical materialized risk.

## The engines

- **[CIRCULAR_TRADING.md](./CIRCULAR_TRADING.md)** — SCC gate → bounded Johnson
  enumeration → six-signal scoring → counterfactual break-edge.
- **[RECONCILIATION.md](./RECONCILIATION.md)** — matching invoices to the filing
  chain, the fuzzy matchers, the MatchEvent/Reason contract, micro-F1 0.961.
- **[RISK_ENGINE.md](./RISK_ENGINE.md)** — the composable Scorer protocol, why
  ML/Propagation were dropped, and how Reasons make a score defensible.
- **[GRAPH_ML.md](./GRAPH_ML.md)** — random walks → SPPMI → exact SVD → cosine
  lookalike (pure numpy), and the honest structural Hit@10.

## The data & domain

- **[GRAPH_MODEL.md](./GRAPH_MODEL.md)** — Neo4j node labels, relationships,
  constraints; SOURCE vs ANALYTIC nodes; known schema discrepancies.
- **[NEO4J_SCHEMA.md](./NEO4J_SCHEMA.md)** — operational schema: connecting,
  constraints/indexes (live-dumped), bootstrap/load/read/reset, example Cypher,
  and the unit vs integration vs benchmark vs demo test tiers.
- **[GST_DOMAIN.md](./GST_DOMAIN.md)** — the GST concepts modeled (GSTR-1/3B,
  ITC, the 16-outcome taxonomy) and an explicit line around what we do NOT claim.

## Operations

- **[API.md](./API.md)** — every HTTP endpoint, params, and the admin-token auth model.
- **[SECURITY.md](./SECURITY.md)** — threat model, controls, and known limitations.
- **[FRONTEND_REDESIGN_V2.md](./FRONTEND_REDESIGN_V2.md)** — the "SIGNAL" design
  system: why editorial was rejected, the visual philosophy, and the live-data wiring.
- **[../ARCHITECTURE.md](../ARCHITECTURE.md)** — system-level architecture (repo root).

## Reproduce the evidence

```bash
python -m pytest -q                       # 217 tests
python -m benchmarks.run_all              # full gate vs baseline.json (exit 0 = pass)
python -m benchmarks.ablation.ablate_risk # scorer marginal-value study
python -m demo.reset --no-neo4j && python -m demo.verify   # reproducible demo
```

> Set `PYTHONHASHSEED=0` for bit-identical benchmark numbers (the runner does
> this for you; it matters because Python's hash salt changes set-iteration
> order, which perturbs SCC/walk order).
