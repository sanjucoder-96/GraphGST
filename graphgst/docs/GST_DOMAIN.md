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

## V6.4 coverage matrix — MODELED / PARTIAL / NOT MODELED

Not every GST concept is modeled to the same depth. This matrix is the honest
map, grounded in the generator (`datagen/`) and detectors (`reconcile/`,
`risk/`). Read it before assuming a concept is fully simulated.

| Status | Concept | What it means in the code |
|---|---|---|
| **MODELED** | GSTIN + taxpayer, supplier & buyer, `Invoice`, `GSTR1`, `GSTR3B`, `TaxPayment`, `EWayBill`, `PurchaseRegister`, CGST/SGST/IGST split, monthly filing periods | The core filing spine. Each is a first-class node with real values, wired into the chain, and reconciled by detectors. Tax is split by same-state (CGST+SGST) vs cross-state (IGST) in `_split_tax`; periods are `YYYY-MM`. |
| **PARTIAL** | HSN | Exactly **one HSN per invoice** (`InvoiceRec.hsn`). Used only for cross-filing *rate consistency* (does the PR's implied rate match the invoice's?), never to assert a correct classification. |
| **PARTIAL** | IRN / e-Invoice | Always generated and always `portal_status="ACTIVE"` (`_one_invoice` comment: "treat as always present in demo"). Never validated against a real IRP — its presence is assumed, so it never fails. |
| **PARTIAL** | GSTR-2B | A **bare stub node** carrying only `return_id`, `gstin`, `period` (`GSTR2BRec`). It has no invoice lines and is **reconciled by no detector** — it exists for graph completeness, not analysis. |
| **PARTIAL** | ITC (input tax credit) | **Inferred from filing-chain breaks**, not stored for normal traffic: `GSTR3B.itc_claimed` defaults to `0.0` and `derive_returns` leaves it `0` for normal returns. A non-zero `itc_claimed` is written only for planted ring / circular-fraud scenarios (`datagen/rings.py`, `rings_hard.py`, `seeder.py`). ITC "at risk" is derived from chain gaps (missing GSTR-1/3B/challan, cancelled supplier). |
| **PARTIAL** | Place of supply | Always set to the **buyer's state** (`place_of_supply=buy.state_code`). Because the tax split is derived from the same state comparison, normal invoices are internally consistent and never trip `POS_MISMATCH`. |
| **PARTIAL** | Invoice line grain | **Single-line invoices** — one HSN and one taxable value per invoice. No multi-line / multi-rate invoices. |
| **NOT MODELED** | Credit notes, debit notes, amendments | No node, no generator, no detector anywhere in the codebase. There is no way to reduce, correct, or revise a filed value. |

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

### Detector-supported but NOT yet generated (V6.4)

The taxonomy has 16 codes, but the ground truth only covers 11 of them:
`datagen/anomalies.py` plants 10 anomaly types — `MISSING_GSTR1`,
`MISSING_GSTR3B`, `MISSING_TAX_PAYMENT`, `AMOUNT_MISMATCH`, `MISSING_EWB`,
`CANCELLED_SUPPLIER`, `HSN_MISMATCH`, `DATE_MISMATCH`, `DUPLICATE`,
`NEAR_DUPLICATE` — plus the `MATCHED` baseline for clean invoices.

The matcher (`reconcile/matcher.py`) *can* emit five more, but **datagen never
plants them**, so the benchmark has zero ground truth to score them against —
**they are currently unmeasurable**:

| Outcome | Matcher can emit it | Datagen plants it | Benchmark can score it |
|---|---|---|---|
| `INVALID_GSTIN_FORMAT` | yes (shape check) | **no** | **no** |
| `TAX_MISMATCH` | yes | **no** | **no** |
| `POS_MISMATCH` | yes | **no** (POS is always internally consistent) | **no** |
| `MISSING_IN_PR` | yes | **no** | **no** |
| `NEAR_MATCH` | yes | **no** | **no** — it surfaces only as false positives (see `IMPLEMENTATION_LOG.md`) |

Practical effect: the headline F1 (0.961) is computed over the 11 planted
outcomes only. These five detectors are real code with real logic, but their
accuracy is unknown until datagen learns to plant them.

### V7 decision (WS6) — new fraud scenarios: **DEFERRED to V8**

V7 evaluated adding 1–2 of `TAX_MISMATCH`, `POS_MISMATCH`, `MISSING_IN_PR`,
credit/debit notes, or amendments. **Decision: defer all of them to V8**, on
purpose, for three reasons:

1. **The detectors already exist; only generation is missing.** `TAX_MISMATCH`,
   `POS_MISMATCH`, and `MISSING_IN_PR` are already emitted by
   `reconcile/matcher.py` (see the table above). The missing half is datagen
   planting, not detection — so shipping them adds *ground truth*, not new
   capability.
2. **Any addition forces a full metric re-baseline.** Planting a new anomaly
   type shifts the label distribution the 9 gated metrics are computed over, so
   every baseline in `benchmarks/baseline.json` would move. Re-baselining during
   the *final productization gate* is exactly the change-the-numbers-under-your-
   own-feet risk the V7 mandate warns against; it belongs in a dedicated data
   phase with its own before/after audit, not bolted onto the release.
