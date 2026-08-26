"""Ring-level temporal intelligence (audit Phase D).

Two well-defined, testable temporal descriptors computed from a detected
ring's edges. They are attached to the ring output for EXPLAINABILITY and
investigation — they are deliberately NOT folded into the six-signal score,
because tuning a new score term on the evaluation data would be the exact
threshold/feature overfitting the audit warns against. If a future ablation
on held-out data shows one of them adds discrimination, it can be promoted
into the scorer then.

Definitions
-----------
velocity_inr_per_day
    total GST circulating in the ring ÷ the ring's date span (days).
    "₹X of tax credit moved around this loop per day." A high number over a
    short span is the economic signature of round-tripping. O(1).

inter_hop_regularity ∈ [0, 1]
    1 − coefficient-of-variation of the consecutive inter-hop day gaps.
    Perfectly uniform cadence (e.g. one hop per day, machine-like) → 1.0;
    organic, irregular spacing → toward 0. Automated circular trading tends
    to be regular; genuine trade is bursty/irregular. Needs ≥2 gaps, else
    None. O(k log k) for the date sort.
"""
from __future__ import annotations

from datetime import date, datetime
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Sequence


def _parse(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    try:
        return date.fromisoformat(str(x))
    except (ValueError, TypeError):
        return None


def velocity_inr_per_day(total_gst: float, date_span_days: int) -> float:
    """GST circulated per day. Span is floored at 1 day (a same-day loop
    circulates its whole value in a single day)."""
    span = max(1, int(date_span_days))
    return round(float(total_gst) / span, 2)


def inter_hop_regularity(edges: Sequence[Dict[str, Any]]) -> Optional[float]:
    """1 − CV of consecutive inter-hop day gaps, clamped to [0, 1].

    Returns None if fewer than two gaps are available or the mean gap is 0
    (all hops on the same day → regularity is undefined; use velocity/span
    to describe a same-day loop instead)."""
    dates = sorted(d for d in (_parse(e.get("date")) for e in edges) if d is not None)
    if len(dates) < 3:
        return None
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    m = mean(gaps)
    if m <= 0:
        return None
    cv = pstdev(gaps) / m
    return round(max(0.0, min(1.0, 1.0 - cv)), 4)


def temporal_descriptors(total_gst: float, date_span_days: int,
                          edges: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Bundle the temporal descriptors for a detected ring."""
    reg = inter_hop_regularity(edges)
    return {
        "velocity_inr_per_day": velocity_inr_per_day(total_gst, date_span_days),
        "inter_hop_regularity": reg,
        # human-readable investigative note
        "note": (
            f"₹{velocity_inr_per_day(total_gst, date_span_days):,.0f}/day over "
            f"{max(1, int(date_span_days))}d"
            + (f", cadence regularity {reg:.2f}" if reg is not None else "")
        ),
    }
