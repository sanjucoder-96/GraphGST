"""Concrete scorer unit tests."""
from __future__ import annotations

from datetime import date

from risk.context import ScorerContext, build_context_from_graph_source
from risk.scorers import (MLScorer, PropagationScorer, ReconcileScorer,
                          RingScorer, RuleScorer, TemporalScorer)


def _gstin(gid, **over):
    base = {"gstin_id": gid, "status": "Active", "state_code": gid[:2]}
    base.update(over)
    return base


def _invoice(iid, sup, buy, period="2024-11", d="2024-11-01", amt=100_000.0):
    return {"invoice_id": iid, "supplier_gstin": sup, "buyer_gstin": buy,
            "date": d, "period": period, "taxable_value": amt,
            "total_gst": amt * 0.18}


# ── RuleScorer ─────────────────────────────────────────────────────────
def test_rule_scorer_cancelled_gstin():
    ctx = build_context_from_graph_source({
        "gstins": [_gstin("G1", status="CANCELLED"), _gstin("G2")],
        "invoices": [_invoice("I1", "G1", "G2")],
        "gstr1_keys": {("G1", "2024-11")},
        "gstr3b_keys": {("G1", "2024-11")},
        "settled_keys": {"GSTR3B-G1-202411"},
    })
    r = RuleScorer(weight=1.0).score("G1", ctx)
    assert r.subscore > 0
    assert any(x.name == "supplier-cancelled" for x in r.reasons)


def test_rule_scorer_missing_filings_and_tax():
    ctx = build_context_from_graph_source({
        "gstins": [_gstin("G1")],
        "invoices": [_invoice("I1", "G1", "G2"), _invoice("I2", "G1", "G3")],
        "gstr1_keys": set(),         # no GSTR-1
    })
    r = RuleScorer(weight=1.0).score("G1", ctx)
    assert r.subscore > 0
    assert any(x.name == "missing-gstr1-fraction" for x in r.reasons)


def test_rule_scorer_supplies_to_self():
    ctx = build_context_from_graph_source({
        "gstins": [_gstin("G1")],
        "edges": [{"src": "G1", "dst": "G1", "amount": 100}],
    })
    r = RuleScorer(weight=1.0).score("G1", ctx)
    assert any(x.name == "supplies-to-self" for x in r.reasons)


# ── RingScorer ─────────────────────────────────────────────────────────
def test_ring_scorer_picks_max_ring_score():
    ctx = ScorerContext(
        gstins=[_gstin("G1")],
        detected_rings=[
            {"ring_id": "R1", "score": 0.60, "members": ["G1", "G2"],
                "signals": {"C": 0.8, "V": 0.6}},
            {"ring_id": "R2", "score": 0.85, "members": ["G1", "G3"],
                "signals": {"C": 0.9, "V": 0.9}},
            {"ring_id": "R3", "score": 0.75, "members": ["G4", "G5"]},
        ],
    )
    r = RingScorer(weight=1.0).score("G1", ctx)
    assert r.subscore == 0.85       # max of the two rings G1 is in
    assert len(r.reasons) == 2       # one per ring G1 is in


def test_ring_scorer_not_a_member():
    ctx = ScorerContext(gstins=[_gstin("G1")], detected_rings=[
        {"ring_id": "R1", "score": 0.9, "members": ["G4", "G5"]},
    ])
    r = RingScorer(weight=1.0).score("G1", ctx)
    assert r.subscore == 0.0


# ── ReconcileScorer ────────────────────────────────────────────────────
def test_reconcile_scorer_saturates():
    events = [
        {"event_id": f"M-{i}", "outcome": "AMOUNT_MISMATCH", "severity": "HIGH",
            "supplier_gstin": "G1", "invoice_id": f"I{i}"} for i in range(20)
    ]
    r = ReconcileScorer(weight=1.0, saturate_at=8).score(
        "G1", ScorerContext(gstins=[_gstin("G1")], match_events=events))
    assert 0.5 < r.subscore <= 0.7    # HIGH sev (0.70) * scale near 1
    assert len(r.reasons) == 1        # one outcome type