3. **V7 is a hardening stage, not a new feature phase.** Introducing fraud
   scenarios is a feature phase and is out of scope for "do not begin another
   major feature phase after the final gate."

**Ranked recommendation for V8** (do the top one first, in isolation, then
re-baseline and audit before adding the next):

1. **`TAX_MISMATCH`** — highest value / lowest risk. Detector exists; a clean
   real-world case (GST charged at the wrong rate / wrong taxable value). Plant
   by perturbing `invoice.total_gst` away from `rate × taxable_value` on a small
   labelled share, leaving the filing chain otherwise intact so it is *distinct*
   from `AMOUNT_MISMATCH` (which perturbs the invoice value itself).
2. **`MISSING_IN_PR`** — supplier filed GSTR-1 but the invoice never appears in
   the buyer's purchase register; a common real reconciliation break. Plant by
   dropping the PR row for a labelled share of otherwise-matched invoices.
3. **Credit / debit notes & amendments** — larger: new node types + new matcher
   logic + new detectors. A genuine feature phase; keep last.

**Re-baseline procedure when V8 executes this:** add the planting to
`datagen/anomalies.py` behind a new `anom_mix_*` weight (default 0), regenerate
the deterministic dataset, run `python -m benchmarks.run_all`, and *only then*
commit the shifted numbers into `benchmarks/baseline.json` with a documented
before/after diff — never silently.

## The GSTIN identifier (`datagen/identifiers.py`)

A GSTIN is a 15-character code: 2-digit state + 10-char PAN + entity digit +
'Z' + checksum. The generator produces **only structurally-valid GSTINs**
(`synth_gstin` always assembles a well-formed 15-char string with a computed
checksum). It does **not** deliberately produce malformed ones — earlier docs
claimed it planted invalid GSTINs "for the `INVALID_GSTIN_FORMAT` case", but
that is **not true**: `INVALID_GSTIN_FORMAT` is one of the five
detector-supported-but-not-generated outcomes above. The matcher's shape check
would catch a malformed GSTIN if one ever appeared, but on synthetic data none
do. The **state code** and **PAN** are used as real signals: shared PAN across
GSTINs indicates common ownership; PIN-prefix and state clustering feed the ring
`network_signal`.

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

## V6.4 — runtime narrative language was softened

The audit narratives the system shows an investigator (the 8-hop walkthrough in
`risk_engine.py` and the insight / draft-notice text in `main.py`) were
**rewritten from definitive legal assertions to conditional, investigator-facing
language**, to match the disclaimer at the top of this document. Concretely:

- Phrases like *"tax evaded"*, *"criminal prosecution applies"*, and specific
  penalty computations were replaced with *"flagged for verification"*,
  *"potential exposure to be assessed by the officer"*, and *"not a legal
  determination"* (e.g. `risk_engine.py` hops 1/5/7; `main.py` insight line and
  the draft SCN, which now closes with *"Officer must review and apply
  independent mind"* / *"modeled indicators, not determinations"*).
- Statute citations themselves (e.g. "Section 16(2)(c)", "Section 74") are
  **kept** — but as the *rationale* for a flag, never as an adjudication, exactly
  as the disclaimer allows. A residual `legal_provisions` list and one Hindi
  summary line still read assertively; those are next on the cleanup list.

The graph evidence and scores did not change — only the words wrapped around
them, so the output no longer overclaims legal certainty.

## What is intentionally NOT modeled

- Real GSTN API integration, e-invoice IRN validation, or live GSTR-2B pull.
- Actual legal adjudication, penalty computation, or interest under any section.
- Real taxpayer data — everything is synthetic (seed 42, deterministic).
- Rate correctness / classification disputes (HSN is used only for
  cross-filing *consistency*, not to assert a correct rate).

Keeping this list explicit is the point: the system is defensible precisely
because it does not overclaim.

## Highest-value planned domain work (V6.4 deferred)

These are the pieces that would most improve **ITC-fraud detection**, listed
here so the gap is on the record. They were *deliberately deferred this pass* to
avoid disturbing the current benchmark baselines (the F1 = 0.961 number is
computed over today's planted outcomes; adding new planted types or reworking
reconciliation would move that number and break comparison with prior runs).

1. **Credit notes and debit notes + a `REVERSAL_MISMATCH` outcome.** Real ITC
   fraud often hides in reversals: a supplier issues a credit note (reducing
   their declared liability) while the buyer never reverses the matching ITC, or
   vice-versa. Modeling credit/debit notes as nodes and adding a
   `REVERSAL_MISMATCH` detector (declared reversal on one side, none on the
   other) would catch a fraud pattern the current chain-break detectors cannot
   see at all. This is the single highest-value addition.
2. **Actually planting `MISSING_IN_PR`.** The matcher already detects it (buyer
   never booked an invoice — a classic fabricated-invoice signal), but datagen
   never plants it, so its accuracy is unmeasured. Teaching `datagen/anomalies.py`
   to drop the PR line for a fraction of invoices would turn an untested detector
   into a benchmarked one.

Both are genuine domain improvements, not cosmetic — they extend what the system
can *detect*, not just what it can *display*.
