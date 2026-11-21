# Graph Model — Neo4j Property-Graph Schema

This document specifies the Neo4j schema Graph GST reads and writes: the node
labels, relationship types, key properties, and the constraints/indexes that
back them. Every element below was read out of the source; the file where each
is created or constrained is cited inline.

> **Disclaimer.** Graph GST is a research/analytics prototype operating on
> **synthetic data** (deterministic seed 42). There is no live GSTN feed and no
> real taxpayer data. The graph models the *shape* of GST filings well enough to
> exercise the detection engines — it is not a faithful reproduction of any real
> GSTN data model, and no output is a compliance determination. See
> `docs/GST_DOMAIN.md` for what is deliberately not modeled.

## Two kinds of nodes

The schema has a hard seam between data that comes **in** and analytics written
**back**:

- **SOURCE nodes** are the synthetic filing records — parties, invoices,
  returns, payments, transport. They are created either by the hand-authored
  demo scenarios (`seeder.py`) or by the bulk CSV loader for generated datasets
  (`datagen/loader.py`).
- **ANALYTIC nodes** — `Ring` and `MatchEvent` — are **derived** and written
  back by the detection engines (`rings/persist.py`, `reconcile/persist.py`).
  They did not exist in the input; they are the product of a pipeline run and
  point back at the source nodes as evidence.

Keeping analytics as first-class nodes (rather than transient API payloads) is
what lets the UI and later pipeline stages traverse *from* a flagged entity *to*
the ring or reconciliation event that flagged it.

## Node labels

