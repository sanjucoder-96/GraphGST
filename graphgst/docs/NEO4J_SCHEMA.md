# Neo4j Schema & Persistence

The operational companion to [`GRAPH_MODEL.md`](./GRAPH_MODEL.md). That document
explains *what the nodes and relationships mean*; this one covers *how the graph
is bootstrapped, constrained, indexed, loaded, read, and reset* — everything you
need to run Graph GST against a real Neo4j database. Every constraint/index
below is created at bootstrap by `seeder.create_constraints()` plus
`risk/materialize.py`, and was verified against the live instance.

> Research prototype on **synthetic** data. Nothing here is real taxpayer data.

## Connecting

Config comes from environment variables, loaded from a gitignored `.env` on
import (`db.py`; `.env.example` documents the shape):

| Var | Local / Docker | Aura |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | `neo4j+s://<id>.databases.neo4j.io` |
| `NEO4J_USERNAME` | `neo4j` | instance user |
| `NEO4J_PASSWORD` | your password | instance password |
| `NEO4J_DATABASE` | `neo4j` | the **named** database (often the instance id) |

`NEO4J_DATABASE` matters: local Neo4j uses the single `neo4j` database, but an
Aura instance exposes a named database (e.g. `38828ec0`). Every session in
`db.py` is pinned to it via `session(database=...)`. All DB access in the
codebase routes through `db.run_query` / `db.run_write`, so this one setting
governs the whole app.

## The knowledge graph in one picture

```
                (Director)                         (Vehicle)
                    ▲                                   ▲
                    │ DIRECTED_BY                        │ USED_VEHICLE
                    │                                    │
   FILED     ┌───(GSTIN)───ISSUED_INVOICE──►(Invoice)──TRANSPORTED_VIA──►(EWayBill)
   ┌─────────┤   supplier                      │  │  │
   ▼         │                    BILLED_TO ◄───┘  │  └──AUTHENTICATED_BY──►(IRN)
(GSTR1)      │   (buyer GSTIN)                     │
(GSTR3B)─SETTLED_BY─►(TaxPayment)   DECLARED_IN ◄──┤
   ▲                                BOOKED_AS ─────┴──►(PurchaseRegister)◄─BOOKED_PR─(GSTIN)
   │
 (GSTR2B)

   ── analytic overlay, written back by the engines ──
   (Ring)──INCLUDES──►(GSTIN)   (Ring)──CONTAINS──►(Invoice)
   (MatchEvent)──ABOUT──►(Invoice)   (MatchEvent)──BY──►(GSTIN)   (MatchEvent)──TO──►(GSTIN)
```

**SOURCE** nodes (`GSTIN, Invoice, GSTR1/2B/3B, TaxPayment, EWayBill, Vehicle,
IRN, PurchaseRegister, Director`) come from the synthetic generator via the
loader. **ANALYTIC** nodes (`Ring, MatchEvent`) are written back by the ring and
reconciliation engines. Full property tables live in `GRAPH_MODEL.md`.

## Constraints (13 uniqueness, from the seeder)

Every source/analytic node type is keyed by a unique business identifier. Created
by `seeder.create_constraints()`, which `loader.load_directory` calls first.

| Label | Key | | Label | Key |
|---|---|---|---|---|
| `GSTIN` | `gstin_id` | | `TaxPayment` | `challan_no` |
| `Invoice` | `invoice_id` | | `EWayBill` | `ewb_id` |
| `GSTR1` | `return_id` | | `Vehicle` | `vehicle_number` |
| `GSTR2B` | `return_id` | | `IRN` | `irn` |
| `GSTR3B` | `return_id` | | `Director` | `director_id` |
| `PurchaseRegister` | `pr_line_id` | | `Ring` | `ring_id` |
| `MatchEvent` | `event_id` | | | |

A **14th** uniqueness constraint, `RiskMeta.id`, is created separately by
`risk/materialize.py` (it keys the singleton risk-materialization stamp), not by
the seeder — so a fully bootstrapped DB carries 14 uniqueness constraints.

Uniqueness is what makes ingestion **idempotent**: every loader uses
`MERGE (n {key: …})`, so re-loading the same dataset updates in place instead of
duplicating (proven in `tests/test_neo4j_integration.py::test_idempotent_reload`).

> **V6.4 removed the dead `:Alert` schema.** Earlier seeders created an `Alert`
> uniqueness constraint (plus `alert_id`/`alert_severity` indexes) for a label no
> code path ever writes. It is gone, not reserved — reinstate it with the feature
> that needs it.