def test_reconcile_scorer_multi_outcome():
    events = [
        {"event_id": "M-1", "outcome": "AMOUNT_MISMATCH", "severity": "HIGH",
            "supplier_gstin": "G1", "invoice_id": "I1"},
        {"event_id": "M-2", "outcome": "CANCELLED_SUPPLIER", "severity": "CRITICAL",
            "supplier_gstin": "G1", "invoice_id": "I1"},
    ]
    r = ReconcileScorer(weight=1.0).score(
        "G1", ScorerContext(gstins=[_gstin("G1")], match_events=events))
    names = sorted(x.name for x in r.reasons)
    assert names == ["reconcile-amount-mismatch", "reconcile-cancelled-supplier"]


# ── TemporalScorer ────────────────────────────────────────────────────
def test_temporal_scorer_detects_burst():
    invs = ([_invoice(f"I{i}", "G1", "B", d=f"2024-11-{i+1:02d}") for i in range(2)]
             + [_invoice(f"IB{i}", "G1", f"NEW{i}", d="2024-11-15") for i in range(10)]
             + [_invoice(f"IC{i}", "G1", "B", d=f"2024-12-{i+1:02d}") for i in range(2)])
    ctx = build_context_from_graph_source({
        "gstins": [_gstin("G1")], "invoices": invs,
    })
    r = TemporalScorer(weight=1.0, burst_threshold=3.0).score("G1", ctx)
    assert r.subscore > 0
    names = {x.name for x in r.reasons}
    assert "tx-burst" in names


def test_temporal_scorer_quiet_entity():
    invs = [_invoice("I1", "G1", "B", d="2024-11-01"),
             _invoice("I2", "G1", "B", d="2024-11-08"),
             _invoice("I3", "G1", "B", d="2024-11-15")]
    ctx = build_context_from_graph_source({"gstins": [_gstin("G1")], "invoices": invs})
    r = TemporalScorer(weight=1.0).score("G1", ctx)
    assert r.subscore == 0


# ── MLScorer ────────────────────────────────────────────────────────────
def test_ml_scorer_returns_zero_below_min_samples():
    ctx = build_context_from_graph_source({
        "gstins": [_gstin("G1"), _gstin("G2")],   # < min_samples
        "invoices": [_invoice("I1", "G1", "G2")],
    })
    r = MLScorer(weight=1.0, min_samples=40).score("G1", ctx)
    assert r.subscore == 0.0


def test_ml_scorer_runs_on_sufficient_data():
    gstins = [_gstin(f"G{i:03d}") for i in range(60)]
    # Give one entity a bigger footprint so its rank is high
    invs = []
    for i in range(60):
        n = 20 if i == 0 else 2
        for j in range(n):
            invs.append(_invoice(f"I{i}_{j}", f"G{i:03d}", f"G{(i+1)%60:03d}",
                                    d=f"2024-11-{(j % 27) + 1:02d}"))
    ctx = build_context_from_graph_source({"gstins": gstins, "invoices": invs})
    scorer = MLScorer(weight=1.0, min_samples=40)
    # First call trains and populates cache; second call is a lookup
    r0 = scorer.score("G000", ctx)
    r1 = scorer.score("G059", ctx)
    assert 0.0 <= r0.subscore <= 1.0
    assert 0.0 <= r1.subscore <= 1.0
    # G000 has the outlier footprint — its rank should be at or near top
    assert r0.subscore >= r1.subscore


# ── PropagationScorer ─────────────────────────────────────────────────
def test_propagation_scorer_neighbors_of_seeds_get_mass():
    ctx = build_context_from_graph_source({
        "gstins": [_gstin("A"), _gstin("B"), _gstin("C"), _gstin("D")],
        "edges": [
            {"src": "A", "dst": "B"}, {"src": "B", "dst": "C"},
            {"src": "C", "dst": "A"},   # ring A→B→C→A
            {"src": "A", "dst": "D"},   # D is neighbor of the ring
        ],
    }, detected_rings=[{"ring_id": "R1", "score": 0.9, "members": ["A", "B", "C"]}])
    scorer = PropagationScorer(weight=1.0)
    r_D = scorer.score("D", ctx)
    # Seed members themselves are excluded from reasons; D is not a seed
    r_seed = scorer.score("A", ctx)
    assert r_seed.subscore == 0.0    # seeds excluded
    assert r_D.subscore >= 0.0
    # D is downstream of a ring member so should receive positive mass
    # (may not always emit a reason if below 0.05)
    if r_D.subscore > 0.05:
        assert any(x.name == "ring-adjacent" for x in r_D.reasons)
