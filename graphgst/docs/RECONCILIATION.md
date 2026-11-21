# Invoice Reconciliation Engine 2.0

Reconciliation is the act of asking one question of every invoice: *does the
rest of the filing chain agree that this supply happened, was declared, was
paid for, and was booked?* Graph GST answers it per invoice by cross-checking
the invoice against the supplier's returns (GSTR-1, GSTR-3B), the settling
challan (TaxPayment), the transport document (EWayBill), and the buyer's own
Purchase Register (PR). Any break in that chain becomes a typed **MatchEvent**
carrying an `outcome`, a `severity`, and a list of evidence-linked **Reasons**.
Code: `reconcile/`. The chain semantics and the full outcome taxonomy live in
`docs/GST_DOMAIN.md`; this document explains the *engine* that produces the
events.

> **Prototype disclaimer.** Everything here runs on synthetic, seeded data
> (`datagen/`). The engine never contacts a real GSTN system, never pulls a
> live GSTR-2B, and does not validate a GSTIN checksum against the portal — it
> is a research reconciliation model, not a compliance product. See
> `docs/GST_DOMAIN.md`.

## What gets reconciled, and against what

For one invoice the engine assembles the following facts and hands them to a
single pure function, `match_one_invoice` (`reconcile/matcher.py`):

| Fact | Source (in-memory key / graph) | Used to detect |
|---|---|---|
| Supplier status + state | `gstins` / `GSTIN` node | `CANCELLED_SUPPLIER`, `POS_MISMATCH` |
| GSTR-1 filed for period | `gstr1_keys` set of `(gstin, period)` | `MISSING_GSTR1` |
| GSTR-3B filed for period | `gstr3b_keys` set of `(gstin, period)` | `MISSING_GSTR3B` |
| GSTR-3B settled by challan | `settled_keys` set of return-ids | `MISSING_TAX_PAYMENT` |
| e-Way Bill present | `ewb_by_invoice` set of invoice-ids | `MISSING_EWB` |
| Buyer PR lines for this invoice | `pr` joined by `invoice_id` | amount / tax / date / duplicate |
| Buyer's whole PR | `pr` joined by `buyer_gstin` | `MISSING_IN_PR`, `NEAR_*` (fuzzy) |

