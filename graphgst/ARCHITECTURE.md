# Graph GST V6 — Architecture

This document describes the target architecture. Phases build toward it incrementally; nothing here should be implemented ahead of its dependencies. Each phase's actual state lives in `IMPLEMENTATION_LOG.md`.

---

## 1. Design principles

1. **The graph is the reasoning layer, not a JOIN.** Every derived fact (a reconciliation outcome, a detected ring, a risk score) is a first-class node connected to its evidence. This means downstream analytics can traverse *between* facts and evidence in a single Cypher pattern — something an SQL system cannot express cleanly.
2. **Every claim is measurable.** No metric appears in the UI unless it is computed from real data. Precision/recall are reported only against synthetic ground truth (Phase 1) or against manually labeled subsets.
3. **Every alert is explainable.** Each alert carries a `Reason[]` list; each reason points at a Cypher-addressable subgraph. UI reason chips are clickable and highlight the exact nodes/edges that produced them.
4. **Small, composable, testable modules.** Each Python module ≤ 500 LOC ideally; each has tests; each is importable without side-effects.
5. **Nothing is hard-coded that pretends to be intelligence.** No literal `xai_confidence`. No fake progress bars. No no-op "retrain" buttons.

## 2. High-level topology

```
                    ┌─────────────────────────────────────────────────┐
                    │  DATA SOURCES                                   │
                    │  (a) Synthetic generator (with truth.json)      │
                    │  (b) User uploads: GSTR-1/2B/3B, PR, EWB CSVs    │
                    │  (c) Legacy seeder (SC1..SC9)                    │
                    └────────────────────┬────────────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────────────┐
                    │  INGESTION                                      │
                    │  parsing · dedup · validation · batching        │
                    └────────────────────┬────────────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────────────┐
                    │  TEMPORAL KNOWLEDGE GRAPH (Neo4j 5 + GDS + APOC)│
                    │  Nodes: GSTIN, Invoice, GSTR-1, GSTR-3B,        │
                    │         GSTR-2B, TaxPayment, EWayBill, IRN,     │
                    │         PurchaseRegister, Director, Vehicle,    │
                    │         MatchEvent, Ring, Alert                 │
                    │  Time: date properties + monthly rollup nodes   │
                    └────────────────────┬────────────────────────────┘
                                         │
      ┌───────────────┬──────────────────┼──────────────────┬───────────────────┐
      ▼               ▼                  ▼                  ▼                   ▼
 Reconciliation  Cycle Engine      Risk Engine        Graph ML            Explainability
   2.0            (SCC → Johnson    (composable         (node2vec,          (evidence
   (MatchEvent    → 6-signal        Reason[] with       vendor kNN,         subgraph
    nodes,         → Ring nodes,    contributions       link prediction     per Reason,
    fuzzy match)   temporal +       + optional ML       — after Phase 1     templated NL)
                   counterfactual)  scorers)             truth exists)
      │               │                  │                  │                   │
      └───────────────┴──────────────────┼──────────────────┴───────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────────────┐
                    │  FASTAPI                                        │
                    │  reconcile · rings · risk · investigate         │
                    │  datagen · alerts · counterfactual · replay     │
                    └────────────────────┬────────────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────────────┐
                    │  INVESTIGATOR UI                                │
                    │  Case Queue · GSTIN Investigate · Ring Explorer │
                    │  Temporal Replay · Evidence Panel · Draft SCN   │
                    └─────────────────────────────────────────────────┘
```

## 3. Node types (target schema, V6)

