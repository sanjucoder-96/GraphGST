# Architecture

How a request flows through Graph GST, and where each concern lives. For the
data model see [`GRAPH_MODEL.md`](./GRAPH_MODEL.md) / [`NEO4J_SCHEMA.md`](./NEO4J_SCHEMA.md);
for the investigation contract see [`INVESTIGATION_MODEL.md`](./INVESTIGATION_MODEL.md).

## The layers

```
┌─────────────────────────────────────────────────────────────┐
│ React (Investigator UI)  — web/src                          │
│   getCaseList() / getCase(gstin)     types/case.ts (typed)  │
└───────────────┬─────────────────────────────────────────────┘
                │  HTTP (JSON), mock-fallback when backend down
┌───────────────▼─────────────────────────────────────────────┐
│ FastAPI (main.py + routers)                                 │
│   /api/cases     investigation/api.py   response_model=Case │
│   /api/risk      risk/api.py     (compose live + refresh)   │
│   /api/rings     rings/api.py                               │
│   /api/reconcile2 reconcile/api.py                          │
│   /api/embed, /api/datagen, /api/benchmarks, /api/demo      │
└───────────────┬─────────────────────────────────────────────┘
                │  canonical schemas.py (Pydantic v2)
┌───────────────▼─────────────────────────────────────────────┐
│ Domain services                                             │
│   investigation/service.py   assemble one Case              │
│   risk/materialize.py        compose → write risk to nodes  │
│   risk/hydrate.py            single shared graph hydration  │
└───────────────┬─────────────────────────────────────────────┘
                │  db.run_query / db.run_write (one config, .env)
┌───────────────▼─────────────────────────────────────────────┐
│ Neo4j (Aura or local)                                       │
│   source graph  +  :Ring/:MatchEvent overlay                │
│   materialized risk on :GSTIN  +  :RiskMeta stamp           │
└───────────────▲─────────────────────────────────────────────┘
                │  refresh_intelligence() on ingestion & on demand
┌───────────────┴─────────────────────────────────────────────┐
│ Intelligence engines                                        │
│   rings/ (SCC→Johnson→6-signal)  reconcile/ (16-outcome)    │
│   risk/ composer (Reconcile·Ring·Rules·Temporal)  embed/    │
└─────────────────────────────────────────────────────────────┘
```

Both the Case Queue and the Investigation page consume the Case API (`getCaseList`
/ `getCase`) — the Investigation page was migrated off its old 4-endpoint +
`MOCK_RINGS` assembly (V6.3). Investigation workflow status is a write:
`PATCH /api/cases/{id}` persists `g.investigation_status` in Neo4j.

## Read vs compute

Two deliberately different paths:

- **Cheap indexed reads** — the case list, a case's risk, the dashboard, and the
  (deprecated) vendor list all read **materialized** risk off `:GSTIN` nodes.
  These are the paths the UI hits per interaction; they are sub-second.
- **On-demand recomputation** — `GET /api/risk/summary` and `/api/risk/gstin/{id}`
  compose live (explainable, always current) via the single shared hydrator
  (`risk/hydrate.py`), and `POST /api/risk/refresh` re-materializes. These are
  slower (they hydrate the graph) and are used for refresh / explainability, not
  for every screen paint.

This split is the core of the "avoid full-graph recomputation on every request"
principle: compute once per ingestion/refresh, read many.

## One hydration, one config

- **Config** (`db.py`): every session routes through one driver singleton pinned
  to `NEO4J_DATABASE`, configured from `.env`. There is no second connection path.
- **Hydration** (`risk/hydrate.py`): the risk context is hydrated **once** per
  compose — previously it hydrated the graph three times and dropped the edge
  list (starving TemporalScorer); now one pass feeds reconcile, rings, and the
  neighbour indexes together.
- **Case assembly** (`investigation/service.py`): a case is a bounded set of
  `gstin_id`-indexed reads (entity, rings, events, exposure, timeline, subgraph,
  lookalikes) — not a full-graph fetch filtered in the browser.

## Schemas as the contract

`schemas.py` is the single source of truth for the investigation-path wire
format (Pydantic v2): `Band`, `Reason`, `RiskScore`, `RingSummary`,
`MatchEventOut`, `RelatedVendor`, `ExposureBreakdown`, `TimelineEvent`,
`CaseListItem`, `Case`, `MaterializationInfo`. `web/src/types/case.ts` mirrors it
1:1. The Case API endpoints declare `response_model`, so responses are validated,
not hand-built dicts. (Legacy `main.py` endpoints still return ad-hoc dicts and
are migrated incrementally.)

## Testing tiers

Unit (`pytest`, DB-free) · Integration (`pytest -m neo4j`, live Aura) ·
Benchmark (`benchmarks.run_all`, in-memory) · Demo (`demo.verify`). See
[`NEO4J_SCHEMA.md`](./NEO4J_SCHEMA.md#testing-tiers-v62).
