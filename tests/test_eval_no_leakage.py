"""Evaluation-integrity guard tests (audit finding F5).

These fail loudly if a planted-label column or value token can reach a
scorer/feature through the benchmark loaders.
"""
from __future__ import annotations

from benchmarks.evalsafe import (assert_label_free, strip_graph_source,
                                  strip_labels)


def test_strip_removes_scenario_from_gstins_but_keeps_status():
    rows = [{"gstin_id": "27X", "status": "CANCELLED", "scenario": "CIRCULAR_TRADING", "directors": "D1"}]
    out = strip_labels(rows, "gstins")
    assert "scenario" not in out[0]
    assert out[0]["status"] == "CANCELLED"   # legitimate feature, kept
    assert out[0]["directors"] == "D1"


def test_strip_removes_invoice_status_and_scenario():
    rows = [{"invoice_id": "I1", "status": "CIRCULAR_FRAUD", "scenario": "CIRCULAR_TRADING",
             "taxable_value": 100.0}]
    out = strip_labels(rows, "invoices")
    assert "status" not in out[0]
    assert "scenario" not in out[0]
    assert out[0]["taxable_value"] == 100.0


def test_strip_removes_ewb_phantom():
    rows = [{"ewb_id": "E1", "phantom": "True", "vehicle_number": "MH01"}]
    out = strip_labels(rows, "ewb")
    assert "phantom" not in out[0]
    assert out[0]["vehicle_number"] == "MH01"


def test_assert_label_free_raises_on_leaked_column():
    rows = [{"invoice_id": "I1", "scenario": "CIRCULAR_TRADING"}]
    try:
        assert_label_free(rows, "invoices", where="unit")
    except AssertionError as e:
        assert "scenario" in str(e)
    else:
        raise AssertionError("expected assert_label_free to raise on leaked column")


def test_assert_label_free_raises_on_label_value_token():
    # A stray label token in a non-denylisted column must still be caught.
    rows = [{"gstin_id": "27X", "note": "CIRCULAR_FRAUD"}]
    try:
        assert_label_free(rows, "gstins", where="unit")
    except AssertionError as e:
        assert "CIRCULAR_FRAUD" in str(e)
    else:
        raise AssertionError("expected assert_label_free to raise on label token")


def test_strip_graph_source_is_label_free_end_to_end():
    gs = {
        "gstins":   [{"gstin_id": "27A", "status": "Active", "scenario": "CIRCULAR_TRADING"}],
        "invoices": [{"invoice_id": "I1", "status": "CIRCULAR_FRAUD", "scenario": "CIRCULAR_TRADING",
                      "supplier_gstin": "27A", "buyer_gstin": "27B"}],
        "pr":       [{"pr_line_id": "P1", "scenario": "CIRCULAR_TRADING"}],
        "edges":    [{"src": "27A", "dst": "27B"}],
    }
    safe = strip_graph_source(gs)
    assert_label_free(safe["gstins"], "gstins", where="e2e")
    assert_label_free(safe["invoices"], "invoices", where="e2e")
    assert_label_free(safe["pr"], "pr", where="e2e")
    # legitimate fields survive
    assert safe["gstins"][0]["status"] == "Active"
    assert safe["invoices"][0]["supplier_gstin"] == "27A"