| Node | Key | Notes |
|---|---|---|
| `GSTIN` | `gstin_id` | Taxpayer. Adds `pan`, `state_code`, `incorp_date`, `sector`. |
| `Invoice` | `invoice_id` | Adds `hsn`, `taxable_value`, `cgst`, `sgst`, `igst`, `total_gst`, `place_of_supply`, `date` (as date), `ewb_required`. |
| `GSTR1` | `return_id` | Supplier outward-supply return. |
| `GSTR2B` | `return_id` | System-generated buyer ITC auto-populated. NEW in V6. |
| `GSTR3B` | `return_id` | Monthly summary + tax paid. |
| `TaxPayment` | `challan_no` | Cleared tax remittance. |
| `IRN` | `irn` | e-Invoice authentication. |
| `EWayBill` | `ewb_id` | Logistics record. |
| `PurchaseRegister` | `pr_line_id` | Buyer's book — new first-class node in V6. |
| `Director` | `director_id` | Shared-director shell-cluster signal. NEW in V6. |
| `Vehicle` | `vehicle_number` | Shared-vehicle circular-ring signal. NEW in V6. |
| `MatchEvent` | `event_id` | Reconciliation outcome. NEW in V6. |
| `Ring` | `ring_id` | Persisted detected cycle. NEW in V6. |
| `Alert` | `alert_id` | User-visible finding. Carries `severity`, `confidence`, `Reason[]`. NEW in V6. |
| `MonthlyStats` | (gstin, period) | Materialized time-series rollup. NEW in V6. |

## 4. Relationship types

Same as V5, extended:

- `(GSTIN)-[:ISSUED_INVOICE]->(Invoice)-[:BILLED_TO]->(GSTIN)`
- `(Invoice)-[:AUTHENTICATED_BY]->(IRN)`
- `(Invoice)-[:TRANSPORTED_VIA]->(EWayBill)`
- `(Invoice)-[:DECLARED_IN]->(GSTR1)`
- `(GSTIN)-[:FILED]->(GSTR1|GSTR3B|GSTR2B)`
- `(GSTR3B)-[:SETTLED_BY]->(TaxPayment)`
- `(GSTR3B)-[:CLAIMS_ITC_FOR]->(Invoice)`
- `(Invoice)-[:LISTED_IN]->(GSTR2B)` — NEW
- `(Invoice)-[:BOOKED_AS]->(PurchaseRegister)` — NEW (buyer-side)
- `(GSTIN)-[:DIRECTED_BY]->(Director)` — NEW
- `(EWayBill)-[:USED_VEHICLE]->(Vehicle)` — NEW
- `(Invoice|GSTIN|Ring)-[:HAS_MATCH_EVENT]->(MatchEvent)` — NEW
- `(Ring)-[:INCLUDES]->(GSTIN|Invoice|EWayBill)` — NEW
- `(Alert)-[:ABOUT]->(GSTIN|Invoice|Ring)` — NEW
- `(Alert)-[:HAS_EVIDENCE]->(*)` — NEW; points at any node cited by any Reason

## 5. Temporal model

- Every `Invoice` has a proper `date` (Neo4j `date` type, not string) — enforced at ingestion.
- Monthly rollups `MonthlyStats {gstin_id, period, tx_count, out_value, in_value, tax_paid, tax_collected}` are materialized by a scheduled Cypher job.
- The Circular Trading Engine (Phase 3) uses `date` to bound cycle detection to a rolling window (default 30 days) and to detect same-day / rapid-return patterns.

## 6. Circular Trading Intelligence Engine (Phase 3)

A pipeline, not a single query:

1. **Stage-1 SCC gate** — Tarjan SCC over the invoice projection via GDS. Only non-trivial SCCs proceed.
2. **Stage-2 bounded cycle enumeration inside each SCC** — APOC `apoc.path.expandConfig` with `uniqueness: RELATIONSHIP_PATH`, `maxLevel: 12` (≈ 6 hops). Canonicalized cycles (rotate to lexicographically smallest starting GSTIN) to dedup rotational duplicates.
3. **Stage-3 temporal filter** — drop cycles whose edge-date span exceeds a configurable window (default 30 days).
4. **Stage-4 six-signal scoring** for each survivor:
   - **C** — closure strength = returned_value / originated_value
   - **V** — value similarity = 1 − stdev(edge_amounts) / mean(edge_amounts)
   - **T** — temporal compactness = 1 − date_span / window_size
   - **R** — recurrence = number of times the same participant multiset appears in the historical `Ring` store
   - **N** — network embedding density (shared Vehicle, Director, PIN cluster)
   - **H** — historical prior (any participant appeared in a confirmed ring before)
