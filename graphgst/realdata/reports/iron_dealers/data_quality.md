# Data quality — iron_dealers

- **Source:** https://github.com/Sindhuja-5/circular-trade-detection
- **License:** No license file (treat as all-rights-reserved; research/testing use only)
- **Real taxpayer data:** NO (public / anonymised / synthetic)
- **Anonymized:** no

## REAL DATA QUALITY REPORT

Records:        130,535
Taxpayers:      799  (suppliers 703, buyers 371)
Invoices:       130,535  (duplicate ids: 0)
Date range:     — → —  (0 month(s))

Coverage:
  GSTIN/entity:   supplier 100.0% · buyer 100.0%
  Invoice ID:     100.0%
  Tax amount:     0.0%
  Date:           0.0%
  Label:          0.0%

Structural:
  self-transactions:        0
  missing endpoints:        0
  exact-duplicate rows:     7,386
  orphan invoice endpoints: 0
  pure suppliers / buyers:  428 / 96
  valid-GSTIN source ids:   0 (non-GSTIN: 799)
  invalid dates:            0
  negative/invalid tax:     0

Potential issues:
  - 7386 exact-duplicate rows (kept — may be legitimate repeat trades).
  - date coverage 0.0% → temporal analysis limited/disabled.
  - no tax amounts → reconciliation / ITC-mismatch cannot run.
  - no fraud/ring labels → UNSUPERVISED analysis only (no precision/recall).
  - no source id is a valid 15-char GSTIN → entity ids are non-GSTIN (public/anonymised data).

## Canonical field mapping

| Source field | Canonical field | Graph node / relationship | Downstream engine |
|---|---|---|---|
| `Seller ID` | `supplier_id` | (:GSTIN {gstin_id}) | rings, risk, embeddings |
| `Buyer ID` | `buyer_id` | (:Invoice)-[:BILLED_TO]->(:GSTIN) | rings, reconcile |
| `(row index)` | `txn_id` | (:GSTIN)-[:ISSUED_INVOICE]->(:Invoice) | rings, reconcile |
| `Value` | `taxable_value` | Invoice.taxable_value / Invoice.amount | rings (value signal), risk |

## Feature availability

| Feature | Available | Required fields | Can run? |
|---|:--:|---|:--:|
| Reconciliation (GSTR-1↔2B↔3B, ITC) | NO | GSTR filings + tax amounts | **NO** |
| ITC-mismatch detection | NO | invoice tax vs claimed ITC | **NO** |
| Ring / circular-trade detection | YES | directed supplier→buyer edges | **YES** |
| GSTIN / entity relationships | YES | entities + edges | **YES** |
| Temporal analysis | NO | per-transaction dates | **NO** |
| Risk scoring (composed) | YES | ring + temporal (+ reconcile/rules if filings) | **PARTIAL** |
| Graph embeddings (structural) | YES | graph structure | **YES** |
| Ground-truth evaluation (precision/recall) | NO | fraud/ring labels | **NO** |
