# reconcile — Reconciliation Engine 2.0 (Phase 2)

Graph-native reconciliation. Consumes invoices, buyer PR lines, GSTR-1
/ 3B / 2B keys, and supplier metadata; emits a flat list of typed
`MatchEvent` dicts.

## Design goals

1. **Every outcome is first-class.** A `MISSING_IN_PR` is an object
   with a stable `event_id`, a severity, a delta, and a list of
   `Reason` chips pointing at the exact evidence node — not a boolean
   flag mixed into another table.
2. **Every classification is explainable.** The `Reason[]` list on
   each event is the same schema the UI (Phase 6) reads to render the
   Explainability Panel and the rings engine (Phase 3) uses for its
   per-signal contributions.
3. **Neo4j-optional.** Every code path can be exercised from an
   in-memory `graph_source` dict; that's what the tests and the
   benchmark do. Neo4j is only needed for persistence + the live
   `/api/reconcile2` endpoints.

## Outcome taxonomy

| Outcome | Severity | When |
|---|---|---|
| `MATCHED` | INFO | supplier declared, buyer booked matching amount within tolerance |
| `NEAR_MATCH` | LOW | ids differ only in punctuation; PR was fuzzy-matched |
| `AMOUNT_MISMATCH` | HIGH | invoice.taxable_value vs pr.booked_amount off by > ±₹1 / ±0.1 % |
| `TAX_MISMATCH` | HIGH | tax differs but rate applied is right (base amount differs) |
| `HSN_MISMATCH` | HIGH | implied PR rate lands on a different slab than invoice HSN |
| `DATE_MISMATCH` | MEDIUM | invoice.date vs pr.booked_date > ±3 days |
| `POS_MISMATCH` | MEDIUM | IGST on intra-state supply, or CGST+SGST on inter-state |
| `MISSING_GSTR1` | HIGH | supplier hasn't filed GSTR-1 for the period |
| `MISSING_GSTR3B` | HIGH | supplier filed GSTR-1 but not GSTR-3B |
| `MISSING_TAX_PAYMENT` | CRITICAL | supplier filed GSTR-3B but no cleared challan |
| `MISSING_EWB` | MEDIUM | invoice ≥ ₹50 000 but no e-Way Bill |
| `MISSING_IN_PR` | HIGH | no PR line references this invoice (exact or fuzzy) |
| `DUPLICATE` | CRITICAL | > 1 PR line for the same invoice_id |
| `NEAR_DUPLICATE` | MEDIUM | PR line invoice_id fuzzy-matches another |
| `CANCELLED_SUPPLIER` | CRITICAL | supplier GSTIN status = CANCELLED |
| `INVALID_GSTIN_FORMAT` | HIGH | GSTIN doesn't match the 15-char shape |

## Fuzzy matchers

- Invoice ID: Jaro-Winkler with prefix boost, threshold 0.90 on the
  punctuation-stripped forms. `INV-2024-001` vs `INV/2024/001` → 1.00.
- Amount: `|a - b| ≤ max(₹1, 0.1 % × max(a, b))`.
- Date: `|a - b| ≤ 3 days`.
- HSN mismatch: implied rate (PR tax / PR amount) rounded to nearest
  standard slab (5 / 12 / 18 / 28 %) differs from the invoice's HSN
  slab by more than 2 pp.

## Public API

```python
from reconcile import run_reconcile, ReconcileConfig

events = run_reconcile(
    graph_source={
        "invoices": [...],
        "pr":       [...],
        "gstins":   [...],
        "gstr1_keys":  {("27...", "2024-10"), ...},
        "gstr3b_keys": {...},
        "settled_keys": {"GSTR3B-27AAPFU-202410", ...},
        "ewb_by_invoice": {"INV-...", ...},
    },
    config=ReconcileConfig(include_matched=False),
)

# Each event:
# {
#   "event_id": "M-abcdef0123456789",
#   "outcome":  "AMOUNT_MISMATCH",
#   "severity": "HIGH",
#   "invoice_id": "INV-...",
#   "supplier_gstin": "27...",
#   "buyer_gstin":    "29...",
#   "delta": -12345.67,
#   "at":    "2026-08-18T20:00:00+00:00",
#   "reasons": [
#     {"name": "taxable-value-delta", "weight": 0.42,
#      "detail": "Supplier invoice ₹...; buyer PR ₹...; (delta ₹...)",
#      "evidence": {"node_type": "PurchaseRegister", "node_id": "PR-..."}},
#   ]
# }
```

## HTTP surface

- `POST /api/reconcile2/run` — run pipeline. `persist=true` requires
  `X-Admin-Token`. Returns count + outcome/severity histograms +
  first 500 events.
- `GET /api/reconcile2/events?outcome=AMOUNT_MISMATCH&limit=200` — read
  persisted events.
- `GET /api/reconcile2/summary` — fast outcome-count summary.

## Benchmark

`benchmarks/bench_reconcile_prf.py` scores this engine's outputs
against `truth.json` from Phase 1 and reports per-outcome
precision / recall / F1. See `IMPLEMENTATION_LOG.md` for the current
numbers.