Key property = the uniquely-constrained identity field (see
[Constraints](#constraints-and-indexes)). "Created in" cites where `MERGE`/
`CREATE` for that label actually appears.

### Source nodes

| Label | Key property | Meaning (as modeled) | Notable properties | Created in |
|---|---|---|---|---|
| `GSTIN` | `gstin_id` | A registered taxpayer (supplier and/or buyer). | `name`, `state`, `state_code`, `pincode`, `status` (`Active`/`CANCELLED`), `scenario`, `risk_score`, `is_defaulter` | `seeder.py`, `datagen/loader.py:64`, `main.py:443` (user-added) |
| `Invoice` | `invoice_id` | A tax invoice from a supplier to a buyer. | `date`, `hsn`, `taxable_value`/`amount`, `cgst`, `sgst`, `igst`, `total_gst`, `place_of_supply`, `ewb_required`, `period`, `status`, `scenario` | `seeder.py`, `datagen/loader.py:92` |
| `GSTR1` | `return_id` | Supplier's outward-supplies return for a period. | `period`, `filed_date`, `filed_status` | `seeder.py`, `datagen/loader.py:187` |
| `GSTR3B` | `return_id` | Supplier's summary return (liability declared). | `period`, `tax_paid_status`, `tax_paid`, `itc_claimed` | `seeder.py`, `datagen/loader.py:209` |
| `GSTR2B` | `return_id` | Buyer's auto-drafted ITC statement. | `period` | `datagen/loader.py:229` (loader only) |
| `TaxPayment` | `challan_no` | A challan settling declared liability. | `payment_date`, `amount_paid`, `cgst_paid`, `sgst_paid`, `igst_paid`, `bank`, `utr`, `status` (`CLEARED`) | `seeder.py`, `datagen/loader.py:245` |
| `EWayBill` | `ewb_id` | Transport document for goods movement. | `vehicle_number`, `distance_km`, `from_pin`, `to_pin`, `valid_until`, `transporter`, `phantom` | `seeder.py`, `datagen/loader.py:122` |
| `Vehicle` | `vehicle_number` | The truck named on an e-way bill. | (key only) | `datagen/loader.py:132` (loader only) |
| `IRN` | `irn` | Invoice Reference Number (e-invoice registration). | `generated_at`, `portal_status` | `seeder.py`, `datagen/loader.py:146` |
| `PurchaseRegister` | `pr_line_id` | Buyer's own booked record of the purchase. | `buyer_gstin`, `invoice_id`, `booked_date`, `booked_amount`, `booked_tax` | `datagen/loader.py:161` (loader only) |
| `Director` | `director_id` | A named director (common-ownership signal). | (key only) | `datagen/loader.py:77` (loader only) |

### Analytic nodes (written back by detection)

| Label | Key property | Meaning | Notable properties | Created in |
|---|---|---|---|---|
| `Ring` | `ring_id` | A detected circular-trading loop (canonical id). | `score`, `C`, `V`, `T`, `R`, `N`, `H` (the six signals), `hops`, `total_gst`, `date_span_days`, `sighting_count`, `break_edge_*` (flat), `detected_at` | `rings/persist.py:38` |
| `MatchEvent` | `event_id` | One invoice's reconciliation outcome. | `outcome`, `severity`, `delta`, `at`, `reasons_json` | `reconcile/persist.py:40` |

> `Vehicle`, `Director`, `PurchaseRegister`, and `GSTR2B` are produced **only**
> by the CSV loader, not by the demo `seeder.py`. In the seeder scenarios the
> vehicle and directors live as *string properties* on `EWayBill` /`GSTIN`
> (e.g. `EWayBill.vehicle_number`, `GSTIN.directors`); the loader promotes them
> to their own nodes so they can be shared across firms (the `N`/network signal
> depends on that sharing).

## Relationship types

| Relationship | Meaning | Created in |
|---|---|---|
| `(GSTIN)-[:ISSUED_INVOICE]->(Invoice)` | Supplier issued this invoice. | `seeder.py:68`, `datagen/loader.py:107` |
| `(Invoice)-[:BILLED_TO]->(GSTIN)` | Invoice is billed to this buyer. | `seeder.py:68`, `datagen/loader.py:108` |
| `(Invoice)-[:AUTHENTICATED_BY]->(IRN)` | e-invoice registered under this IRN. | `seeder.py:69`, `datagen/loader.py:149` |
| `(Invoice)-[:TRANSPORTED_VIA]->(EWayBill)` | Goods moved under this e-way bill. | `seeder.py:69`, `datagen/loader.py:131` |
| `(EWayBill)-[:USED_VEHICLE]->(Vehicle)` | E-way bill names this vehicle. | `datagen/loader.py:133` (loader only) |
| `(Invoice)-[:DECLARED_IN]->(GSTR1)` | Invoice declared in supplier's GSTR-1. | `seeder.py:70`, `datagen/loader.py:197` |
| `(GSTIN)-[:FILED]->(GSTR1)` | Supplier filed this GSTR-1. | `seeder.py:70`, `datagen/loader.py:193` |
| `(GSTIN)-[:FILED]->(GSTR3B)` | Taxpayer filed this GSTR-3B. | `seeder.py:71`, `datagen/loader.py:217` |
| `(GSTIN)-[:FILED]->(GSTR2B)` | Buyer's GSTR-2B statement. | `datagen/loader.py:233` (loader only) |
| `(GSTR3B)-[:SETTLED_BY]->(TaxPayment)` | Liability settled by this challan. | `seeder.py:71`, `datagen/loader.py:256` |
| `(GSTIN)-[:DIRECTED_BY]->(Director)` | Firm is directed by this person. | `datagen/loader.py:78` (loader only) |
| `(GSTIN)-[:BOOKED_PR]->(PurchaseRegister)` | Buyer booked this purchase line. | `datagen/loader.py:171` (loader only) |
| `(Invoice)-[:BOOKED_AS]->(PurchaseRegister)` | Invoice is booked as this PR line. | `datagen/loader.py:175` (loader only) |
| `(GSTIN)-[:SUPPLIES_TO]->(GSTIN)` | Direct upstream/downstream supply edge for multi-hop default traversal. | `seeder.py:169,229` (seeder only) |
| `(GSTR3B)-[:CLAIMS_ITC_FOR]->(Invoice)` | Buyer's return claims ITC against this invoice. | `seeder.py:72,215` (seeder only) |
| `(Ring)-[:INCLUDES]->(GSTIN)` | Ring membership. | `rings/persist.py:55` |
| `(Ring)-[:CONTAINS]->(Invoice)` | Invoice leg of the ring. | `rings/persist.py:59` |
| `(MatchEvent)-[:ABOUT]->(Invoice)` | Reconciliation event about this invoice. | `reconcile/persist.py:48` |
| `(MatchEvent)-[:BY]->(GSTIN)` | The invoice's supplier. | `reconcile/persist.py:52` |
| `(MatchEvent)-[:TO]->(GSTIN)` | The invoice's buyer. | `reconcile/persist.py:56` |

Two supply-graph edges — `SUPPLIES_TO` and `CLAIMS_ITC_FOR` — are authored only
in the demo `seeder.py`, not emitted by the synthetic generator. `SUPPLIES_TO`
is what the upstream-default propagation query walks
(`MATCH (t)<-[:SUPPLIES_TO*1..n]-(u)`, `main.py:464`; `risk_engine.py:112`);
`CLAIMS_ITC_FOR` links a buyer's GSTR-3B back to the supplier invoice it claims
credit on (`risk_engine.py:216`). On a purely generated dataset those two edge
types are absent.

## Schema diagram

### Core supply / consistency chain (source nodes)

```
        Director                                              Vehicle
           ▲                                                     ▲
           │ [:DIRECTED_BY]                       [:USED_VEHICLE]│
           │                                                     │
     GSTIN (supplier) ──[:ISSUED_INVOICE]──▶  Invoice  ──[:TRANSPORTED_VIA]──▶ EWayBill
        │   │                                  │  │  │
        │   │ [:FILED]                         │  │  └──[:AUTHENTICATED_BY]──▶ IRN
        │   ├──────────────▶ GSTR1  ◀──[:DECLARED_IN]  │
        │   │                                  │        │ [:BILLED_TO]
        │   └──▶ GSTR3B ──[:SETTLED_BY]──▶ TaxPayment   ▼
        │            ▲                            GSTIN (buyer)
        │            │ [:CLAIMS_ITC_FOR]             │
        │            └── (buyer GSTR3B) ◀────────────┤ [:FILED] (GSTR2B/GSTR3B)
        │                                            │
        └──[:SUPPLIES_TO]──▶ GSTIN (buyer)           │ [:BOOKED_PR]
                                                     ▼
                                    Invoice ──[:BOOKED_AS]──▶ PurchaseRegister
```

The intended "clean" chain is: an invoice is issued and billed, authenticated by
an IRN, transported under an e-way bill, declared in the supplier's GSTR-1,
summarized in a GSTR-3B, settled by a TaxPayment, and booked in the buyer's
PurchaseRegister. A break anywhere in that chain is a reconciliation anomaly
(`reconcile/`), and a closed `SUPPLIES_TO`/invoice loop is a circular-trading
candidate (`rings/`).

### Analytic overlay (written back)

```
     ┌──[:INCLUDES]──▶ GSTIN          MatchEvent ──[:ABOUT]──▶ Invoice
  Ring                                    │  │
     └──[:CONTAINS]──▶ Invoice            │  ├──[:BY]──▶ GSTIN (supplier)
                                          │  └──[:TO]──▶ GSTIN (buyer)
```

A `Ring` node hangs off the exact GSTINs and invoices that form the loop; a
`MatchEvent` hangs off the invoice it reconciled plus both parties. Both are
idempotent `MERGE`s on their key, so re-running a pipeline updates in place
rather than duplicating (`rings/persist.py`, `reconcile/persist.py`).

## Constraints and indexes

All uniqueness constraints and range indexes are declared in one place —
`seeder.create_constraints()` (`seeder.py:9`) — and applied before any load
(`datagen/loader.py:287`). A Neo4j uniqueness constraint also creates a backing
index on the key, so key-lookups are covered automatically; the extra range
indexes cover non-key properties the code filters or sorts on.

### Uniqueness constraints (`seeder.py:19-33`)

| Node | Unique property |
|---|---|
| `GSTIN` | `gstin_id` |
| `Invoice` | `invoice_id` |
| `GSTR1` | `return_id` |
| `GSTR3B` | `return_id` |
| `GSTR2B` | `return_id` |
| `EWayBill` | `ewb_id` |
| `IRN` | `irn` |
| `TaxPayment` | `challan_no` |
| `PurchaseRegister` | `pr_line_id` |
| `Director` | `director_id` |
| `Vehicle` | `vehicle_number` |
| `Ring` | `ring_id` |
| `MatchEvent` | `event_id` |
| `Alert` | `alert_id` — **declared but never written** (see gaps) |

The two analytic engines **re-declare** their own constraint at run start so they
are self-sufficient even if `seeder.py` never ran:
`Ring.ring_id` (`rings/persist.py:32`, invoked from `rings/engine.py:184`) and
`MatchEvent.event_id` (`reconcile/persist.py:24`). These are `IF NOT EXISTS`, so
they are harmless duplicates of the seeder declarations.

### Range indexes (`seeder.py:35-50`)

| Node | Indexed properties |
|---|---|
| `Invoice` | `date`, `status`, `scenario`, `hsn` |
| `GSTIN` | `status`, `scenario`, `risk_score`, `state` |
| `EWayBill` | `vehicle_number`, `scenario` |
| `TaxPayment` | `payment_date`, `status` |
| `GSTR1` | `period` |
| `GSTR3B` | `period` |
| `Ring` | `period` |
| `Alert` | `severity` — index on an unwritten label |

Constraint/index creation is best-effort: each statement is wrapped in
`try/except` and a failure is logged at debug level rather than aborting the seed
(`seeder.py:52-56`).

## Honest notes and gaps

A skeptical reader should know these discrepancies between what the schema
*declares* and what the code *writes*:

- **`Alert` is declared but never created.** A uniqueness constraint
  (`alert_id`) and an index (`alert_severity`) exist for `:Alert`
  (`seeder.py:28,50`), but no `MERGE`/`CREATE (:Alert)` appears anywhere in the
  Python backend. It is a reserved/aspirational label, not a live node type.
- **`HAS_EVIDENCE` is documented but not implemented.** The `reconcile/persist.py`
  module docstring describes a
  `(:MatchEvent)-[:HAS_EVIDENCE {reason_name}]->(…)` edge to the cited evidence
  node (lines 5, 13), but the actual `UPSERT_CQL` only writes `ABOUT`, `BY`, and
  `TO` (lines 47-56). Per-reason evidence currently lives in the
  `MatchEvent.reasons_json` string property instead of as edges.
- **Invoice property-name drift in the ring read path — FIXED (V6.1).** The
  Neo4j edge query in `rings/engine.py` previously read `i.invoice_date`,
  `i.total_amount`, and `i.gst_amount`, but the writers (`seeder.py`,
  `datagen/loader.py`) store `date`, `amount`, and `total_gst`. On Neo4j-sourced
  invoices those three fields therefore read as `null`, silently zeroing the
  closure (C) and value (V) ring signals and `total_gst`. It was invisible to
  the test/benchmark suites because they feed an in-memory `graph_source` and
  never exercise this query. The audit corrected the query to read the canonical
  `i.date`/`i.amount`/`i.total_gst` (RETURN aliases unchanged). This remains the
  one path with **no automated test** — it requires a live Neo4j — so it is
  called out here explicitly.
- **Property sets vary by writer.** `GSTIN` from the loader carries
  `state_code`, `pincode`, `sector`, `incorp_date`; the same label from the
  seeder carries `taxpayer_type`, `risk_score`, `is_defaulter`, and a `directors`
  *string*. Treat the node tables above as the union, not a guaranteed-present
  set on every node.
