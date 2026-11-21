"""Anomaly injection with ground truth.

Given a base population of `MATCHED` invoice bundles, we deterministically
convert a fraction of them into flawed invoices and record the ground
truth so downstream algorithms can be scored.

Each planted anomaly appears in `truth.json` under `planted_anomalies` as:

    {"type": "AMOUNT_MISMATCH", "invoice_id": "...", "delta": 32400,
     "explain": "Buyer PR shows 200000, supplier GSTR1 shows 232400"}

We never mutate the input list in place; we return the new (bundles,
gstr1, gstr3b, tax, planted) so the pipeline stays composable.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional

from .config import GenerationConfig
from .rng import derive, weighted_choice
from .transactions import (GSTR1Rec, GSTR3BRec, InvoiceRec,
                            PurchaseRegisterRec, TaxPaymentRec,
                            TransactionBundle)


ANOM_TYPES = [
    "MISSING_GSTR1", "MISSING_GSTR3B", "MISSING_TAX_PAYMENT",
    "AMOUNT_MISMATCH", "MISSING_EWB", "CANCELLED_SUPPLIER",
    "HSN_MISMATCH", "DATE_MISMATCH",
]


def _mix_weights(cfg: GenerationConfig) -> dict[str, float]:
    return {
        "MISSING_GSTR1":       cfg.anom_mix_missing_gstr1,
        "MISSING_GSTR3B":      cfg.anom_mix_missing_gstr3b,
        "MISSING_TAX_PAYMENT": cfg.anom_mix_missing_tax,
        "AMOUNT_MISMATCH":     cfg.anom_mix_amount_mismatch,
        "MISSING_EWB":         cfg.anom_mix_missing_ewb,
        "CANCELLED_SUPPLIER":  cfg.anom_mix_cancelled_supplier,
        "HSN_MISMATCH":        cfg.anom_mix_hsn_mismatch,
        "DATE_MISMATCH":       cfg.anom_mix_date_mismatch,
    }


def inject_anomalies(
    cfg: GenerationConfig,
    bundles: list[TransactionBundle],
    gstr1s: list[GSTR1Rec],
    gstr3bs: list[GSTR3BRec],
    taxpays: list[TaxPaymentRec],
    ring_invoice_ids: set[str] | None = None,
    gstin_meta_records: list = None,     # kept as list to avoid a circular import
) -> tuple[
    list[TransactionBundle], list[GSTR1Rec], list[GSTR3BRec],
    list[TaxPaymentRec], list[dict],
]:
    ring_invoice_ids = ring_invoice_ids or set()
    gstin_meta_records = gstin_meta_records or []
    rng = derive(cfg.seed, "anomalies.pick")
    total = len(bundles)
    n_defective = int(round(cfg.recon_issue_share * total))
    n_duplicates = int(round(cfg.duplicate_share * total))
    # Only pick from non-ring invoices; ring invoices carry their own status.
    candidate_idx = [i for i, b in enumerate(bundles) if b.invoice.invoice_id not in ring_invoice_ids]
    rng.shuffle(candidate_idx)
    defective_idx = candidate_idx[:n_defective]

    planted: list[dict] = []
    weights = _mix_weights(cfg)
    # ── (a) inject reconciliation defects into invoices ──────────────────
    g1_by_key = {(g.gstin, g.period): g for g in gstr1s}
    g3_by_key = {(g.gstin, g.period): g for g in gstr3bs}
    tp_by_g3 = {t.gstr3b_return_id: t for t in taxpays}
    dropped_gstr1: set[tuple[str, str]] = set()
    dropped_gstr3b: set[tuple[str, str]] = set()
    dropped_tp: set[str] = set()
    cancelled_gstins: set[str] = set()

    for idx in defective_idx:
        b = bundles[idx]
        atype = weighted_choice(rng, weights)
        if atype == "MISSING_GSTR1":
            b.invoice.status = "MISSING_GSTR1"
            b.invoice.scenario = "MISSING_GSTR1"
            dropped_gstr1.add((b.invoice.supplier_gstin, b.invoice.period))
        elif atype == "MISSING_GSTR3B":
            b.invoice.status = "MISSING_GSTR3B"
            b.invoice.scenario = "MISSING_GSTR3B"
            dropped_gstr3b.add((b.invoice.supplier_gstin, b.invoice.period))
        elif atype == "MISSING_TAX_PAYMENT":
            b.invoice.status = "MISSING_TAX_PAYMENT"
            b.invoice.scenario = "MISSING_TAX_PAYMENT"
            g3 = g3_by_key.get((b.invoice.supplier_gstin, b.invoice.period))
            if g3:
                g3.tax_paid_status = "PENDING"
                g3.tax_paid = 0.0
                dropped_tp.add(g3.return_id)
        elif atype == "AMOUNT_MISMATCH":
            delta = round(b.invoice.total_gst * rng.uniform(0.1, 0.9), 2)
            new_amount = round(b.invoice.taxable_value * rng.uniform(0.5, 1.5), 2)
            new_tax = round(new_amount * (b.invoice.total_gst / max(b.invoice.taxable_value, 1)), 2)
            b.pr.booked_amount = new_amount
            b.pr.booked_tax = new_tax
            b.invoice.status = "AMOUNT_MISMATCH"
            b.invoice.scenario = "AMOUNT_MISMATCH"
            planted.append({
                "type": "AMOUNT_MISMATCH", "invoice_id": b.invoice.invoice_id,
                "delta_amount": round(b.invoice.taxable_value - new_amount, 2),
                "delta_tax": round(b.invoice.total_gst - new_tax, 2),
            })
            continue
        elif atype == "MISSING_EWB":
            if b.invoice.taxable_value >= cfg.ewb_threshold_amount:
                b.ewb = None  # drop the EWB even though it was required
                b.invoice.status = "MISSING_EWB"
                b.invoice.scenario = "MISSING_EWB"
            else:
                # Below threshold, MISSING_EWB is not really a defect.
                # Fall through to a different anomaly to avoid biasing the mix.
                b.invoice.status = "MATCHED"
                continue
        elif atype == "CANCELLED_SUPPLIER":
            cancelled_gstins.add(b.invoice.supplier_gstin)
            b.invoice.status = "CANCELLED_GSTIN"
            b.invoice.scenario = "CANCELLED_GSTIN"
            # Actually mutate the GSTIN record's status so the CSV / graph
            # reflects the anomaly (was a Phase 1 gap — the label was
            # planted but the state was never changed).
            for g in gstin_meta_records:
                if g.gstin_id == b.invoice.supplier_gstin:
                    g.status = "CANCELLED"
                    if not g.cancellation_date:
                        g.cancellation_date = b.invoice.date
                    break
        elif atype == "HSN_MISMATCH":
            # buyer's PR records a different HSN (and thus different tax rate)
            b.pr.booked_tax = round(b.invoice.taxable_value * 0.05, 2)  # PR believes 5 %
            b.invoice.status = "HSN_MISMATCH"
            b.invoice.scenario = "HSN_MISMATCH"
            planted.append({
                "type": "HSN_MISMATCH", "invoice_id": b.invoice.invoice_id,
                "supplier_hsn": b.invoice.hsn, "pr_tax": b.pr.booked_tax,
            })
            continue
        elif atype == "DATE_MISMATCH":
            new_dt = (date.fromisoformat(b.invoice.date) + timedelta(days=rng.randint(4, 30))).isoformat()
            b.pr.booked_date = new_dt
            b.invoice.status = "DATE_MISMATCH"
            b.invoice.scenario = "DATE_MISMATCH"
            planted.append({
                "type": "DATE_MISMATCH", "invoice_id": b.invoice.invoice_id,
                "invoice_date": b.invoice.date, "pr_date": new_dt,
            })
            continue
        # Uniform planted entry for the simpler cases
        planted.append({"type": atype, "invoice_id": b.invoice.invoice_id})

    # ── (b) rewrite the returns/payments to reflect drops ────────────────
    new_gstr1s = [g for g in gstr1s if (g.gstin, g.period) not in dropped_gstr1]
    new_gstr3bs = [g for g in gstr3bs if (g.gstin, g.period) not in dropped_gstr3b]
    new_taxpays = [t for t in taxpays if t.gstr3b_return_id not in dropped_tp]

    # cancelled suppliers: mark GSTIN as CANCELLED via scenario in the bundle graph
    # (network.py already tagged some; here we ensure planted ones too)
    if cancelled_gstins:
        planted.extend(
            {"type": "CANCELLED_SUPPLIER", "gstin_id": gid}
            for gid in cancelled_gstins
        )

    # ── (c) duplicates and near-duplicates ───────────────────────────────
    new_bundles = list(bundles)
    if n_duplicates > 0:
        # Sample from remaining MATCHED invoices only.
        matched_idx = [i for i, b in enumerate(new_bundles) if b.invoice.status == "MATCHED"]
        rng.shuffle(matched_idx)
        for i in matched_idx[:n_duplicates]:
            src = new_bundles[i]
            # Two flavors: exact duplicate (same invoice_id in PR twice) and
            # near-duplicate (id differs by punctuation, amount by ±1).
            near = rng.random() < 0.6
            if near:
                dup_id = src.invoice.invoice_id.replace("-", "/")
                dup_amt = src.pr.booked_amount + rng.choice([-1, 1])
                new_pr = PurchaseRegisterRec(
                    pr_line_id=f"PR-DUP-{dup_id}",
                    buyer_gstin=src.invoice.buyer_gstin,
                    invoice_id=dup_id,
                    booked_date=src.pr.booked_date,
                    booked_amount=dup_amt,
                    booked_tax=src.pr.booked_tax,
                )
                # Attach as a phantom bundle sharing supplier/buyer
                new_bundles.append(TransactionBundle(
                    invoice=InvoiceRec(**{**src.invoice.__dict__, "invoice_id": dup_id + "-NEAR",
                                          "status": "NEAR_DUPLICATE",
                                          "scenario": "NEAR_DUPLICATE"}),
                    ewb=None, irn=src.irn, pr=new_pr,
                ))
                planted.append({
                    "type": "NEAR_DUPLICATE", "of_invoice": src.invoice.invoice_id,
                    "duplicate_pr_line": new_pr.pr_line_id,
                })
            else:
                # Exact duplicate: same invoice_id booked twice in PR
                new_pr = PurchaseRegisterRec(
                    pr_line_id=f"PR-DUP-{src.invoice.invoice_id}",
                    buyer_gstin=src.invoice.buyer_gstin,
                    invoice_id=src.invoice.invoice_id,
                    booked_date=src.pr.booked_date,
                    booked_amount=src.pr.booked_amount,
                    booked_tax=src.pr.booked_tax,
                )
                new_bundles.append(TransactionBundle(
                    invoice=InvoiceRec(**{**src.invoice.__dict__,
                                          "invoice_id": src.invoice.invoice_id + "-DUP",
                                          "status": "DUPLICATE",
                                          "scenario": "DUPLICATE"}),
                    ewb=None, irn=src.irn, pr=new_pr,
                ))
                planted.append({
                    "type": "DUPLICATE", "of_invoice": src.invoice.invoice_id,
                })

    return new_bundles, new_gstr1s, new_gstr3bs, new_taxpays, planted
