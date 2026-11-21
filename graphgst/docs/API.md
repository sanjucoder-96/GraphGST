# Graph GST — HTTP API Reference

The backend is a single **FastAPI** app (`main.py`, `title="GraphGST V6"`,
`version="6.0.0"`). It exposes ~48 endpoints: a core set defined directly on
the app (no prefix) plus seven optional routers, each mounted under `/api/<name>`
only if its package imports cleanly. A router that fails to import is logged and
skipped — the rest of the API still serves — so the exact surface depends on
which phases are installed.

- **Base URL (dev):** `http://localhost:8000`
- **Interactive docs:** `/docs` (Swagger UI) and `/redoc`; schema at `/openapi.json`. Enabled by default.
- **Data:** everything is **synthetic** (hand-seeded scenarios or the generator in `/api/datagen`). This is a demo / research backend, not production.
- **Persistence:** Neo4j. Most read endpoints run Cypher directly; see [Neo4j-down behaviour](#conventions).

## Auth model

There is exactly one privilege level: **admin**, proven by an `X-Admin-Token`
request header that must equal the server's `ADMIN_TOKEN` env var. The check is
constant-time (`hmac.compare_digest`) and **fails closed**: if `ADMIN_TOKEN` is
unset the guarded endpoint returns **503** (disabled), not open access; a
missing/wrong token returns **401**. Read-only analytics endpoints are
unauthenticated by design.

Full threat model, path-safety rules, and known limitations live in
[`SECURITY.md`](./SECURITY.md) — this reference only states which endpoints are
guarded. The endpoints requiring admin are:

`DELETE /api/seed`, `POST /api/seed`, `POST /api/invoices`,
`PATCH /api/cases/{id}`, `POST /api/datagen/generate`,
`POST /api/datagen/load`, `POST /api/embed/train`, `POST /api/benchmarks/run`,
`POST /api/demo/reset`, `POST /api/reconcile2/run` (only when `persist=true`),
`POST /api/rings/detect` (only when `persist=true` or `propagate=true`), and
`POST /api/risk/refresh`.
Every guard is the shared, constant-time `security.require_admin`.

## Conventions

- **CORS:** origins from `CORS_ORIGINS` (default `http://localhost:3000,:5173,:8080`); methods `GET,POST,DELETE`; headers `Content-Type,X-Admin-Token`; credentials allowed. Never `*` in the shipped default.
- **Request bodies** are JSON, validated by Pydantic models (typed fields, defaults as noted per endpoint). Query ints that feed Cypher are clamped.
- **503 when `ADMIN_TOKEN` unset** on every admin endpoint (fail-closed). **503 on `/api/risk/*`** when the risk context cannot be hydrated from Neo4j (`"risk context unavailable"`).
- **Neo4j down, elsewhere:** `GET /api/health` degrades gracefully (`status: "degraded"`, HTTP 200). The other core read endpoints call Cypher with no guard, so an unavailable database surfaces as an unhandled **500** rather than a 503. The `/api/risk/*` router is the one that explicitly returns 503.
- **404** is returned by lookup endpoints when the entity/artifact is absent (e.g. unknown `ring_id`, no trained embeddings, no `latest.json`).

---

## Core — health, seed, feedback (`main.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | none | Service banner `{message, status, docs}`. |
| GET | `/api/health` | none | Neo4j connectivity + node/relationship counts (no longer returns `neo4j_uri`). Always 200; `status` is `healthy` or `degraded`. |
| GET | `/api/seed/status` | none | `{has_data, node_count}` — used by the UI to show/hide the seed button. |
| POST | `/api/seed` | **admin** | Seed the 9 hand-crafted scenarios; requires `X-Admin-Token`. Query `force: bool = false`. Idempotent when `force=false`; **`force=true` wipes the graph first**. Returns `{message, seeded, skipped, results[]}`. |
| DELETE | `/api/seed` | **admin** | `MATCH (n) DETACH DELETE n` — wipe the entire graph. |
| POST | `/api/agent/feedback` | none | Append an auditor-feedback record to `feedback.jsonl` with a server timestamp. Returns `{stored, at}`. |

**`POST /api/agent/feedback` body** (`FeedbackRecord`): `label: str`
(`accurate` \| `false_positive` \| `missed_fraud` \| `notice_approved`),
`query: str = ""`, `intent: str = ""`, `subgraph_node_ids: list[str] = []`,
`comment: str = ""`.

## Graph & dashboard (`main.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/graph/full` | none | Whole graph as Cytoscape `{nodes, edges, stats}`, with per-node/edge CSS classes for fraud/mismatch styling. |
| GET | `/api/dashboard/summary` | none | Aggregate tiles: `node_counts`, `itc` (total/eligible/blocked/matched/mismatch), `tax_payments`, `vendor_risk` bands, `scenarios[]`. |

## Reconciliation — legacy (`main.py`)

The original V5 reconciliation surface, kept alive for the existing UI. The
newer engine lives at [`/api/reconcile2`](#apireconcile2--reconciliation-20-phase-2).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/reconcile` | none | ITC validation results (`get_itc_validation_results()`). |
| GET | `/api/reconcile/audit-trail/{invoice_id}` | none | Human-readable audit narrative for one invoice (`generate_audit_narrative`). |

## Fraud detection (`main.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/fraud/circular` | none | Circular-trading rings via `MATCH path=(a)-[:ISSUED_INVOICE*2..5]->(a)`. Returns `{rings_detected, rings[], cypher_used}`. |
| GET | `/api/fraud/circular-gst` | none | Dedicated SC9 "Circular GST Fraud" analysis: `{scenario, description, entities[], invoices[], ewb_flags[], total_itc_fraud, ring_size, common_vehicle, detection_method}`. |
| GET | `/api/fraud/phantom-ewb` | none | E-Way Bills sharing a vehicle + validity window (`{phantom_shipments[], count}`). |
| GET | `/api/fraud/cancelled-gstin` | none | Invoices issued by `CANCELLED` GSTINs (`{invoices[], count}`). |

## Vendors & risk model (`main.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/vendors/risk` | none | **DEPRECATED (V6.3).** Now serves the **materialized composer risk** off GSTIN nodes (`summary.model_used = "composer/v1 (materialized)"`, ~378 ms), not the old ~9 s NetworkX+IsolationForest recompute. Superseded by [`/api/cases`](#apicases--canonical-case-api-v63) and `/api/risk/summary`. Kept until the Investigation page migrates. |
| GET | `/api/vendors` | none | Flat GSTIN list with invoice count + total GST, ordered by `risk_score` desc. Effectively dead from the UI. |
| GET | `/api/risk-engine/model-status` | none | Orphaned info about the legacy IsolationForest `.pkl` (the composer deliberately does not ship it). |

> **V6.3:** `compute_risk_scores` is retired as the scoring authority. The
> composable [`/api/risk`](#apirisk--composable-risk-engine-phase-4) engine is
> the single canonical source, materialized onto GSTIN nodes; the dashboard and
> `/api/vendors/risk` read those materialized values. See
> [`INVESTIGATION_MODEL.md`](./INVESTIGATION_MODEL.md).

## `/api/cases` — Canonical Case API (V6.3)

The coherent investigation object — the frontend consumes these instead of
reassembling a case from 6-10 endpoints. Typed via `schemas.py` (mirrored by
`web/src/types/case.ts`); both declare a `response_model`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/cases/` | none | Ranked `CaseList` from materialized risk. Query `band` (LOW/MED/HIGH/CRITICAL), `min_score: float=0`, `limit: int=100` (1..1000), `q` (free-text). Each row: `risk_score` (0-1), `band`, `exposure_inr`, `ring_ids`, `top_reasons`, `investigation_status`. Cheap indexed read (~1.5 s). |
| GET | `/api/cases/{gstin_id}` | none | One `Case`: `entity`, `risk` (score/band/reasons/`materialized`), `exposure`, `rings[]` (each with its per-hop `edges[]`), `reconciliation[]`, `related_vendors[]`, `timeline[]`, `subgraph`, `investigation_status`, `materialization`. **404** if the entity is absent. One coherent request (~0.5-0.8 s warm). Query `subgraph: bool=true`. |
| PATCH | `/api/cases/{gstin_id}` | **admin** | Persist the investigation workflow status onto the graph; requires `X-Admin-Token`. Body `{status}` ∈ `open|investigating|escalated|resolved|dismissed` (`CaseStatusUpdate`). Returns `CaseStatusResult {case_id, investigation_status, updated_at}`. **422** on an invalid status; **404** if the entity is absent. The status is real Neo4j state (`g.investigation_status`) and is read back by GET. |

Every GET response carries a `materialization` block with a `stale` flag so
stale risk is never served as current.

## Invoices (`main.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/invoices` | none | Full invoice list joined to supplier/buyer, GSTR-1/3B, tax payment, EWB. |
| POST | `/api/invoices` | **admin** | Create an invoice + upsert its supply chain in Neo4j; derives GST split and a reconciliation `status`. Requires `X-Admin-Token`. |

**`POST /api/invoices` body** (`InvoiceCreate`): `supplier_gstin`,
`supplier_name`, `buyer_gstin`, `buyer_name`, `invoice_id`, `amount: float`,
`invoice_date` (all required); `tax_rate: float = 0.18`, `hsn: str = "9999"`,
`description: str = ""`, `has_ewb: bool = true`,
`supplier_filed_gstr1: bool = true`, `supplier_filed_gstr3b: bool = true`,
`tax_payment_cleared: bool = true`. Returns `{message, invoice_id, status,
gst_amount, chain_complete}`. `status` is derived (`MISSING_GSTR1` /
`MISSING_GSTR3B` / `MISSING_TAX_PAYMENT` / `MISSING_EWB` / `MATCHED`).

## Analytics (`main.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/analytics/scenarios` | none | Invoice counts + GST-at-risk grouped by scenario/status. |
| GET | `/api/analytics/multi-hop/{gstin_id}` | none | Upstream supply-chain risk. Query `depth: int = 3`, **clamped to 1..5** before it feeds the var-length Cypher. |
| GET | `/api/analytics/tax-payments` | none | GSTR-3B → TaxPayment reconciliation per GSTIN with a derived `final_status`. |

## GraphRAG Audit Copilot (`main.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/agent/query` | none | Natural-language audit copilot. Classifies intent, pulls the relevant subgraph from Neo4j, and returns structured intelligence. |

**`POST /api/agent/query` body** (`AgentQuery`): `query: str` (required),
`language: str = "en"` (`"en"` or `"hi"`), `gstin_id: str | None = null`.
**Response:** `{intent, query, subgraph{nodes,edges}, insights[], scenario,
hindi_summary, draft_notice, counterfactual, xai_confidence,
xai_confidence_method, graph_nodes_queried, legal_provisions[], next_action}`.
Notes: `intent` is keyword-matched (English + Hindi triggers); `draft_notice`
(a Section-74 SCN) is generated **only** when a live `CIRCULAR_GST_FRAUD` ring
exists in the graph — its amounts/GSTINs come from Neo4j at request time, not a
template; `xai_confidence` is an honest interim heuristic
(`n_evidence / (n_evidence + 3)`), not a calibrated probability.

---

## `/api/rings` — Circular Trading Engine (Phase 3)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/rings/detect` | **conditional** | Run the full ring-detection pipeline and return scored rings. **Admin required only when `persist=true` or `propagate=true`** (both mutate Neo4j). |
| GET | `/api/rings/` | none | List persisted rings, filtered. Query `min_score: float = 0.0` (0..1), `limit: int = 100` (1..1000). |
| GET | `/api/rings/{ring_id}` | none | Fetch one persisted ring; **404** if unknown. |

**`POST /api/rings/detect` body** (`DetectRequest`): `hop_max: int = 8`
(2..16), `window_days: int = 30` (1..365), `weights: dict[str,float] | null =
null`, `use_gds: bool = true`, `persist: bool = false`, `propagate: bool = false`,
`horizon_days: int | null = null`. **Response:** a list of ring objects —
`{ring_id, members[], invoices[], hops, date_span_days, total_gst, score,
signals{}, contribution{}, share{}, break_edge}`.

> **Auth (V6.1 hardening):** both write flags default to `false`, so the
> default call (and the frontend's `{hop_max, window_days}` request) is a pure
> read that needs no token. Setting `persist=true` or `propagate=true` requires
> a valid `X-Admin-Token` (checked by the shared `security.require_admin`
> before the engine runs), matching `/api/reconcile2/run`. An earlier version
> defaulted both flags to `true` with no guard — an unauthenticated write path
> that has been closed; see `docs/SECURITY.md`.

## `/api/reconcile2` — Reconciliation 2.0 (Phase 2)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/reconcile2/run` | **conditional** | Run the reconciliation pipeline and return MatchEvents. **Admin required only when `persist=true`.** |
| GET | `/api/reconcile2/events` | none | List persisted events. Query `outcome: str | null = null`, `limit: int = 100` (1..1000). |
| GET | `/api/reconcile2/summary` | none | Outcome/severity counts via a live re-run (no persistence). |

**`POST /api/reconcile2/run` body** (`RunBody`): `persist: bool = false`,
`include_matched: bool = false`, and tolerances `amount_abs: float = 1.0`,
`amount_rel: float = 0.001`, `date_days: int = 3`, `invoice_id_jw: float = 0.90`.
**Response:** `{count, by_outcome{}, by_severity{}, events[], truncated}` — the
`events` array is capped at 500 (`truncated` flags overflow); the full set
persists to Neo4j when `persist=true`.

## `/api/risk` — Composable Risk Engine (Phase 4)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/risk/gstin/{gstin_id}` | none | Composed risk for one GSTIN with full scorer attribution (live compose). **404** if absent; **503** if the context can't be hydrated. |
| GET | `/api/risk/summary` | none | Ranked GSTINs + band counts + a `materialization` block. Live compose. Query `limit: int = 50` (1..1000). **503** if context unavailable. |
| POST | `/api/risk/refresh` | **admin** | **(V6.3)** Materialize composed risk onto the graph — the canonical "make risk current" op. Query `persist_intelligence: bool=true` (also detect+persist rings and reconcile+persist events first). Returns rings/events persisted + gstins scored + fingerprint. |
| GET | `/api/risk/materialization` | none | **(V6.3)** Materialization stamp + live staleness verdict (`stale`, `fingerprint` vs `current_fingerprint`, `materialized_at`, `n_scored`). |

The default composer blends four scorers — Reconcile (0.35), Ring (0.30),
Rules (0.20), Temporal (0.15). `MLScorer` and `PropagationScorer` are
importable but **excluded from the default** after the ablation showed negative
marginal value (see [`RISK_ENGINE.md`](./RISK_ENGINE.md) and
[`BENCHMARKS.md`](./BENCHMARKS.md)). `/summary` returns `{count, band_counts{LOW,
MED, HIGH, CRITICAL}, top[]}`; each item is the same object as `/gstin/{id}`,
**enriched (V6.2) with `name`, `state`, `scenario`, `status`** from the entity
node so a client can render an investigation queue without a second call. This
is the queue's primary source (the web Case Queue reads it via `getCases`) —
~2.6s against remote Aura vs ~9s for the legacy `/api/vendors/risk`, which
recomputes IsolationForest + centrality per request.

> **V6.2 fix:** `GET /api/rings/` and `/api/rings/{id}` previously returned a
> raw `neo4j.time.DateTime` for `detected_at`/`last_scored_at`, which FastAPI
> could not serialize (500 whenever a ring was persisted). The read queries now
> `toString(...)` every temporal property, so these fields are ISO-8601 strings.

## `/api/embed` — Node2Vec Lookalikes (Phase 5)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/embed/train` | **admin** | Retrain node embeddings from the live graph, persist artifacts. CPU-heavy, synchronous. |
| GET | `/api/embed/lookalike/{gstin_id}` | none | Top-K cosine-similar GSTINs. Query `k: int = 5` (1..100). **404** if no model is trained yet. |
| GET | `/api/embed/status` | none | `{trained}` and, when trained, `n_indexed`, `config`, `stats`, `saved_at`, `shape`, plus a `stale` flag and `graph_fingerprint`. |

**`POST /api/embed/train` body** (`TrainBody`): `dim: int = 64`,
`walks_per_node: int = 10`, `walk_len: int = 20`, `window: int = 5`,
`neg_k: int = 5`, `p: float = 1.0`, `q: float = 1.0`, `seed: int = 42`.
Returns `{trained, n_indexed, stats, artifacts}`.

## `/api/datagen` — Synthetic Data Generator (Phase 1)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/datagen/generate` | **admin** | Run the generator; write a dataset dir; return counts + planted-truth totals. |
| POST | `/api/datagen/load` | **admin** | Load an existing generated dir into Neo4j. Query `dir` (**required**), path-checked by `resolve_within`; **400** on traversal, **404** if not a directory. |
| GET | `/api/datagen/truth` | none | Read `truth.json` from a generated dir. Query `dir` (**required**), same path-safety; **404** if `truth.json` is absent. |
| GET | `/api/datagen/status` | none | List directories under the server CWD that contain a `truth.json`. |

**`POST /api/datagen/generate` body** (`GenerateBody`): `n_gstins: int = 1000`,
`months: int = 6`, `normal_share: float = 0.90`, `recon_issue_share: float =
0.06`, `circular_share: float = 0.03`, `duplicate_share: float = 0.01`,
`n_rings: int = 15`, `ring_size_min: int = 3`, `ring_size_max: int = 8`,
`seed: int = 42`, `out_dir: str = "./datagen_output"`. Returns `{ok, out_dir,
counts, planted_rings, planted_anomalies}`.

> **Auth (V6.1 hardening):** this router now imports the shared, constant-time
> `security.require_admin` (`hmac.compare_digest`), consistent with every other
> router and with `SECURITY.md`. It previously used a local `!=` token compare,
> which was timing-variable; that has been replaced.

## `/api/benchmarks` — Evaluation Harness (Phase 7)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/benchmarks/latest` | none | Latest recorded bench report (`latest.json`). **404** if none. |
| GET | `/api/benchmarks/baseline` | none | Checked-in baseline (`baseline.json`). **404** if none. |
| GET | `/api/benchmarks/diff` | none | Baseline-vs-latest comparison (same shape as the CLI). **404** if no latest. |
| GET | `/api/benchmarks/model-card` | none | Investigator-UI card summarising the gated headline metrics. **404** if no latest. |
| POST | `/api/benchmarks/run` | **admin** | Run the full suite (fixed 500-GSTIN / seed-42 config), write `latest.json`, return the diff. Takes ~10s of CPU; **no request body**. |

`model-card` returns `{generated_at, git_commit, dataset_config,
tolerance_abs, overall_pass, cards[]}` where each card is `{module, metric,
headline, value, baseline, delta, status, unit, notes}`. Metric definitions
and gating live in [`BENCHMARKS.md`](./BENCHMARKS.md).

## `/api/demo` — Reproducible Demo (Phase 8)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/demo/status` | none | Current demo state, or `{initialized: false, hint}` if not yet reset. |
| GET | `/api/demo/story` | none | Narrator script + hero ring + per-step expectations (`story_json()`). |
| GET | `/api/demo/hero` | none | The hero ring's canonical properties (`{hero_ring}`). |
| POST | `/api/demo/reset` | **admin** | Rebuild demo artifacts. Query `load_neo4j: bool = true`; `false` regenerates CSVs only and leaves the graph untouched. |
| GET | `/api/demo/verify` | none | Run the story verifier; returns `{exit_code, ...}` (`exit_code` 0 when every assertion holds). |
