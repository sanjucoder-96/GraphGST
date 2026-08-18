"""Direct unit tests on `matcher.match_one_invoice`."""
import pytest

from reconcile.matcher import match_one_invoice


def _invoice(**over):
    # Default fixture: INTRA-state supply (supplier state 27 = buyer state 27),
    # CGST+SGST split, IGST=0 — so a "clean chain" doesn't trip POS_MISMATCH.
    base = {
        "invoice_id": "INV-1",
        "supplier_gstin": "27AAPFU0939F1ZV",
        "buyer_gstin":   "27KKKPO1234F1ZV",
        "date": "2024-11-01",
        "hsn":  "7208",
        "taxable_value": 100000.0,
        "total_gst": 18000.0,
        "cgst": 9000.0, "sgst": 9000.0, "igst": 0.0,
        "place_of_supply": "27",
        "ewb_required": True,
        "period": "2024-11",
    }
    base.update(over)
    return base


def _pr(**over):
    base = {
        "pr_line_id": "PR-INV-1", "invoice_id": "INV-1",
        "buyer_gstin": "27KKKPO1234F1ZV",
        "booked_date": "2024-11-01",
        "booked_amount": 100000.0,
        "booked_tax": 18000.0,
    }
    base.update(over)
    return base


def _supplier(**over):
    base = {"gstin_id": "27AAPFU0939F1ZV", "status": "Active", "state_code": "27"}
    base.update(over)
    return base


def _outcomes(events):
    return sorted(e["outcome"] for e in events)


def test_clean_chain_matches():
    ev = match_one_invoice(_invoice(), [_pr()], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    assert _outcomes(ev) == ["MATCHED"]


def test_missing_gstr1():
    ev = match_one_invoice(_invoice(), [_pr()], _supplier(),
                            supplier_filed_gstr1=False, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    assert "MISSING_GSTR1" in _outcomes(ev)


def test_missing_gstr3b():
    ev = match_one_invoice(_invoice(), [_pr()], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=False,
                            supplier_gstr3b_settled=False, ewb_present=True)
    assert "MISSING_GSTR3B" in _outcomes(ev)


def test_missing_tax_payment():
    ev = match_one_invoice(_invoice(), [_pr()], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=False, ewb_present=True)
    assert "MISSING_TAX_PAYMENT" in _outcomes(ev)


def test_amount_mismatch():
    ev = match_one_invoice(_invoice(), [_pr(booked_amount=50000.0)], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    outs = _outcomes(ev)
    assert "AMOUNT_MISMATCH" in outs
    amt = next(e for e in ev if e["outcome"] == "AMOUNT_MISMATCH")
    assert amt["delta"] == pytest.approx(50000.0)


def test_date_mismatch():
    ev = match_one_invoice(_invoice(), [_pr(booked_date="2024-12-05")], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    assert "DATE_MISMATCH" in _outcomes(ev)


def test_cancelled_supplier():
    ev = match_one_invoice(
        _invoice(), [_pr()], _supplier(status="CANCELLED",
                                       cancellation_date="2024-10-01"),
        supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
        supplier_gstr3b_settled=True, ewb_present=True)
    assert "CANCELLED_SUPPLIER" in _outcomes(ev)


def test_invalid_gstin_shortcircuits_other_checks():
    ev = match_one_invoice(_invoice(supplier_gstin="27FOO"), [], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    assert _outcomes(ev) == ["INVALID_GSTIN_FORMAT"]


def test_missing_in_pr():
    ev = match_one_invoice(_invoice(), [], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    assert "MISSING_IN_PR" in _outcomes(ev)


def test_near_match_fuzzy_id():
    # PR line uses different punctuation
    fuzzy_pr = _pr(pr_line_id="PR-FUZ-INV-1", invoice_id="INV/1")
    ev = match_one_invoice(_invoice(), [], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True,
                            all_pr_lines_for_buyer=[fuzzy_pr])
    outs = _outcomes(ev)
    assert "NEAR_MATCH" in outs
    assert "MISSING_IN_PR" not in outs


def test_duplicate_pr():
    ev = match_one_invoice(_invoice(),
                            [_pr(), _pr(pr_line_id="PR-INV-1-DUP")],
                            _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    assert "DUPLICATE" in _outcomes(ev)


def test_missing_ewb_when_required():
    ev = match_one_invoice(_invoice(), [_pr()], _supplier(),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=False)
    assert "MISSING_EWB" in _outcomes(ev)


def test_pos_mismatch_igst_intrastate():
    # Supplier and buyer in same state, but IGST used instead of CGST+SGST
    inv = _invoice(place_of_supply="27", cgst=0.0, sgst=0.0, igst=18000.0)
    ev = match_one_invoice(inv, [_pr()], _supplier(state_code="27"),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    assert "POS_MISMATCH" in _outcomes(ev)


def test_pos_mismatch_cgst_on_interstate():
    # Supplier state 27, buyer state 29 — CGST+SGST used incorrectly
    inv = _invoice(supplier_gstin="27AAPFU0939F1ZV",
                    buyer_gstin="29AABCT1332L1ZU",
                    place_of_supply="29",
                    cgst=9000.0, sgst=9000.0, igst=0.0)
    ev = match_one_invoice(inv, [_pr(buyer_gstin="29AABCT1332L1ZU")], _supplier(state_code="27"),
                            supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
                            supplier_gstr3b_settled=True, ewb_present=True)
    assert "POS_MISMATCH" in _outcomes(ev)


def test_hsn_mismatch_via_rate_slab():
    # supplier HSN 8471 → 18 %; PR books tax as if 5 % applied (5000 on 100000)
    ev = match_one_invoice(
        _invoice(hsn="8471"),
        [_pr(booked_tax=5000.0)], _supplier(),
        supplier_filed_gstr1=True, supplier_filed_gstr3b=True,
        supplier_gstr3b_settled=True, ewb_present=True,
        hsn_catalog={"8471": {"rate": 0.18}},
    )
    outs = _outcomes(ev)
    # Should classify as HSN_MISMATCH, not plain TAX_MISMATCH, because the
    # implied PR rate (5 %) is in a different slab than the invoice HSN (18 %).
    assert "HSN_MISMATCH" in outs
    assert "TAX_MISMATCH" not in outs
