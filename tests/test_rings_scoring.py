"""Six-signal scoring math — with the closure_strength fix (Phase 3 rev).

The key regression test is `test_closure_excludes_seed_from_numerator`:
under the old buggy formula every ring with a valid seed clamped to
C=1.0. Under the fixed formula C reflects the actual return ratio.
"""
import math
from datetime import date, timedelta

import pytest

from rings.scoring import (
    DEFAULT_WEIGHTS,
    closure_strength,
    historical_prior,
    network_signal,
    recurrence,
    score_ring,
    temporal_compactness,
    value_similarity,
)


def _edges(amts, dates=None, vehicles=None, hsns=None, pins=None, gst=None, src_dst=None):
    n = len(amts)
    if dates is None:
        dates = [date(2026, 1, 1)] * n
    if vehicles is None:
        vehicles = [None] * n
    if hsns is None:
        hsns = [None] * n
    if pins is None:
        pins = [None] * n
    if gst is None:
        gst = amts
    if src_dst is None:
        src_dst = [(f"G000{i}", f"G000{(i+1) % n}") for i in range(n)]
    return [
        {
            "src": src_dst[i][0],
            "dst": src_dst[i][1],
            "invoice_id": f"INV{i}",
            "amount": amts[i],
            "gst_amount": gst[i],
            "date": dates[i],
            "vehicle_id": vehicles[i],
            "hsn": hsns[i],
            "pin_prefix": pins[i],
        }
        for i in range(n)
    ]


# ── closure_strength: post-fix (Phase 3 rev) ─────────────────────────

def test_closure_excludes_seed_from_numerator():
    """REGRESSION: under the old bug the seed was counted in `returned`
    so the ratio was >= 1 for any ring with a valid seed and clamped
    to 1.0. Post-fix, `returned` excludes the seed edge, so a k-cycle
    with equal GST on every edge scores (k-1)/1 clamped to 1.0, but a
    ring where downstream edges carry less GST scores strictly <1.
    """
    members = ("G0000", "G0001", "G0002")
    # Seed GST=100, other two edges GST=30 each. Returned = 60,
    # originated = 100, C = 0.6. Old bug returned 1.0.
    e = _edges(
        [100, 30, 30], gst=[100, 30, 30],
        src_dst=[("G0000", "G0001"), ("G0001", "G0002"), ("G0002", "G0000")],
    )
    assert closure_strength(e, members) == pytest.approx(0.6)


def test_closure_perfect_cycle_clamps_to_1():
    """Equal GST on every edge: returned/originated = (k-1) > 1 so clamp."""
    members = ("G0000", "G0001", "G0002")
    e = _edges(
        [100, 100, 100], gst=[100, 100, 100],
        src_dst=[("G0000", "G0001"), ("G0001", "G0002"), ("G0002", "G0000")],
    )
    assert closure_strength(e, members) == 1.0


def test_closure_zero_when_no_seed_edge():
    members = ("G0000", "G0001")
    e = _edges([10, 10], src_dst=[("G0001", "G0002"), ("G0002", "G0003")])
    assert closure_strength(e, members) == 0.0


def test_closure_leaky_below_one():
    """Downstream drops all GST to 0: nothing returned -> C = 0."""
    members = ("G0000", "G0001", "G0002")
    e = _edges(
        [1000, 0, 0], gst=[1000, 0, 0],
        src_dst=[("G0000", "G0001"), ("G0001", "G0002"), ("G0002", "G0000")],
    )
    assert closure_strength(e, members) == 0.0


def test_closure_discriminates():
    """REGRESSION: post-fix the signal must actually discriminate rings.

    Old bug: two clearly-different rings both scored 1.0. Post-fix:
    a tight ring scores near 1.0, a leaky ring scores much lower.
    """
    members = ("G0000", "G0001", "G0002")
    tight = _edges(
        [100, 100, 100], gst=[100, 100, 100],
        src_dst=[("G0000", "G0001"), ("G0001", "G0002"), ("G0002", "G0000")],
    )
    leaky = _edges(
        [100, 20, 10], gst=[100, 20, 10],
        src_dst=[("G0000", "G0001"), ("G0001", "G0002"), ("G0002", "G0000")],
    )
    c_tight = closure_strength(tight, members)
    c_leaky = closure_strength(leaky, members)
    assert c_tight > c_leaky
    assert c_tight == pytest.approx(1.0)
    assert c_leaky == pytest.approx(0.3)


# ── other signals ──────────────────────────────────────────────────────

def test_value_similarity_identical():
    e = _edges([500, 500, 500])
    assert value_similarity(e) == 1.0


def test_value_similarity_disparate():
    e = _edges([100, 900, 500])
    assert value_similarity(e) < 0.5


def test_value_similarity_mean_zero_safe():
    e = _edges([0, 0, 0])
    assert value_similarity(e) == 0.0


def test_temporal_compactness_bounds():
    assert temporal_compactness(0, window_days=30) == 1.0
    assert temporal_compactness(30, window_days=30) == 0.0
    assert temporal_compactness(60, window_days=30) == 0.0  # clamped


def test_recurrence_saturating():
    """REGRESSION: with the persistence fix, n_prior can grow beyond 1.

    The pure math here just checks the curve is monotone-saturating.
    The integration test in test_rings_persist verifies that the
    Ring.sighting_count actually grows from run to run.
    """
    assert recurrence(0) == 0.0
    r1 = recurrence(1)
    r3 = recurrence(3)
    r10 = recurrence(10)
    assert 0 < r1 < r3 < r10 < 1.0
    assert r3 == pytest.approx(1 - math.exp(-1), abs=1e-9)
    assert r10 > 0.95


def test_network_signal_all_shared():
    members = ("G0000", "G0001", "G0002")
    e = _edges(
        [100, 100, 100],
        vehicles=["MH01"] * 3, hsns=["7208"] * 3, pins=["400"] * 3,
    )
    meta = {m: {"directors": ["D1"]} for m in members}
    assert network_signal(e, members, member_meta=meta) == pytest.approx(1.0)


def test_network_signal_none_shared():
    members = ("G0000", "G0001", "G0002")
    e = _edges(
        [100, 100, 100],
        vehicles=["MH01", "MH02", "MH03"],
        hsns=["7208", "7209", "7210"],
        pins=["400", "401", "402"],
    )
    meta = {m: {"directors": [f"D_{m}"]} for m in members}
    assert network_signal(e, members, member_meta=meta) == pytest.approx(0.0)


def test_historical_prior():
    assert historical_prior(["A", "B", "C"], []) == 0.0
    assert historical_prior(["A", "B", "C"], ["A", "B", "C"]) == 1.0
    assert historical_prior(["A", "B", "C"], ["B"]) == pytest.approx(1 / 3)


def test_score_ring_share_sums_to_one():
    members = ("G0000", "G0001", "G0002")
    e = _edges([100, 90, 80], gst=[100, 90, 80],
               src_dst=[("G0000", "G0001"), ("G0001", "G0002"), ("G0002", "G0000")])
    out = score_ring(members, e, date_span_days=10, n_prior=2)
    assert out["final"] > 0
    assert sum(out["share"].values()) == pytest.approx(1.0)


def test_score_ring_zero_signals_zero_share():
    members = ("G0000", "G0001")
    e = _edges([0, 0], gst=[0, 0], src_dst=[("G0999", "G0001"), ("G0001", "G0999")])
    out = score_ring(members, e, date_span_days=999, window_days=30)
    assert out["final"] == 0.0
    assert all(v == 0.0 for v in out["share"].values())
