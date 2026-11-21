"""End-to-end smoke test with pure Python graph_source (no Neo4j).

Exercises the full pipeline including the fixes:
  * closure_strength distinguishes tight vs leaky rings
  * counterfactual break_edge is not deterministically the seed
  * duplicate edges from an upstream loader would have inflated results;
    here we feed clean edges to demonstrate the expected shape.
"""
from datetime import date

from rings.engine import EngineConfig, run_pipeline


def _edge(src, dst, gst, invoice, d=None, amount=None, vehicle=None):
    return {
        "src": src, "dst": dst, "invoice_id": invoice,
        "amount": amount if amount is not None else gst,
        "gst_amount": gst,
        "date": d or date(2026, 1, 1),
        "vehicle_id": vehicle, "hsn": None, "pin_prefix": None,
    }


def test_pipeline_detects_tight_ring():
    edges = [
        _edge("G01", "G02", 100, "i1", date(2026, 1, 1)),
        _edge("G02", "G03", 100, "i2", date(2026, 1, 2)),
        _edge("G03", "G01", 100, "i3", date(2026, 1, 3)),
    ]
    graph_source = {"edges": edges, "member_meta": {}}
    cfg = EngineConfig(persist=False, propagate=False, use_gds=False)
    rings = run_pipeline(cfg, graph_source=graph_source)
    assert len(rings) == 1
    r = rings[0]
    assert sorted(r.members) == ["G01", "G02", "G03"]
    # Tight closure (equal GST, clamped to 1.0).
    assert r.signals["C"] == 1.0
    # Compact temporal.
    assert r.signals["T"] > 0.9
    # Break edge suggested.
    assert r.break_edge is not None


def test_pipeline_scores_leaky_below_tight():
    tight = [
        _edge("G01", "G02", 100, "t1", date(2026, 1, 1)),
        _edge("G02", "G03", 100, "t2", date(2026, 1, 2)),
        _edge("G03", "G01", 100, "t3", date(2026, 1, 3)),
    ]
    leaky = [
        _edge("H01", "H02", 100, "l1", date(2026, 1, 1)),
        _edge("H02", "H03", 10, "l2", date(2026, 1, 2)),
        _edge("H03", "H01", 10, "l3", date(2026, 1, 3)),
    ]
    cfg = EngineConfig(persist=False, propagate=False, use_gds=False)
    rings = run_pipeline(cfg, graph_source={"edges": tight + leaky, "member_meta": {}})
    assert len(rings) == 2
    tight_r = next(r for r in rings if "G01" in r.members)
    leaky_r = next(r for r in rings if "H01" in r.members)
    # REGRESSION: post-fix, closure discriminates. Old bug had both at 1.0.
    assert tight_r.signals["C"] > leaky_r.signals["C"]


def test_pipeline_no_cycles_returns_empty():
    edges = [
        _edge("G01", "G02", 100, "i1"),
        _edge("G02", "G03", 100, "i2"),
        # No G03 -> G01, so no cycle.
    ]
    cfg = EngineConfig(persist=False, propagate=False, use_gds=False)
    rings = run_pipeline(cfg, graph_source={"edges": edges, "member_meta": {}})
    assert rings == []
