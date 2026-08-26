# The Investigation Model — Case API & Canonical Risk

Why Graph GST has a **Case API**, why the frontend must not reconstruct an
investigation itself, and how composed risk became the single canonical source.
Introduced in V6.3.

## The problem this solves

Before V6.3 the investigation workspace assembled a "case" *in the browser* from
4+ unrelated endpoints (`/api/graph/full`, `/api/vendors/risk`, `/api/rings/{id}`,
N× `/api/reconcile/audit-trail/{invoice}`) **plus a client-side mock** — the
entity→ring mapping ran against `MOCK_RINGS` in the browser. Meanwhile two
different risk engines were exposed as if equivalent: the legacy
`compute_risk_scores` (0-100 integer, ~9s NetworkX + IsolationForest per request,
never persisted, with a documented feature-leakage bug) and the modern composer
(0-1 float, explainable, live-only). The queue page used one; the investigation
page used the other; they could rank the same GSTIN differently.

Three things were wrong: **the client owned investigation assembly**, **risk had
two contradictory sources**, and **nothing was materialized** so every read paid
full recomputation.

## Canonical risk — one source, materialized

The composable risk engine (`risk/`) is the single source of truth. It is
**materialized** onto each `:GSTIN` node so reads are cheap and consistent:

| Property | Meaning |
|---|---|
| `risk_score_norm` | canonical composed score, 0-1 float |
| `risk_score` | 0-100 integer mirror (keeps the existing range index + any legacy reader working) |
| `risk_band` | `LOW`/`MED`/`HIGH`/`CRITICAL` — one band vocabulary everywhere |
| `risk_reasons_json` | top composed `Reason[]` (preserves attribution) |
| `risk_scored_at` | when this entity was last scored |

`risk/materialize.py` computes the composer once and writes these in a batched
`UNWIND … SET`. The legacy `compute_risk_scores` is **retired as the scoring
authority** — `/api/vendors/risk` now reads the materialized values (≈378 ms vs
~9 s before, 24× faster) and is marked deprecated; only its ITC-validation and
audit-narrative helpers survive.

### Staleness — stale risk can never read as current

A singleton `:RiskMeta` node stores the graph **fingerprint** (counts of
gstins / invoices / rings / events) captured at materialization time. Every risk
and case response carries a `materialization` block whose `stale` flag is
`fingerprint != current_fingerprint`. So if the graph changes without a refresh,
the API says so — it does not silently serve old scores as current.

### When risk is (re)computed

- **On ingestion** — `demo.reset` and `POST /api/datagen/load?refresh=true` call
  `refresh_intelligence()` after loading, so risk is current the moment data lands.
- **On demand** — `POST /api/risk/refresh` (admin) recomputes and re-materializes.
- `refresh_intelligence()` is deterministic (composer is a pure function of the
  graph; `PYTHONHASHSEED=0` fixes the ring engine's SCC order) and clears the
  prior `:Ring`/`:MatchEvent` overlay first, so the persisted intelligence is
  exactly the current detection — no orphans.

## The Case — one coherent investigation object

`GET /api/cases/{gstin_id}` returns, in ONE response, everything the workspace
needs (canonical schemas in `schemas.py`):

```
Case
├─ entity            EntityRef (gstin, name, state, status, scenario)
├─ risk              RiskScore (score 0-1, score_100, band, reasons[], materialized, scored_at)
├─ exposure          ExposureBreakdown (ITC ₹ tied to blocking outcomes, by_outcome)
├─ rings[]           RingSummary (score, band, members, signals, break_edge, temporal, velocity)
├─ reconciliation[]  MatchEventOut (outcome, severity, role supplier|buyer, reasons[])
├─ related_vendors[] RelatedVendor (embedding lookalikes, enriched w/ name+band+shares_ring)
├─ timeline[]        TimelineEvent (date-ordered invoice activity)
├─ subgraph          Cytoscape-shaped 1-hop invoice neighbourhood
├─ investigation_status  open | reviewing | closed
└─ materialization   MaterializationInfo (stale, fingerprint, scored_at)
```

`GET /api/cases` returns a ranked `CaseList` (each row a `CaseListItem` with
risk, band, exposure, ring ids, top reasons) read straight from materialized
risk — a real investigation queue in one indexed read.

### Why the frontend must not assemble the case

- **One source of truth.** If the client stitches a case from many endpoints, it
  re-derives business logic (entity→ring linkage, exposure, severity mapping) that
  belongs in the domain — and drifts from the backend's own numbers.
- **One round-trip, predictable latency.** `GET /api/cases/{id}` is a bounded set
  of `gstin_id`-indexed queries (≈0.5–0.8 s warm against remote Aura), not 6-10
  chained calls each paying its own latency, nor a full-graph transfer to filter
  in the browser.
- **No fixtures masquerading as data.** The old flow fell back to `MOCK_RINGS`
  for entity→ring mapping even when live; the Case API resolves it in Neo4j.
- **Typed contract.** The response is a validated Pydantic model
  (`response_model=Case`), mirrored 1:1 by `web/src/types/case.ts`, so the UI
  gets predictable, strongly-typed data.

The final Investigator UI should consume `getCase(gstin)` and `getCaseList()`
(`web/src/lib/api.ts`) and render — never re-fetch-and-join.

## Layering

```
React (Investigator UI)
   │  getCaseList() / getCase(gstin)          types/case.ts
   ▼
FastAPI  /api/cases                            investigation/api.py   (response_model=Case)
   ▼
Case domain service                            investigation/service.py
   │  targeted, gstin_id-indexed reads + materialized risk
   ▼
Neo4j (source graph + :Ring/:MatchEvent overlay + materialized risk on :GSTIN)
   ▲
Intelligence engines (rings / reconcile / composer / embeddings)
   │  refresh_intelligence() materializes on ingestion & on demand
```

## What is intentionally deferred

Ring-level workflow metadata (assignee, human status transitions), per-date ring
score-evolution series, and enriched shared-asset evidence are modeled in the
schema but not yet fully populated — they are follow-ups for the UI phase, noted
so the contract is stable even before every field is rich.
