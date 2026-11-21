"""Adversarial edge-case hardening for the detection core (audit Phase I).

These tests deliberately feed degenerate, malformed, extreme, and boundary
inputs to the ring engine and the pure scorers. The contract under test is
robustness: the engine must NEVER raise on bad data — it degrades to a sane,
documented result (usually "no ring" or a clamped score). Every case here is a
shape a real ingest could produce (a missing field, a zero-amount credit note,
a same-day loop, a self-dealing invoice).

If any of these ever starts raising, that is a regression in input hardening,
not a test to relax.
"""
from datetime import date

import pytest

from rings.engine import EngineConfig, run_pipeline
from rings.scoring import (closure_strength, network_signal, score_ring,
                           temporal_compactness, value_similarity)

CFG = EngineConfig(persist=False, propagate=False, use_gds=False)


def _edge(src, dst, gst, inv, d=None, amount=None, vehicle=None, hsn=None, pin=None):
    return {
        "src": src, "dst": dst, "invoice_id": inv,
        "amount": amount if amount is not None else gst,
        "gst_amount": gst,
        "date": d if d is not None else date(2026, 1, 1),
        "vehicle_id": vehicle, "hsn": hsn, "pin_prefix": pin,
    }


def _run(edges, member_meta=None):
    return run_pipeline(CFG, graph_source={"edges": edges, "member_meta": member_meta or {}})


# ── Degenerate graphs ──────────────────────────────────────────────────

def test_empty_graph():
    assert _run([]) == []


def test_missing_edges_key():
    # graph_source with no 'edges' at all must not KeyError.
    assert run_pipeline(CFG, graph_source={"member_meta": {}}) == []


def test_single_edge_no_cycle():
    assert _run([_edge("A", "B", 100, "i1")]) == []


def test_self_loop_is_not_a_ring():
    # A->A is an SCC of size 1; the min_size=2 gate must exclude it.
    assert _run([_edge("A", "A", 100, "i1")]) == []


def test_two_disconnected_rings_both_found():
    edges = [
        _edge("A", "B", 100, "a1"), _edge("B", "C", 100, "a2"), _edge("C", "A", 100, "a3"),
        _edge("X", "Y", 100, "x1"), _edge("Y", "Z", 100, "x2"), _edge("Z", "X", 100, "x3"),
    ]
    rings = _run(edges)
    assert len(rings) == 2
    member_sets = {frozenset(r.members) for r in rings}
    assert frozenset({"A", "B", "C"}) in member_sets
    assert frozenset({"X", "Y", "Z"}) in member_sets


def test_overlapping_rings_sharing_a_node():
    # Figure-8: two 3-cycles sharing only node A. Both are in one SCC and both
    # must be enumerated and scored independently.
    edges = [
        _edge("A", "B", 100, "b1"), _edge("B", "C", 100, "b2"), _edge("C", "A", 100, "b3"),
        _edge("A", "D", 100, "d1"), _edge("D", "E", 100, "d2"), _edge("E", "A", 100, "d3"),
    ]
    rings = _run(edges)
    member_sets = {frozenset(r.members) for r in rings}
    assert frozenset({"A", "B", "C"}) in member_sets
    assert frozenset({"A", "D", "E"}) in member_sets
    # Every detected ring contains the shared node or is one of the two loops.
    assert all("A" in r.members for r in rings)


def test_two_cycle_minimal_ring():
    # A->B->A: the smallest possible loop (mutual invoicing).
    rings = _run([_edge("A", "B", 100, "i1"), _edge("B", "A", 100, "i2")])
    assert len(rings) == 1
    assert sorted(rings[0].members) == ["A", "B"]


# ── Malformed / missing fields ─────────────────────────────────────────

def test_missing_gst_amount_does_not_crash():
    edges = [
        {"src": "A", "dst": "B", "invoice_id": "i1", "amount": 100, "date": date(2026, 1, 1)},
        {"src": "B", "dst": "C", "invoice_id": "i2", "amount": 100, "date": date(2026, 1, 2)},
        {"src": "C", "dst": "A", "invoice_id": "i3", "amount": 100, "date": date(2026, 1, 3)},
    ]
    rings = _run(edges)  # gst_amount absent everywhere
    assert len(rings) == 1
    # No GST anywhere → closure has no originated amount → C == 0.0, no crash.
    assert rings[0].signals["C"] == 0.0


