"""Pairwise reconciliation logic.

Given one invoice + its buyer-side PR line (or absence thereof) plus the
supplier's filing state, produce a list of MatchEvent dicts. The engine
calls this once per invoice.

Everything here is pure data-in → data-out; no I/O. That means the same
function is called by:
  * the API (data from Neo4j)
  * the batch engine (data from `graph_source`)
  * the tests (data from small hand-crafted fixtures)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from . import fuzzy
from .outcomes import (AMOUNT_MISMATCH, CANCELLED_SUPPLIER, DATE_MISMATCH,
                       DUPLICATE, HSN_MISMATCH, INVALID_GSTIN_FORMAT,
                       MATCHED, MISSING_EWB, MISSING_GSTR1, MISSING_GSTR3B,
                       MISSING_IN_PR, MISSING_TAX_PAYMENT, NEAR_DUPLICATE,
                       NEAR_MATCH, POS_MISMATCH, TAX_MISMATCH, Reason,
                       severity_for)


# ── Input record shapes (pure dicts to keep the interface graph-source-agnostic) ─
# Invoice   : {invoice_id, supplier_gstin, buyer_gstin, date, hsn,
#              taxable_value, total_gst, place_of_supply, ewb_required, period}
# PR line   : {pr_line_id, invoice_id, booked_date, booked_amount, booked_tax}
# GSTIN meta: {gstin_id, status, cancellation_date, state_code}


def event_id(*parts) -> str:
    h = hashlib.sha1("::".join(str(p) for p in parts).encode()).hexdigest()[:16]
    return "M-" + h


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reason(name: str, weight: float, detail: str, **evidence) -> Reason:
    return Reason(name=name, weight=weight, detail=detail, evidence=dict(evidence))


def _rate_from_hsn(hsn: str, hsn_catalog: dict) -> Optional[float]:
    return (hsn_catalog.get(hsn) or {}).get("rate")


def match_one_invoice(
    invoice: dict,
    pr_lines: List[dict],
    supplier: dict,
    supplier_filed_gstr1: bool,
    supplier_filed_gstr3b: bool,
    supplier_gstr3b_settled: bool,
    ewb_present: bool,
    all_pr_lines_for_buyer: Iterable[dict] = (),
    hsn_catalog: Optional[dict] = None,
    tolerances: Optional[dict] = None,
) -> List[dict]:
    """Return a list of MatchEvent dicts for a single invoice.

    Parameters
    ----------
    invoice : the invoice being reconciled
    pr_lines : buyer-side Purchase Register lines that reference this invoice's ID
                 (exact or normalized-equal after `normalize_id`). Empty ⇒
                 MISSING_IN_PR unless a fuzzy match exists in
                 `all_pr_lines_for_buyer`.
    supplier : {gstin_id, status, cancellation_date, state_code, ...}
    all_pr_lines_for_buyer : the buyer's entire PR (small, so O(n) fuzzy scan
                             is fine for now — indexed match comes in a
                             later revision).
    hsn_catalog : optional {hsn: {rate, ...}} used to catch HSN-implied
                  tax mismatches (e.g. supplier billed 18%, buyer booked 5%).
    """
    tol = {"amount_abs": 1.0, "amount_rel": 0.001, "date_days": 3,
            "invoice_id_jw": 0.90}
    if tolerances:
        tol.update(tolerances)

    events: List[dict] = []
    inv_id = invoice.get("invoice_id")
    sup_id = invoice.get("supplier_gstin")
    buy_id = invoice.get("buyer_gstin")
    hsn_catalog = hsn_catalog or {}

    # ── 1. GSTIN format checks ────────────────────────────────────────
    for who, gid in (("supplier", sup_id), ("buyer", buy_id)):
        if not fuzzy.is_valid_gstin(gid):
            events.append(_event(
                inv_id, sup_id, buy_id, INVALID_GSTIN_FORMAT, delta=None,
                reasons=[_reason(
                    "invalid-gstin-shape", 1.0,
                    f"{who} GSTIN {gid!r} does not match the 15-char state+PAN+entity+Z+check pattern",
                    node_type="GSTIN", node_id=gid,
                )],
            ))
    # short-circuit further semantic checks if either party has a broken GSTIN
    if events and any(e["outcome"] == INVALID_GSTIN_FORMAT for e in events):
        return events

    # ── 2. Supplier cancellation ──────────────────────────────────────
    if (supplier or {}).get("status") == "CANCELLED":
        events.append(_event(
            inv_id, sup_id, buy_id, CANCELLED_SUPPLIER, delta=None,
            reasons=[_reason(
                "supplier-cancelled", 1.0,
                f"Invoice raised by cancelled GSTIN {sup_id}"
                + (f" (cancelled {supplier.get('cancellation_date')})"
                   if supplier.get("cancellation_date") else ""),
                node_type="GSTIN", node_id=sup_id,
            )],
        ))
        # continue running other checks — cancellation doesn't preclude the
        # invoice ALSO being an amount mismatch etc; investigators need every
        # dimension surfaced.

    # ── 3. Missing supplier declarations ──────────────────────────────
    if not supplier_filed_gstr1:
        events.append(_event(
            inv_id, sup_id, buy_id, MISSING_GSTR1, delta=None,
            reasons=[_reason(
                "gstr1-not-filed", 1.0,
                f"Supplier has not filed GSTR-1 for {invoice.get('period')}; "
                f"invoice absent from buyer's auto-populated GSTR-2B",
                node_type="GSTR1", node_id=f"GSTR1-{sup_id}-{invoice.get('period')}",
            )],
        ))
    elif not supplier_filed_gstr3b:
        events.append(_event(
            inv_id, sup_id, buy_id, MISSING_GSTR3B, delta=None,
            reasons=[_reason(
                "gstr3b-not-filed", 1.0,
                f"Supplier filed GSTR-1 but not GSTR-3B for {invoice.get('period')}; "
                f"tax liability declared but summary return missing",
                node_type="GSTR3B", node_id=f"GSTR3B-{sup_id}-{invoice.get('period')}",
            )],
        ))
    elif not supplier_gstr3b_settled:
        events.append(_event(
            inv_id, sup_id, buy_id, MISSING_TAX_PAYMENT, delta=None,
            reasons=[_reason(
                "tax-not-remitted", 1.0,
                f"Supplier filed GSTR-3B but no cleared challan — tax "
                f"collected from buyer has not reached exchequer",
                node_type="TaxPayment", node_id=None,
            )],
        ))

    # ── 4. e-Way Bill ─────────────────────────────────────────────────
    if invoice.get("ewb_required") and not ewb_present:
        events.append(_event(
            inv_id, sup_id, buy_id, MISSING_EWB, delta=None,
            reasons=[_reason(
                "ewb-required-absent", 0.9,
                f"Invoice value ₹{float(invoice.get('taxable_value',0)):,.0f} "
                f"exceeds the ₹50 000 EWB threshold but no e-Way Bill is attached",
                node_type="EWayBill", node_id=None,
            )],
        ))

    # ── 5. PR-side reconciliation ─────────────────────────────────────
    pr = _pick_pr_line(pr_lines)
    if pr is None:
        # try fuzzy match in buyer's whole PR
        fuzzy_hit = _find_fuzzy_pr(inv_id, all_pr_lines_for_buyer, tol["invoice_id_jw"])
        if fuzzy_hit is not None:
            events.append(_event(
                inv_id, sup_id, buy_id, NEAR_MATCH, delta=None,
                reasons=[_reason(
                    "near-match-invoice-id", 0.75,
                    f"Buyer PR references {fuzzy_hit.get('invoice_id')!r} which "
                    f"fuzzy-matches this invoice id (JW≥{tol['invoice_id_jw']}); "
                    f"treating as a formatting variation",
                    node_type="PurchaseRegister", node_id=fuzzy_hit.get("pr_line_id"),
                )],
            ))
            pr = fuzzy_hit
        else:
            events.append(_event(
                inv_id, sup_id, buy_id, MISSING_IN_PR, delta=None,
                reasons=[_reason(
                    "no-pr-line", 1.0,
                    f"No Purchase Register line references invoice {inv_id} "
                    f"and no fuzzy match found in buyer {buy_id}'s book",
                    node_type="PurchaseRegister", node_id=None,
                )],
            ))
    if pr is not None:
        # A. amount
        amount_off = not fuzzy.amount_close(
            invoice.get("taxable_value"), pr.get("booked_amount"),
            abs_tol=tol["amount_abs"], rel_tol=tol["amount_rel"])
        if amount_off:
            delta = float(invoice.get("taxable_value", 0) or 0) - float(pr.get("booked_amount", 0) or 0)
            events.append(_event(
                inv_id, sup_id, buy_id, AMOUNT_MISMATCH, delta=delta,
                reasons=[_reason(
                    "taxable-value-delta",
                    min(1.0, abs(fuzzy.relative_delta(invoice.get("taxable_value"), pr.get("booked_amount")) or 0)),
                    f"Supplier invoice ₹{float(invoice.get('taxable_value',0)):,.2f}; "
                    f"buyer PR ₹{float(pr.get('booked_amount',0)):,.2f} "
                    f"(delta ₹{delta:+,.2f})",
                    node_type="PurchaseRegister", node_id=pr.get("pr_line_id"),
                )],
            ))
        # B. tax — only emit if the tax delta isn't just a downstream
        # consequence of the amount delta. When amount is already off, the
        # tax will be off proportionally; that's ONE anomaly, not two.
        tax_off = not fuzzy.amount_close(
            invoice.get("total_gst"), pr.get("booked_tax"),
            abs_tol=tol["amount_abs"], rel_tol=tol["amount_rel"])
        if tax_off and not amount_off:
            delta = float(invoice.get("total_gst", 0) or 0) - float(pr.get("booked_tax", 0) or 0)
            outcome = HSN_MISMATCH if _looks_like_wrong_rate(
                invoice, pr, hsn_catalog) else TAX_MISMATCH
            events.append(_event(
                inv_id, sup_id, buy_id, outcome, delta=delta,
                reasons=[_reason(
                    "tax-delta",
                    min(1.0, abs(fuzzy.relative_delta(invoice.get("total_gst"), pr.get("booked_tax")) or 0)),
                    f"Supplier total GST ₹{float(invoice.get('total_gst',0)):,.2f}; "
                    f"buyer PR tax ₹{float(pr.get('booked_tax',0)):,.2f} "
                    f"(delta ₹{delta:+,.2f})",
                    node_type="PurchaseRegister", node_id=pr.get("pr_line_id"),
                    hsn_supplier=invoice.get("hsn"),
                )],
            ))
        elif tax_off and amount_off and _looks_like_wrong_rate(invoice, pr, hsn_catalog):
            # Amount was off AND the implied rate slab is different — this
            # deserves an explicit HSN flag on top of AMOUNT_MISMATCH.
            events.append(_event(
                inv_id, sup_id, buy_id, HSN_MISMATCH, delta=None,
                reasons=[_reason(
                    "implied-rate-slab-differs", 0.8,
                    f"PR-implied rate does not match invoice HSN {invoice.get('hsn')} slab",
                    node_type="PurchaseRegister", node_id=pr.get("pr_line_id"),
                    hsn_supplier=invoice.get("hsn"),
                )],
            ))
        # C. date
        if not fuzzy.date_close(invoice.get("date"), pr.get("booked_date"),
                                  days_tol=tol["date_days"]):
            delta_d = fuzzy.date_delta_days(invoice.get("date"), pr.get("booked_date"))
            events.append(_event(
                inv_id, sup_id, buy_id, DATE_MISMATCH, delta=None,
                reasons=[_reason(
                    "date-window-exceeded",
                    min(1.0, abs(delta_d or 0) / 30.0),
                    f"Invoice date {invoice.get('date')} vs PR booked date "
                    f"{pr.get('booked_date')} (delta {delta_d:+d} days > "
                    f"±{tol['date_days']} tolerance)"
                    if delta_d is not None else
                    f"Invoice date {invoice.get('date')} vs PR booked date "
                    f"{pr.get('booked_date')} could not be parsed",
                    node_type="PurchaseRegister", node_id=pr.get("pr_line_id"),
                )],
            ))
        # D. Duplicate (same invoice_id booked twice in PR)
        if len(pr_lines) > 1:
            events.append(_event(
                inv_id, sup_id, buy_id, DUPLICATE, delta=None,
                reasons=[_reason(
                    "pr-line-count",
                    1.0,
                    f"Buyer's PR contains {len(pr_lines)} lines referencing "
                    f"invoice {inv_id} — potential double-claim of ITC",
                    node_type="PurchaseRegister",
                    node_id=[p.get("pr_line_id") for p in pr_lines],
                )],
            ))
        else:
            # E. Near-duplicate: scan buyer's whole PR for lines whose id
            # fuzzy-matches this invoice's id (punctuation-different) but
            # is NOT this invoice's exact line. Even a single hit here
            # implies the buyer has recorded the same underlying supply
            # twice under lightly-different ids.
            fuzzy_dupes = [
                p for p in all_pr_lines_for_buyer
                if p.get("pr_line_id") != pr.get("pr_line_id")
                and p.get("invoice_id") != inv_id
                and fuzzy.invoice_id_match(inv_id, p.get("invoice_id"), threshold=tol["invoice_id_jw"])
            ]
            if fuzzy_dupes:
                events.append(_event(
                    inv_id, sup_id, buy_id, NEAR_DUPLICATE, delta=None,
                    reasons=[_reason(
                        "fuzzy-pr-duplicate", 0.9,
                        f"Buyer PR line {fuzzy_dupes[0].get('pr_line_id')} "
                        f"(invoice_id {fuzzy_dupes[0].get('invoice_id')!r}) "
                        f"fuzzy-matches this invoice's id modulo punctuation — "
                        f"suspected double-claim under a mangled id",
                        node_type="PurchaseRegister",
                        node_id=[p.get("pr_line_id") for p in fuzzy_dupes],
                    )],
                ))

    # ── 6. Place-of-supply implication ────────────────────────────────
    same_state = (
        (supplier or {}).get("state_code")
        and (invoice.get("place_of_supply"))
        and (supplier or {}).get("state_code") == invoice.get("place_of_supply")
    )
    if invoice.get("igst") is not None:
        # If IGST > 0 but same-state, or CGST+SGST > 0 but different state → POS mismatch
        igst = float(invoice.get("igst", 0) or 0)
        cgst = float(invoice.get("cgst", 0) or 0)
        sgst = float(invoice.get("sgst", 0) or 0)
        if igst > 0 and same_state:
            events.append(_event(
                inv_id, sup_id, buy_id, POS_MISMATCH, delta=None,
                reasons=[_reason(
                    "igst-on-intrastate", 1.0,
                    f"IGST ₹{igst:,.2f} charged on intra-state supply "
                    f"(supplier state = buyer state = {supplier.get('state_code')})",
                    node_type="Invoice", node_id=inv_id,
                )],
            ))
        elif (cgst + sgst) > 0 and not same_state:
            events.append(_event(
                inv_id, sup_id, buy_id, POS_MISMATCH, delta=None,
                reasons=[_reason(
                    "cgst-sgst-on-interstate", 1.0,
                    f"CGST+SGST ₹{cgst+sgst:,.2f} charged on inter-state supply "
                    f"(supplier {supplier.get('state_code')} vs buyer {invoice.get('place_of_supply')})",
                    node_type="Invoice", node_id=inv_id,
                )],
            ))

    # ── 7. If no events raised, this invoice is fully MATCHED ─────────
    if not events:
        events.append(_event(
            inv_id, sup_id, buy_id, MATCHED, delta=0.0,
            reasons=[_reason(
                "chain-clean", 1.0,
                "Supplier declared, tax paid, buyer booked matching amount within tolerance",
            )],
        ))

    return events


# ── helpers ────────────────────────────────────────────────────────────
def _event(inv_id, sup, buy, outcome, delta, reasons: List[Reason]) -> dict:
    return {
        "event_id": event_id(inv_id, sup, buy, outcome),
        "outcome": outcome,
        "severity": severity_for(outcome),
        "invoice_id": inv_id,
        "supplier_gstin": sup,
        "buyer_gstin": buy,
        "delta": delta,
        "at": _now(),
        "reasons": [r.to_dict() for r in reasons],
    }


def _pick_pr_line(pr_lines: List[dict]) -> Optional[dict]:
    """Choose one PR line as the "reconciled with" reference.

    When there are multiple exact matches we pick the earliest booked
    (deterministic) and let the DUPLICATE detection flag the extras.
    """
    if not pr_lines:
        return None
    return min(pr_lines, key=lambda r: str(r.get("booked_date", "9999-12-31")))


def _find_fuzzy_pr(inv_id: str, buyer_pr: Iterable[dict], jw_threshold: float) -> Optional[dict]:
    if not inv_id:
        return None
    for p in buyer_pr:
        pid = p.get("invoice_id")
        if pid == inv_id:
            return p
        if fuzzy.invoice_id_match(inv_id, pid, threshold=jw_threshold):
            return p
    return None


def _looks_like_wrong_rate(invoice: dict, pr: dict, hsn_catalog: dict) -> bool:
    """Heuristic: does the PR's tax/amount ratio imply a different HSN rate
    slab (5/12/18/28 %) than the invoice's stated HSN?"""
    if not hsn_catalog or not invoice.get("hsn"):
        return False
    supplier_rate = _rate_from_hsn(invoice.get("hsn"), hsn_catalog)
    if not supplier_rate:
        return False
    pr_amt = float(pr.get("booked_amount", 0) or 0)
    pr_tax = float(pr.get("booked_tax", 0) or 0)
    if pr_amt <= 0:
        return False
    implied = pr_tax / pr_amt
    # If PR's implied rate lands on a different standard slab, tag HSN_MISMATCH
    slabs = [0.05, 0.12, 0.18, 0.28]
    nearest = min(slabs, key=lambda s: abs(s - implied))
    return abs(nearest - supplier_rate) > 0.02  # different slab
