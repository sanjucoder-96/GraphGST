# GST Domain Model

This document explains the Indian GST concepts Graph GST models, and — just as
importantly — draws a hard line around what it does **not** claim.

> **Disclaimer.** Graph GST is a research/analytics prototype. The rules and
> severity rankings below encode the developers' modeling rationale for
> *prioritizing investigative attention on synthetic data*. They are **not
> legal advice, not a compliance certification, and have not been validated by
> a tax practitioner or against live GSTN systems.** Statutory section
> references (e.g. Sec 16, Sec 74) appear as the rationale for a severity
> weight, not as an assertion of how any real case would be adjudicated. No
> output should be used to issue a real notice without independent
> professional review.

## The documents we model

GST compliance is a reconciliation problem across several filings. Graph GST
models these as first-class graph nodes:

| Node | Real-world meaning (as modeled) |
|---|---|
| `Invoice` | A tax invoice from a supplier GSTIN to a buyer GSTIN. |
| `GSTR1` | The supplier's outward-supplies return for a period. |
| `GSTR3B` | The supplier's summary return where tax liability is declared. |
| `TaxPayment` | A challan settling the declared liability. |
| `EWayBill` | The transport document for movement of goods. |
| `PurchaseRegister` | The buyer's own record of the invoice (their booked purchase). |

The intended chain of consistency: an invoice should appear in the supplier's
GSTR-1, be summarized in their GSTR-3B, be settled by a TaxPayment, be
transported under an EWayBill, and be booked in the buyer's PurchaseRegister.
A break anywhere in that chain is a reconciliation anomaly.

## Input Tax Credit (ITC) — why the chain matters

The economic heart of GST fraud is ITC: a buyer can offset the tax it *paid* on
purchases against the tax it *owes* on sales. That is only legitimate if the
supplier actually declared and remitted the corresponding tax. Every anomaly
below is ultimately about **ITC that a buyer might claim but that was never
backed by real, remitted tax** — which is precisely what a fake-invoice or
carousel scheme manufactures.

## The 16-outcome reconciliation taxonomy (`reconcile/outcomes.py`)

Each invoice is reconciled to an outcome. Severity is the modeled investigative
priority, with the developer's rationale in parentheses:

| Outcome | Severity | Modeled rationale |
|---|---|---|
| `MISSING_TAX_PAYMENT` | CRITICAL | Tax declared but no cleared challan — collected-not-remitted. |
| `DUPLICATE` | CRITICAL | Same invoice claimed twice — double ITC. |
| `CANCELLED_SUPPLIER` | CRITICAL | Invoice from a cancelled GSTIN — ITC ineligible. |
| `AMOUNT_MISMATCH` / `TAX_MISMATCH` / `HSN_MISMATCH` | HIGH | Values disagree across filings. |
| `MISSING_GSTR1` | HIGH | Buyer's ITC blocked — supplier never declared the outward supply. |
| `MISSING_GSTR3B` | HIGH | Supplier's summary liability not declared. |
| `MISSING_IN_PR` | HIGH | Buyer never booked it — possible fabricated invoice. |
| `INVALID_GSTIN_FORMAT` | HIGH | Structurally invalid party identifier. |
| `DATE_MISMATCH` / `POS_MISMATCH` / `NEAR_DUPLICATE` | MEDIUM | Softer inconsistencies. |
| `MISSING_EWB` | MEDIUM | Logistics/movement compliance gap. |
| `NEAR_MATCH` | LOW / `MATCHED` INFO | Clean or trivially-off. |

These strings are the **authoritative** codes shared with the synthetic
generator (`datagen/anomalies.py`) so benchmark scoring is a direct string
comparison — the detector and the ground truth speak the same vocabulary, but
the detector never *reads* the truth (see `docs/BENCHMARKS.md`).

## The GSTIN identifier (`datagen/identifiers.py`)

A GSTIN is a 15-character code: 2-digit state + 10-char PAN + entity digit +
'Z' + checksum. The generator produces structurally-valid GSTINs (and
deliberately invalid ones for the `INVALID_GSTIN_FORMAT` case). The **state
code** and **PAN** are used as real signals: shared PAN across GSTINs indicates
common ownership; PIN-prefix and state clustering feed the ring `network_signal`.

## The filing rules in the risk engine (`risk/scorers/rules.py`)

The `RuleScorer` turns filing-chain gaps into weighted Reasons, each pointing at
the exact graph path:

- **supplier-cancelled** — GSTIN status is CANCELLED (weight 1.0).
- **missing-gstr1-fraction** — fraction of the entity's invoices with no GSTR-1.
- **missing-gstr3b-fraction** — GSTR-1 filed but no GSTR-3B for the period.
- **unremitted-tax-fraction** — GSTR-3B filed but no cleared challan (highest
  multiplier, ×1.5 — collected-not-remitted is the sharpest red flag).
- **supplies-to-self** — a GSTIN that is both supplier and buyer on one invoice.

The subscore is the **mean** of fired reason weights, so it stays in [0,1]
regardless of how many rules fire — more rules firing raises confidence via the
composite, not by letting one entity's score exceed the bound.

## What is intentionally NOT modeled

- Real GSTN API integration, e-invoice IRN validation, or live GSTR-2B pull.
- Actual legal adjudication, penalty computation, or interest under any section.
- Real taxpayer data — everything is synthetic (seed 42, deterministic).
- Rate correctness / classification disputes (HSN is used only for
  cross-filing *consistency*, not to assert a correct rate).

Keeping this list explicit is the point: the system is defensible precisely
because it does not overclaim.
