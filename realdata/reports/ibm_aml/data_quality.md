# Data quality — ibm_aml

- **Source:** https://github.com/IBM/AML-Data
- **License:** CDLA-Sharing-1.0 (commercial OK, share-alike)
- **Real taxpayer data:** NO (public / anonymised / synthetic)
- **Anonymized:** no

## REAL DATA QUALITY REPORT

Records:        131,995
Taxpayers:      144,107  (suppliers 79,280, buyers 99,098)
Invoices:       131,995  (duplicate ids: 0)
Date range:     2022-09-01 → 2022-09-18  (1 month(s))

Coverage:
  GSTIN/entity:   supplier 100.0% · buyer 100.0%
  Invoice ID:     100.0%
  Tax amount:     0.0%
  Date:           100.0%
  Label:          100.0%

Structural:
  self-transactions:        14,742
  missing endpoints:        0
  exact-duplicate rows:     0
  orphan invoice endpoints: 0
  pure suppliers / buyers:  45,009 / 64,827
  valid-GSTIN source ids:   0 (non-GSTIN: 144,107)
  invalid dates:            0
  negative/invalid tax:     0

Potential issues:
  - 14742 self-transactions (supplier==buyer) — not a supplier→buyer edge (dropped at load, counted).
  - no tax amounts → reconciliation / ITC-mismatch cannot run.
  - no source id is a valid 15-char GSTIN → entity ids are non-GSTIN (public/anonymised data).

## Canonical field mapping

| Source field | Canonical field | Graph node / relationship | Downstream engine |
|---|---|---|---|
| `From Bank + Account` | `supplier_id` | (:GSTIN {gstin_id}) | rings, risk, embeddings |
| `To Bank + Account` | `buyer_id` | (:Invoice)-[:BILLED_TO]->(:GSTIN) | rings, reconcile |
| `Timestamp` | `date` | Invoice.date | temporal, rings |
| `Amount Paid` | `taxable_value` | Invoice.taxable_value | rings (value), risk |
| `(row index)` | `txn_id` | (:GSTIN)-[:ISSUED_INVOICE]->(:Invoice) | rings, reconcile |
| `Is Laundering` | `label` | (ground-truth, not a graph field) | supervised evaluation |

## Feature availability

| Feature | Available | Required fields | Can run? |
|---|:--:|---|:--:|
| Reconciliation (GSTR-1↔2B↔3B, ITC) | NO | GSTR filings + tax amounts | **NO** |
| ITC-mismatch detection | NO | invoice tax vs claimed ITC | **NO** |
| Ring / circular-trade detection | YES | directed supplier→buyer edges | **YES** |
| GSTIN / entity relationships | YES | entities + edges | **YES** |
| Temporal analysis | YES | per-transaction dates | **YES** |
| Risk scoring (composed) | YES | ring + temporal (+ reconcile/rules if filings) | **PARTIAL** |
| Graph embeddings (structural) | YES | graph structure | **YES** |
| Ground-truth evaluation (precision/recall) | YES | fraud/ring labels | **YES** |

## Cleaning notes

- 9155 entities dropped as edge-less after removing invalid transactions.