5. **Stage-5 Ring persistence** — `MERGE (r:Ring {ring_id: canonical_hash})` with score components, then `MERGE (r)-[:INCLUDES]->(gstin_or_invoice)` for each ring element.
6. **Stage-6 counterfactual** — for each survivor, remove each edge in turn (in-memory) and recompute the score to identify the "break point" edge with the largest score drop.
7. **Stage-7 propagation** — personalized PageRank via GDS seeded from confirmed ring members, colouring "ring-adjacent" GSTINs.

## 7. Reconciliation Engine 2.0 (Phase 2)

- Emits `MatchEvent` nodes (`outcome`, `delta`, `at`) linked to both sides (supplier declaration and buyer PR / GSTR-2B). Reconciliation state becomes queryable via graph patterns, not join tables.
- Full outcome taxonomy: `MATCHED`, `PARTIAL_MATCH`, `AMOUNT_MISMATCH`, `TAX_MISMATCH`, `DATE_MISMATCH`, `HSN_MISMATCH`, `POS_MISMATCH`, `MISSING_IN_GSTR1`, `MISSING_IN_GSTR2B`, `MISSING_IN_PR`, `DUPLICATE`, `NEAR_DUPLICATE`, `CANCELLED_SUPPLIER`, `INVALID_GSTIN_FORMAT`.
- Fuzzy matchers: token-sort ratio on invoice-id, ±₹1 / ±0.1 % on amount, ±3 days on date.
- Both directions: supplier→buyer and buyer→supplier.

## 8. Risk engine (Phase 4)

Composable scorers, each producing `Reason[]`:

- `RuleScorer` — the current additive rule engine, cleaned.
- `CycleScorer` — reads persisted `Ring` node scores.
- `TemporalScorer` — burst detection, sudden neighbor growth.
- `MLScorer` — IsolationForest / LOF trained on real features (NOT `risk_score`).
- `PropagationScorer` — personalized PageRank mass from confirmed rings.

Final GSTIN score = weighted sum with reason-level contribution attribution. Weights are configurable and displayed in the UI.

## 9. Graph ML (Phase 5)

- **node2vec** embeddings via GDS → stored on GSTIN nodes.
- **Vendor lookalike** = cosine k-NN in embedding space; UI: "5 vendors that behave like this one".
- **Link prediction** (later) — missing invoice hypothesis for high-embedding-similarity pairs.

## 10. Investigator UI (Phase 6)

Single React app. Deprecates the vanilla shell once ready. Pages:

- **Case Queue** — ranked open alerts, sortable by `severity × exposure × confidence`.
- **GSTIN Investigate** — header risk card with Reason chips; k-hop neighborhood graph; reconciliation summary; historical risk sparkline; related alerts; notes.
- **Ring Explorer** — Cytoscape canvas of the ring with amounts on edges; timeline scrubber for temporal replay; six-signal gauges; "break the ring" counterfactual; shared-vehicle/director badges.
- **Temporal Replay** — timeline scrubber over an entity's whole neighborhood.
- **Evidence Panel** — right-hand drawer, always available; clicking a Reason chip highlights its subgraph.
- **Data Health** — ingestion counts per source, dedup stats.
- **Draft Notice** — SCN template that reads real failing hops (no hard-coded amounts).

## 11. Benchmarks (Phase 7)

Every algorithmic claim must have a reproducible benchmark. See `benchmarks/`:

- Reconciliation P/R/F1 per outcome type on synthetic truth.
- Cycle recall (planted rings recovered / planted) and FP rate.
- Risk model AUC + Precision@K.
- Latency curves on 10K / 100K / 1M invoices.

## 12. Frontend consolidation

The React app in Hack_Me/src/ was a stub with mock-data fallbacks and is dropped in V6. Phase 6 will re-introduce a single React app in a `web/` sibling folder built with Vite. The vanilla shell in `pages/` + `assets/` is the demo frontend until Phase 6 lands, and its known-fake elements (agent.js no-op feedback, splash timers, decorative Cypher) are being removed in Phase 0.

---

**Owner:** Lead engineer.
**Status:** Living document. Update whenever a phase ships.