## Indexes (30 range + 2 token-lookup)

A bootstrapped DB carries **30 range indexes** (14 backing the uniqueness
constraints, 16 explicit property indexes) plus Neo4j's **2 built-in
token-lookup** indexes. The seeder creates the source-data property indexes;
`risk/materialize.py` creates the two materialized-risk indexes the case list
rides on.

| Label | Indexed properties | Serves |
|---|---|---|
| `GSTIN` | `status, risk_score, scenario, state` (+ id) | risk/rule filters, dashboards |
| `GSTIN` | `risk_band, risk_score_norm` (materialize.py) | case-list band filter + score sort |
| `Invoice` | `date, hsn, scenario, status` (+ id) | reconciliation, temporal windows |
| `GSTR1/GSTR3B` | `period` (+ id) | filing-period joins |
| `TaxPayment` | `status, payment_date` (+ id) | settlement checks |
| `EWayBill` | `vehicle_number, scenario` (+ id) | shared-vehicle ring signal |

**Case-list hot path (V6.4):** `investigation/service.list_cases` filters and
sorts on `g.risk_score_norm` (the canonical 0–1 score). The new **`gstin_risk_norm`**
index on `GSTIN.risk_score_norm` turns that from a full `NodeByLabelScan` into an
index scan. The band filter is now a **seekable** equality —
`g.risk_band = $band`, added to the query only when a band is actually requested
— so the `gstin_risk_band` index is usable; the previous
`($band IS NULL OR g.risk_band = $band)` disjunction would have defeated it.

**Removed in V6.4:** the `ring_period` index (`:Ring` has no `period` property, so
it indexed nothing) and the `:Alert` indexes (`alert_id`, `alert_severity`),
alongside the `:Alert` constraint above.

**Known redundancy (acceptable):** id properties that already have a uniqueness
*constraint* also carry a backing range *index* — the constraint provides it
automatically, so it is counted above but not created by a separate statement.
The *non-id* property indexes are the ones that matter, and they match the query
patterns in `rings/`, `reconcile/`, `risk/`, and `investigation/`.

## Two write paths: loader (canonical) vs seeder (legacy demo)

The live database has **one** canonical writer: the datagen **loader**
(`datagen/loader.py`, driven by `POST /api/datagen/load`). Everything the risk,
ring, reconciliation, and Case surfaces read is the loader's model — the graph
drawn above.

`seeder.py` is a **separate, small demo path**: nine hand-crafted scenarios
(`POST /api/seed`) built on an older, divergent model — `SUPPLIES_TO` and
`CLAIMS_ITC_FOR` relationships, GSTIN properties like `is_defaulter`,
`incorporation_date`, and a plain `directors` string, plus a state-only address
(no `state_code`). The loader writes none of these: it models supply as
`ISSUED_INVOICE`/`BILLED_TO`, attaches directors as `:Director` nodes via
`DIRECTED_BY`, and stores `incorp_date` + `state_code`.

Because the two models diverge, the legacy `main.py` endpoints that read the
seeder model return empty or null on loader data and are **legacy/deprecated**:

