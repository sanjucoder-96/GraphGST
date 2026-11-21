"""Tests for ring-level temporal descriptors (audit Phase D)."""
from __future__ import annotations

from datetime import date

from rings.temporal_signals import (cyclic_temporal_incoherence,
                                     inter_hop_regularity, temporal_descriptors,
                                     velocity_inr_per_day)


def test_velocity_basic():
    assert velocity_inr_per_day(300000, 3) == 100000.0
    # same-day loop: span floored to 1
    assert velocity_inr_per_day(50000, 0) == 50000.0


def _edges(days):
    return [{"date": date(2024, 6, d).isoformat()} for d in days]


def test_regularity_uniform_is_high():
    # one hop per day → perfectly uniform → regularity ~1.0
    r = inter_hop_regularity(_edges([1, 2, 3, 4]))
    assert r is not None and r >= 0.99


def test_regularity_irregular_is_lower():
    # gaps 1, 9, 1 → high variation → lower regularity
    r_reg = inter_hop_regularity(_edges([1, 2, 3, 4]))
    r_irr = inter_hop_regularity(_edges([1, 2, 11, 12]))
    assert r_irr is not None and r_reg is not None
    assert r_irr < r_reg


def test_regularity_needs_three_dates():
    assert inter_hop_regularity(_edges([1, 2])) is None
    assert inter_hop_regularity([]) is None


def test_regularity_all_same_day_is_none():
    assert inter_hop_regularity(_edges([5, 5, 5, 5])) is None


def test_regularity_handles_unparseable_dates():
    edges = [{"date": "not-a-date"}, {"date": None}, {"date": "2024-06-01"}]
    # only 1 parseable → None
    assert inter_hop_regularity(edges) is None


def _cyc(days):
    # edges in cycle-traversal order with the given hop dates
    return [{"date": date(2024, 6, d).isoformat()} for d in days]


def test_incoherence_monotone_forward_loop_is_zero():
    # a real forward flow: dates non-decreasing → exactly one wrap descent → 0
    assert cyclic_temporal_incoherence(_cyc([1, 2, 3])) == 0.0
    assert cyclic_temporal_incoherence(_cyc([1, 2, 3, 4, 5])) == 0.0


def test_incoherence_impossible_loop_flags():
    # SYNTHETIC SCENARIO: A->B (18 Jun), B->C (02 Jun), C->A (25 Jun): B resells
    # (02 Jun) before it was supplied (18 Jun) — impossible for one consignment.
    # D=2 descents → max(0,2-1)/(3-1) = 0.5. Every span/velocity/compactness
    # signal stays benign (all within June), only this one fires.
    assert cyclic_temporal_incoherence(_cyc([18, 2, 25])) == 0.5


def test_incoherence_same_day_loop_is_zero():
    assert cyclic_temporal_incoherence(_cyc([7, 7, 7])) == 0.0


def test_incoherence_needs_all_dates():
    assert cyclic_temporal_incoherence([{"date": "2024-06-01"}, {"date": None}]) is None
    assert cyclic_temporal_incoherence(_cyc([1])) is None


def test_incoherence_is_bounded():
    v = cyclic_temporal_incoherence(_cyc([5, 1, 6, 2, 7]))
    assert v is not None and 0.0 <= v <= 1.0


def test_temporal_descriptors_bundle():
    d = temporal_descriptors(300000, 3, _edges([1, 2, 3, 4]))
    assert d["velocity_inr_per_day"] == 100000.0
    assert 0.0 <= d["inter_hop_regularity"] <= 1.0
    assert "cyclic_temporal_incoherence" in d
    assert "note" in d and "day" in d["note"]


def test_descriptors_bundle_flags_impossible_loop_in_note():
    d = temporal_descriptors(300000, 30, _cyc([18, 2, 25]))
    assert d["cyclic_temporal_incoherence"] == 0.5
    assert "IMPOSSIBLE" in d["note"]


def test_engine_attaches_temporal_to_ring():
    """The detected-ring output carries the temporal descriptors."""
    from rings.engine import EngineConfig, run_pipeline
    edges = [
        {"src": "A", "dst": "B", "invoice_id": "I1", "date": date(2024, 6, 1),
         "amount": 100000, "gst_amount": 18000, "vehicle_id": "V1", "hsn": "1",
         "pin_prefix": "40"},
        {"src": "B", "dst": "C", "invoice_id": "I2", "date": date(2024, 6, 2),
         "amount": 100000, "gst_amount": 18000, "vehicle_id": "V1", "hsn": "1",
         "pin_prefix": "40"},
        {"src": "C", "dst": "A", "invoice_id": "I3", "date": date(2024, 6, 3),
         "amount": 100000, "gst_amount": 18000, "vehicle_id": "V1", "hsn": "1",
         "pin_prefix": "40"},
    ]
    rings = run_pipeline(graph_source={"edges": edges, "member_meta": {}},
                          config=EngineConfig(hop_max=6, persist=False, propagate=False))
    assert rings, "expected at least one detected ring"
    t = rings[0].to_dict()["temporal"]
    assert t is not None
    assert t["velocity_inr_per_day"] > 0