def test_all_none_dates_does_not_crash():
    edges = [
        _edge("A", "B", 100, "i1", d=None), _edge("B", "C", 100, "i2", d=None),
        _edge("C", "A", 100, "i3", d=None),
    ]
    # date defaults to a real date in _edge; force them None here explicitly.
    for e in edges:
        e["date"] = None
    rings = _run(edges)
    assert len(rings) == 1
    # Span undefined → 0 → temporally compact by the documented convention.
    assert rings[0].date_span_days == 0


def test_none_amounts_do_not_crash():
    edges = [
        _edge("A", "B", None, "i1"), _edge("B", "C", None, "i2"), _edge("C", "A", None, "i3"),
    ]
    for e in edges:
        e["amount"] = None
    rings = _run(edges)
    assert len(rings) == 1
    assert 0.0 <= rings[0].score <= 1.0


# ── Extreme magnitudes ─────────────────────────────────────────────────

def test_extreme_large_amounts():
    big = 10 ** 12
    edges = [
        _edge("A", "B", big, "i1", amount=big), _edge("B", "C", big, "i2", amount=big),
        _edge("C", "A", big, "i3", amount=big),
    ]
    rings = _run(edges)
    assert len(rings) == 1
    assert rings[0].signals["C"] == 1.0          # balanced loop still clamps to 1
    assert 0.0 <= rings[0].score <= 1.0          # score stays normalized
    assert rings[0].total_gst == 3 * big


def test_zero_amounts_ring():
    edges = [
        _edge("A", "B", 0, "i1", amount=0), _edge("B", "C", 0, "i2", amount=0),
        _edge("C", "A", 0, "i3", amount=0),
    ]
    rings = _run(edges)
    assert len(rings) == 1
    assert rings[0].signals["C"] == 0.0          # no originated GST
    assert rings[0].signals["V"] == 0.0          # mean amount 0 → V floored


def test_negative_amounts_do_not_produce_out_of_range_signals():
    # A credit-note style negative should not push any signal outside [0,1].
    edges = [
        _edge("A", "B", -100, "i1", amount=-100), _edge("B", "C", 100, "i2", amount=100),
        _edge("C", "A", 100, "i3", amount=100),
    ]
    rings = _run(edges)
    assert len(rings) == 1
    for k, v in rings[0].signals.items():
        assert 0.0 <= v <= 1.0, f"signal {k}={v} out of range"


# ── Temporal boundaries ────────────────────────────────────────────────

def test_same_day_ring_is_maximally_compact():
    d = date(2026, 6, 1)
    edges = [_edge("A", "B", 100, "i1", d), _edge("B", "C", 100, "i2", d), _edge("C", "A", 100, "i3", d)]
    rings = _run(edges)
    assert len(rings) == 1
    assert rings[0].date_span_days == 0
    assert rings[0].signals["T"] == 1.0


def test_ring_outside_window_is_filtered():
    # Span 60 days with default window 30 → no invoice combination fits → dropped.
    edges = [
        _edge("A", "B", 100, "i1", date(2026, 1, 1)),
        _edge("B", "C", 100, "i2", date(2026, 2, 1)),
        _edge("C", "A", 100, "i3", date(2026, 3, 3)),
    ]
    assert _run(edges) == []


# ── Pure-scorer boundary contracts ─────────────────────────────────────

def test_scorer_functions_never_exceed_unit_interval():
    assert closure_strength([], []) == 0.0
    assert value_similarity([]) == 0.0
    assert temporal_compactness(0, 0) == 0.0          # window 0 guarded
    assert temporal_compactness(-5, 30) == 1.0        # negative span clamps up
    assert temporal_compactness(999, 30) == 0.0       # huge span clamps down
    assert network_signal([], []) == 0.0


def test_score_ring_bounds_on_garbage():
    out = score_ring(["A"], [{"src": "A", "dst": "A"}], date_span_days=-3)
    assert 0.0 <= out["final"] <= 1.0
    assert all(0.0 <= v <= 1.0 for v in out["signals"].values())


@pytest.mark.parametrize("span", [0, 1, 29, 30, 31, 10 ** 6])
def test_temporal_compactness_is_bounded_for_any_span(span):
    v = temporal_compactness(span, 30)
    assert 0.0 <= v <= 1.0
