"""Break-edge counterfactual — post-fix (Phase 3 rev).

The original implementation was deterministically biased toward the
seed edge (edge leaving the lex-smallest member) because closure_strength
depended on that specific edge. These tests verify:

  * With the closure fix + members-rotation-per-hypothetical, removing
    non-seed edges can score higher than removing the seed edge when
    the ring's fraud pattern points that way.
  * The recommended break edge is a function of the DATA, not lex order.
"""
from datetime import date

import pytest

from rings.counterfactual import analyse_break, _rotate_members_for_reduced
from rings.scoring import DEFAULT_WEIGHTS, score_ring


def _edge(src, dst, gst, amount=None, d=None, invoice="I"):
    return {
        "src": src, "dst": dst, "invoice_id": invoice,
        "amount": amount if amount is not None else gst,
        "gst_amount": gst,
        "date": d or date(2026, 1, 1),
        "vehicle_id": None, "hsn": None, "pin_prefix": None,
    }


def test_rotate_members_picks_lex_smallest_with_active_seed():
    members = ("A", "B", "C")
    reduced = [_edge("B", "C", 10), _edge("C", "A", 10)]
    # "A" has no outgoing edge in reduced -> pseudo-seed rotates to "B".
    rotated = _rotate_members_for_reduced(members, reduced)
    assert rotated[0] == "B"


def test_rotate_members_all_active_stays_at_lex_smallest():
    members = ("A", "B", "C")
    edges = [_edge("A", "B", 10), _edge("B", "C", 10), _edge("C", "A", 10)]
    assert _rotate_members_for_reduced(members, edges)[0] == "A"


def test_break_edge_not_always_seed():
    """REGRESSION for the counterfactual seed-bias finding.

    Under the old bug the seed edge (edge leaving the lex-smallest
    member) was always recommended, because closure_strength keyed on
    it. After the fix, the recommendation must reflect the DATA.

    Construction:  edges A→B(1), B→C(1000), C→A(2000).
    Removing the seed A→B enables a rebalanced (B→C, C→A) pair that
    scores HIGHER in both closure (1.0) and value_similarity (0.67),
    so its score_drop is NEGATIVE — a very unappealing enforcement
    target. Removing B→C or C→A each break the return chain and drop
    the score. So the recommendation must land on a non-seed edge.
    """
    members = ("A", "B", "C")
    edges = [
        _edge("A", "B", 1, invoice="seed"),
        _edge("B", "C", 1000, invoice="mid"),
        _edge("C", "A", 2000, invoice="tail"),
    ]
    scored = score_ring(members, edges, date_span_days=5)
    ring = {
        "members": members,
        "edges": edges,
        "score": scored["final"],
        "signals": scored["signals"],
    }
    out = analyse_break(ring, window_days=30)
    per_edge = {(e["src"], e["dst"]): e for e in out["per_edge"]}
    assert set(per_edge.keys()) == {("A", "B"), ("B", "C"), ("C", "A")}
    # Data-dependence: three edges must NOT produce identical drops.
    drops = {k: v["score_drop"] for k, v in per_edge.items()}
    assert len(set(round(d, 6) for d in drops.values())) > 1, drops
    # Seed edge (A→B) removal INCREASES the score (score_drop < 0), so
    # it must not be the break_edge recommendation.
    assert drops[("A", "B")] < 0
    assert (out["break_edge"]["src"], out["break_edge"]["dst"]) != ("A", "B")


def test_break_edge_reflects_v_signal_change():
    """With amounts wildly disparate on one edge, removing THAT edge
    should improve value_similarity the most — so the score drop is
    dominated by V changes, not lex order.
    """
    members = ("A", "B", "C")
    edges = [
        _edge("A", "B", 100, amount=100, invoice="e1"),
        _edge("B", "C", 100, amount=100, invoice="e2"),
        _edge("C", "A", 100, amount=100000, invoice="outlier"),
    ]
    scored = score_ring(members, edges, date_span_days=1)
    ring = {"members": members, "edges": edges,
            "score": scored["final"], "signals": scored["signals"]}
    out = analyse_break(ring, window_days=30)
    per_edge = {(e["src"], e["dst"]): e for e in out["per_edge"]}
    # Removing the outlier makes remaining edges uniform (V rises).
    # score_after should be HIGHER for the outlier removal than for
    # removing a uniform edge — i.e. score_drop is NEGATIVE (or at least
    # the smallest) for the outlier. The break edge (largest drop)
    # should NOT be the outlier.
    outlier_drop = per_edge[("C", "A")]["score_drop"]
    uniform_drop = per_edge[("A", "B")]["score_drop"]
    assert uniform_drop >= outlier_drop


def test_break_edge_ties_stable():
    """When two removals produce equal drops the tie-break is
    deterministic (lex on src, dst)."""
    members = ("A", "B", "C")
    # Fully symmetric ring: all removals produce identical drops.
    edges = [
        _edge("A", "B", 100), _edge("B", "C", 100), _edge("C", "A", 100),
    ]
    scored = score_ring(members, edges, date_span_days=0)
    ring = {"members": members, "edges": edges,
            "score": scored["final"], "signals": scored["signals"]}
    out = analyse_break(ring, window_days=30)
    assert out["break_edge"] is not None
    # tied_alternatives should list the other two.
    assert len(out["tied_alternatives"]) == 2


def test_analyse_break_empty_edges():
    ring = {"members": ("A", "B"), "edges": [],
            "score": 0.0, "signals": {"R": 0, "H": 0}}
    out = analyse_break(ring)
    assert out["break_edge"] is None