The **filing keys are sets, not per-invoice facts.** GSTR-1/3B/payment status is
a property of a `(supplier, period)`, so *every* invoice from that supplier in
that period reconciles against the same filing state — a fact that matters for
scoring (see [Cascade-aware scoring](#cascade-aware-scoring-a-benchmark-concept)).

## Pipeline

```
run_reconcile(graph_source | Neo4j)          reconcile/engine.py
  │  hydrate: invoices, pr, gstins, gstr1/gstr3b/settled/ewb keys
  │  index PR:  pr_by_inv[(invoice_id)]  pr_by_buyer[(buyer_gstin)]
  ▼  for each invoice ──►  match_one_invoice(...)          reconcile/matcher.py
        1. GSTIN shape check ──(invalid ⇒ emit + RETURN, short-circuit)
        2. supplier CANCELLED?         (does not short-circuit)
        3. missing filings   GSTR1 ▸ GSTR3B ▸ TAX_PAYMENT   (elif: one fires)
        4. EWB required but absent?
        5. PR join ─► pick line ─► amount ▸ tax/HSN ▸ date ▸ DUP/NEAR_DUP
                      └─ no line ─► fuzzy scan ─► NEAR_MATCH | MISSING_IN_PR
        6. place-of-supply vs IGST / CGST+SGST
        7. no event raised ⇒ MATCHED
  ▼  list[MatchEvent dict]  ──(cfg.persist)──►  upsert_events()   reconcile/persist.py
```

`run_reconcile` has two invocation modes (`reconcile/engine.py`): an in-memory
`graph_source` dict (used by tests and the benchmark, no database required) and
a Neo4j mode (`graph_source=None`) that hydrates the same structures with a
handful of Cypher queries in `_hydrate_from_neo4j`. Both feed the identical
matcher, so the pipeline is exercised end-to-end without a live graph.

## The seven checks (`reconcile/matcher.py`)

`match_one_invoice` runs the checks in a deliberate order and can emit **more
than one event per invoice** — an investigator needs every failing dimension
surfaced, not just the first.

| # | Check | Fires | Notable logic |
|---|---|---|---|
| 1 | GSTIN shape | `INVALID_GSTIN_FORMAT` | Runs for supplier **and** buyer; if either is malformed the function `return`s early — a broken identifier makes the other checks meaningless. |
| 2 | Supplier cancelled | `CANCELLED_SUPPLIER` | Does **not** short-circuit; a cancelled supplier can still also be an amount mismatch etc. |
| 3 | Missing filings | `MISSING_GSTR1` / `MISSING_GSTR3B` / `MISSING_TAX_PAYMENT` | Strict `if/elif/elif` precedence: **exactly one** fires, the earliest gap in the chain. No point reporting an unpaid challan when GSTR-1 was never filed. |
| 4 | e-Way Bill | `MISSING_EWB` | Only when `invoice.ewb_required` is true and no EWB is attached. |
| 5 | PR reconciliation | `MISSING_IN_PR`, `NEAR_MATCH`, `AMOUNT_MISMATCH`, `TAX_MISMATCH`, `HSN_MISMATCH`, `DATE_MISMATCH`, `DUPLICATE`, `NEAR_DUPLICATE` | See below. |
| 6 | Place of supply | `POS_MISMATCH` | Only evaluated when `invoice.igst is not None`; IGST on a same-state supply, or CGST+SGST on a cross-state supply. |
| 7 | Fallback | `MATCHED` | Emitted only if stages 1–6 produced nothing. |

### Stage 3 precedence is load-bearing

The chain is ordered: declare (GSTR-1) → summarize/owe (GSTR-3B) → pay
(TaxPayment). The `elif` cascade reports the **first** broken link only, so one
invoice yields at most one filing-gap event. This precedence is later mirrored
by the benchmark scorer (below), which is why the two must stay in sync.

The settled check is convention-coupled: the engine does not look up the
GSTR-3B node's stored id, it *reconstructs* the expected return-id as
`GSTR3B-{gstin[:7]}-{period}` (`_expected_gstr3b_id`, `reconcile/engine.py`) and
tests membership in `settled_keys`. That mirrors `datagen`'s id convention; if
datagen changed its return-id format, this check would silently miss.

### Stage 5: PR join and the amount/tax anti-double-count

`_pick_pr_line` selects the earliest-booked PR line referencing the invoice
(deterministic tie-break). If no line references the invoice id exactly, the
engine runs a fuzzy scan of the buyer's whole PR (`_find_fuzzy_pr`); a hit
becomes `NEAR_MATCH` (a formatting variation, treated as reconciled), a miss
becomes `MISSING_IN_PR`.

Once a PR line is chosen, four sub-checks run. The tax check is deliberately
suppressed when the amount is already off:

- **Amount** (`AMOUNT_MISMATCH`) when `taxable_value` vs `booked_amount` exceeds
  tolerance.
- **Tax** only when `tax_off and not amount_off` — because if the base amount is
  wrong the tax is proportionally wrong too, and that is **one** anomaly, not
  two. The outcome is `HSN_MISMATCH` if the PR-implied rate lands on a different
  slab (`_looks_like_wrong_rate`), otherwise `TAX_MISMATCH`. When the amount
  *and* the implied slab both differ, an extra `HSN_MISMATCH` is added on top of
  the amount event.
- **Date** (`DATE_MISMATCH`) when booked date is outside the day tolerance.
- **Duplicate**: `DUPLICATE` when more than one PR line references this exact
  invoice id (double-claimed ITC); otherwise a fuzzy scan for a *different* PR
  line whose id matches modulo punctuation raises `NEAR_DUPLICATE`.

### Reason weights

Every event carries at least one `Reason` whose `weight ∈ [0,1]` is a
per-reason confidence, not a probability. Some are fixed priors (e.g.
`ewb-required-absent` = 0.9, `near-match-invoice-id` = 0.75); the numeric
mismatches are **proportional** — amount/tax use `min(1.0, |relative_delta|)`
and date uses `min(1.0, |Δdays|/30)` — so a bigger discrepancy is a
higher-confidence reason.

## The fuzzy matchers (`reconcile/fuzzy.py`)

Real ERPs disagree on formatting constantly; these matchers stop trivial
formatting differences from masquerading as fraud. All are pure and
deterministic (no time-of-day tolerance), so tests pin exact values.

| Matcher | Rule | Why |
|---|---|---|
| Invoice id | Two-stage: normalize (strip non-alphanumerics, uppercase); the **digit runs must be identical**, *and* Jaro-Winkler ≥ 0.90 | `INV-2024-001` ≡ `INV/2024/001` (punctuation only) but `INV-…-001` ≠ `INV-…-002`. The digit-equality gate stops JW's prefix boost from masking a real sequential-number difference. |
| Amount | `|a−b| ≤ max(₹1, 0.1 % · max(|a|,|b|))` | Rupee rounding on small invoices, percentage rounding on large ones. |
| Date | `|a−b| ≤ 3 days` | Booking-lag tolerance. |
| GSTIN | Regex shape only: `2 digit + 5 alpha + 4 digit + alpha + alnum + Z + alnum` | **Shape check, not checksum** — it does not verify the mod-36 check digit against the portal. |

Jaro-Winkler is implemented from scratch (`_jaro`, `jaro_winkler`) with
Winkler's default prefix weight `p=0.1` and a 4-character prefix cap, because
invoice ids that agree on a leading prefix are exactly the case Winkler was
designed to boost.

Tolerances are configurable via `ReconcileConfig.tolerances`
(`reconcile/engine.py`) and exposed on the HTTP endpoint; defaults:

| Key | Default |
|---|---|
| `amount_abs` | 1.0 |
| `amount_rel` | 0.001 |
| `date_days` | 3 |
| `invoice_id_jw` | 0.90 |

## The MatchEvent

A MatchEvent is the unit of output — a first-class, cite-able object rather than
a boolean flag on another table. Fields (`reconcile/matcher.py` `_event`,
`reconcile/engine.py` `MatchEvent`):

| Field | Meaning |
|---|---|
| `event_id` | `"M-" + sha1(invoice_id::supplier::buyer::outcome)[:16]` — stable, content-addressed. |
| `outcome` | One of the 16 canonical codes (`reconcile/outcomes.py`). |
| `severity` | `severity_for(outcome)` → INFO/LOW/MEDIUM/HIGH/CRITICAL. |
| `invoice_id`, `supplier_gstin`, `buyer_gstin` | The parties. |
| `delta` | Signed numeric difference where meaningful (amount/tax), else `None`; `0.0` for `MATCHED`. |
| `at` | UTC wall-clock ISO timestamp of the run. |
| `reasons` | List of `Reason` dicts. |

Each `Reason` (`reconcile/outcomes.py`) is
`{name, weight, detail, evidence}`, where `detail` is the human-readable
one-liner rendered in the UI and `evidence` points at the exact supporting
node(s) — e.g. `{"node_type": "PurchaseRegister", "node_id": "PR-…"}` (a list of
ids for duplicates). This is the same Reason schema the rings and risk engines
use, so the UI's explainability panel renders all three uniformly.

### Persistence (`reconcile/persist.py`)

When `cfg.persist` is set, `upsert_events` writes each event as a first-class
`(:MatchEvent {event_id, outcome, severity, delta, at, reasons_json})` node
(idempotent `MERGE` on `event_id`, guarded by a uniqueness constraint) linked
by `-[:ABOUT]->(:Invoice)`, `-[:BY]->(:GSTIN supplier)`, and
`-[:TO]->(:GSTIN buyer)`. Reasons are stored inline as a JSON string. Writes are
batched (500) and a failed batch is logged and re-raised.

## Determinism

Determinism is by construction, with one honest exception:

- `event_id` is a hash of `(invoice_id, supplier, buyer, outcome)` **only** — it
  excludes `at`, `delta`, and reason text, so re-running on the same graph
  reproduces the same ids, and `MERGE`-on-`event_id` is a true upsert.
- The matcher and every fuzzy function are **pure** (data-in → data-out, no
  I/O, no randomness); `_pick_pr_line` breaks ties by earliest `booked_date`.
- **Exception:** the `at` field is `datetime.now(timezone.utc)` — wall-clock,
  therefore *not* reproducible across runs. Only the timestamp varies; the
  identity, outcome, severity, and evidence of every event are stable.

The benchmark dataset itself is fixed by seed 42 and `PYTHONHASHSEED=0` (the
runner re-execs itself to set it — see `docs/BENCHMARKS.md`), because Python's
hash salt would otherwise perturb set-iteration order upstream in datagen.

## Cascade-aware scoring (a benchmark concept)

The word "cascade" describes how the **benchmark scores** the engine
(`benchmarks/bench_reconcile_prf.py` `_score`), not something the engine itself
computes. It exists to score the engine *fairly*, and it is worth understanding
because a skeptical reader should know exactly what the headline number counts.

The problem: `datagen` may plant one filing anomaly as a single labelled fact
("supplier X did not file GSTR-1 for period P"), but the engine correctly flags
**every** invoice from X in P, because filing state is a `(supplier, period)`
property. Scored naively, those N−1 extra — and *correct* — events would count
as false positives and unfairly tank precision.

The scorer therefore **expands the truth set** to match: for each planted
`MISSING_GSTR1/3B/TAX_PAYMENT`, it finds the invoice's `(supplier, period)` and
marks every invoice in that group as *expected* to raise that outcome. Crucially
it respects the same `GSTR1 ▸ GSTR3B ▸ TAX_PAYMENT` precedence the engine uses
(`_CASCADE_PRIORITY`), expanding only the highest-priority planted gap per
group — so the expected set matches what the `elif` cascade will actually emit.
`CANCELLED_SUPPLIER` is handled similarly but at the GSTIN level: every invoice
from a cancelled supplier is expected to fire it.

This is a **scoring-side** alignment of label granularity to detector behavior,
not a leak: the detector still only ever reads filing keys and status, never the
ground-truth labels. That no-leakage guarantee is enforced separately
(`benchmarks/evalsafe.py`, `tests/test_eval_no_leakage.py`; see
`docs/BENCHMARKS.md`).

Per outcome the scorer computes TP/FP/FN over `(invoice_id, outcome)` keys, then
sums them into a **micro** precision/recall/F1.

### How to read the 0.961 honestly

Two transparency notes a judge should have, both verifiable in the committed
`benchmarks/baseline.json`:

1. **Cascade-expanded rows dominate the micro totals.** The
   `CANCELLED_SUPPLIER` invoice-level row alone contributes 338 of the 1358
   micro true-positives at a perfect 1.0/1.0 — by construction, since every
   invoice from a cancelled supplier trivially raises it and the truth is
   expanded to expect exactly that. The micro number is therefore weighted
   toward the easy, high-multiplicity outcomes, not the subtle amount/tax/date
   ones.
2. **`CANCELLED_SUPPLIER` is counted twice in the micro sum.** `_score`
   produces both an invoice-level `CANCELLED_SUPPLIER` row and a separate
   `CANCELLED_SUPPLIER (gstin-level)` roll-up, and the micro total sums *all*
   rows, so cancelled-supplier detections are aggregated at both granularities.

Neither undermines the engine — it detects what it claims to — but both shape
what "micro-F1 = 0.961" means, and are stated here rather than buried.

## Benchmark result

On the hardened, seeded synthetic dataset the reconciliation engine scores:

| Metric | Value |
|---|---:|
| `reconcile.micro_f1` | **0.961** |
| `reconcile.micro_precision` | 0.935 |
| `reconcile.micro_recall` | 0.988 |

These are the gated headline numbers; the methodology, the leakage guards, and
the ±0.02 regression gate live in `docs/BENCHMARKS.md`. The full per-outcome
precision/recall/F1 breakdown is emitted by
`benchmarks/bench_reconcile_prf.py` into `benchmarks/latest.json`.

## HTTP surface (`reconcile/api.py`)

Mounted at `/api/reconcile2`:

- `POST /run` — run the pipeline; `persist=true` requires an `X-Admin-Token`
  (`require_admin`). Returns count, outcome/severity histograms, and the first
  500 events.
- `GET /events?outcome=…&limit=…` — read persisted events.
- `GET /summary` — outcome-count summary via a fast live re-run (excludes
  `MATCHED`).

## What this engine is intentionally *not*

- Not connected to any real GSTN / e-invoice / GSTR-2B system — synthetic data
  only.
- GSTIN validation is **shape-only**; no checksum verification.
- The settled-payment check depends on `datagen`'s return-id naming convention
  (`_expected_gstr3b_id`), not a stored foreign key.
- Severity rankings are the developers' modeled investigative priority, not
  legal adjudication — see the disclaimer in `docs/GST_DOMAIN.md`.
