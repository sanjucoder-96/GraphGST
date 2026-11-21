"""Temporal filter — including the None-safe greedy sort fix."""
from datetime import date

from rings.temporal import (
    _date_span_days,
    _pick_best_combination,
    _none_safe_date_key,
    group_edges_by_pair,
    materialize_and_filter,
)


def _e(src, dst, d, iid="I"):
    return {
        "src": src, "dst": dst, "invoice_id": iid,
        "amount": 100, "gst_amount": 100, "date": d,
        "vehicle_id": None, "hsn": None, "pin_prefix": None,
    }


def test_group_by_pair():
    edges = [_e("A", "B", date(2026, 1, 1)), _e("A", "B", date(2026, 1, 2))]
    g = group_edges_by_pair(edges)
    assert len(g[("A", "B")]) == 2


def test_date_span_ignores_none():
    edges = [_e("A", "B", date(2026, 1, 1)), _e("A", "B", None)]
    assert _date_span_days(edges) == 0


def test_none_safe_key_pushes_none_last():
    a = _e("A", "B", date(2026, 1, 1))
    b = _e("A", "B", None)
    c = _e("A", "B", date(2026, 1, 5))
    ordered = sorted([b, c, a], key=_none_safe_date_key)
    # a first, then c, then None-dated b
    assert ordered[0]["date"] == date(2026, 1, 1)
    assert ordered[1]["date"] == date(2026, 1, 5)
    assert ordered[2]["date"] is None


def test_greedy_fallback_none_safe_no_crash():
    """REGRESSION: greedy sort must not TypeError on None dates.

    Build enough options per hop that the Cartesian product exceeds
    combo_cap so we go through the greedy path, and include None-dated
    edges in the mix.
    """
    # 3 hops, each with 12 options (12^3 = 1728 < 2048 default cap,
    # so we shrink the cap to force greedy).
    options = []
    for hop in range(3):
        opts = []
        for i in range(12):
            d = date(2026, 1, 1 + i) if i % 3 else None
            opts.append(_e(f"G{hop}", f"G{hop+1}", d, iid=f"i{hop}-{i}"))
        options.append(opts)
    # combo_cap=10 forces greedy for sure.
    best = _pick_best_combination(options, window_days=365, combo_cap=10)
    # Should not raise; may or may not find a valid combo depending on
    # median picks, but no TypeError from mixed-None comparison.
    assert best is None or len(best) == 3


def test_materialize_filters_by_window():
    cycle = ("A", "B", "C")
    edges_by_pair = {
        ("A", "B"): [_e("A", "B", date(2026, 1, 1))],
        ("B", "C"): [_e("B", "C", date(2026, 1, 3))],
        ("C", "A"): [_e("C", "A", date(2026, 1, 5))],
    }
    kept = materialize_and_filter([cycle], edges_by_pair, window_days=30)
    assert len(kept) == 1
    assert kept[0]["date_span_days"] == 4


def test_materialize_drops_out_of_window():
    cycle = ("A", "B", "C")
    edges_by_pair = {
        ("A", "B"): [_e("A", "B", date(2026, 1, 1))],
        ("B", "C"): [_e("B", "C", date(2026, 3, 1))],
        ("C", "A"): [_e("C", "A", date(2026, 6, 1))],
    }
    kept = materialize_and_filter([cycle], edges_by_pair, window_days=30)
    assert kept == []
