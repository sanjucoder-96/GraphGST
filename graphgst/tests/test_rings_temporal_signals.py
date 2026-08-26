"""Tests for ring-level temporal descriptors (audit Phase D)."""
from __future__ import annotations

from datetime import date

from rings.temporal_signals import (inter_hop_regularity, temporal_descriptors,
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


def test_temporal_descriptors_bundle():
    d = temporal_descriptors(300000, 3, _edges([1, 2, 3, 4]))
    assert d["velocity_inr_per_day"] == 100000.0
    assert 0.0 <= d["inter_hop_regularity"] <= 1.0
    assert "note" in d and "day" in d["note"]


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