| Endpoint | Reads (seeder-only) | On loader data |
|---|---|---|
| `GET /api/analytics/multi-hop/{gstin}` | `SUPPLIES_TO*` paths, `is_defaulter` | empty `upstream_risks` |
| `GET /api/fraud/circular-gst` | `scenario = 'CIRCULAR_GST_FRAUD'`, `itc_fraud_amount`, `directors` | empty (the loader's ring scenario is `CIRCULAR_TRADING`) |

To keep the two models from mixing, `POST /api/seed?force=true` wipes the graph
(`clear_graph()`) before seeding (V6.4).

## Bootstrap, load, read, reset

```
seeder.create_constraints()          # 13 constraints + 14 range indexes (idempotent, IF NOT EXISTS)
        │
loader.load_directory(dir)           # CSVs → MERGE nodes+rels (dependency order, batched)
        │                            #   └─ _gc_orphans(): DETACH DELETE isolated TaxPayment/PurchaseRegister
rings.engine.load_graph_from_neo4j() # read invoice edges (i.date/i.amount/i.total_gst)
reconcile.engine._hydrate_from_neo4j()# read invoices + filing keys + PR
        │
run_pipeline(persist=True)           # write :Ring + :INCLUDES/:CONTAINS back
run_reconcile(persist=True)          # write :MatchEvent + :ABOUT/:BY/:TO back
```

**Deterministic reset** — `demo/reset.py` (or `DELETE /api/seed`) runs
`MATCH (n) DETACH DELETE n` then reloads, giving a byte-stable graph. The
loader's dependency order (`GSTIN → Invoice → EWB/IRN/PR → returns → payments`)
guarantees endpoints exist before relationships are merged onto them.
`POST /api/seed?force=true` is likewise destructive — as of V6.4 it calls
`clear_graph()` (a full `DETACH DELETE`) **before** seeding, so the legacy seeder
model can never be overlaid on a loader-populated graph.

### Post-load orphan GC (V6.4)

`load_directory` ends with `_gc_orphans()`, which `DETACH DELETE`s any
`TaxPayment` or `PurchaseRegister` node left structurally isolated
(`WHERE NOT (x)--()`). These dangle from load ordering — a `TaxPayment` whose
`GSTR3B` parent row was absent, a `PurchaseRegister` whose `Invoice` was absent —
and would otherwise be counted but never reachable. On the current dataset this
removes about 10 `TaxPayment` and 7 `PurchaseRegister` nodes; `load_directory`
returns the tally as `orphans_removed`.

### The property-name contract (V6.1 fix, V6.2-verified)

Writers store `i.date`, `i.amount`, `i.total_gst`. The ring read query
(`rings/engine.load_graph_from_neo4j`) must read those exact names — an earlier
version read `i.invoice_date`/`i.total_amount`/`i.gst_amount`, which do not
exist, so on the **live** path those came back `null` and silently zeroed the
closure/value signals. Fixed, and now **proven against a real database** by
`tests/test_neo4j_integration.py::test_graph_read_property_fidelity`.

### Temporal serialization (V6.2 fix)

`:Ring` stores `detected_at = datetime()` (a `neo4j.time.DateTime`). FastAPI /
Pydantic cannot JSON-serialize that type, so `GET /api/rings/` and
`/api/rings/{id}` 500'd whenever a ring was persisted. The read queries now
`toString(...)` every temporal property (`rings/persist.py`).

## Example Cypher

```cypher
// Every invoice a supplier issued, with its filing status
MATCH (s:GSTIN {gstin_id: $gstin})-[:ISSUED_INVOICE]->(i:Invoice)
OPTIONAL MATCH (s)-[:FILED]->(g1:GSTR1)  WHERE g1.period = i.period
RETURN i.invoice_id, i.date, i.total_gst, g1 IS NOT NULL AS gstr1_filed
ORDER BY i.date;

// A detected ring and its members + invoices
MATCH (r:Ring {ring_id: $ring_id})
OPTIONAL MATCH (r)-[:INCLUDES]->(g:GSTIN)
OPTIONAL MATCH (r)-[:CONTAINS]->(i:Invoice)
RETURN r.score, r.total_gst, collect(DISTINCT g.gstin_id) AS members,
       collect(DISTINCT i.invoice_id) AS invoices;

// Circular structure directly in Cypher (bounded), for cross-checking the engine
MATCH path = (a:GSTIN)-[:ISSUED_INVOICE]->(:Invoice)-[:BILLED_TO]->
             (b:GSTIN)-[:ISSUED_INVOICE*2..6]->(:Invoice)-[:BILLED_TO]->(a)
RETURN a.gstin_id AS seed, length(path) AS hops LIMIT 10;
```

## Testing tiers (V6.2)

| Tier | Command | Touches Neo4j? |
|---|---|---|
| Unit | `pytest` | No — `pytest.ini` deselects `-m neo4j`; `conftest.py` points the driver at an unreachable localhost |
| Integration | `pytest -m neo4j` | **Yes** — live DB; self-skips if none reachable |
| Benchmark | `python -m benchmarks.run_all` | No — in-memory graph_source |
| Demo | `python -m demo.verify` | No (in_memory) / Yes (`--http`) |

CI runs the unit tier on every push and the integration tier in a dedicated job
against a `neo4j:5-community` service container (`.github/workflows/ci.yml`).

## Beginner explanation

A knowledge graph stores *things* (nodes) and *how they connect* (relationships),
instead of rows in tables. Here a taxpayer (`GSTIN`) *issues* an `Invoice` that is
*billed to* another taxpayer — so "who traded with whom" is a path you can walk,
not a join you reconstruct. Fraud like circular trading is literally a **loop** in
this graph (A→B→C→A), which is why a graph database fits: finding a loop is a
native graph operation, and the six-signal scorer then judges how suspicious each
loop is. Constraints stop duplicate entities; indexes make the lookups fast; the
loader's `MERGE`-everything approach means you can safely re-run it.
