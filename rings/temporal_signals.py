"""Ring-level temporal intelligence (audit Phase D).

Two well-defined, testable temporal descriptors computed from a detected
ring's edges. They are attached to the ring output for EXPLAINABILITY and
investigation — they are deliberately NOT folded into the six-signal score,
because tuning a new score term on the evaluation data would be the exact
threshold/feature overfitting the audit warns against. If a future ablation
on held-out data shows one of them adds discrimination, it can be promoted
into the scorer then.

V7 evaluation (WS7) — `cyclic_temporal_incoherence` stays DESCRIPTOR-ONLY.
The held-out promotion test is currently *vacuous* and would show no gain:
the synthetic generator plants every fraud ring with causally-coherent
(monotone) hop dates — the easy planter steps +1 day/hop, and the hard
planter draws `offs = sorted(...)` (`datagen/rings_hard.py:116`), so the loop
is monotone non-decreasing. The signal is therefore identically 0 on *every*
planted positive, and non-zero only on some legitimate hard-negative cycles
(which get independent random dates). An ablation on this data would show ≤ 0
marginal AUC/AP — a small loss, not a gain. Promotion must wait until (1) the
generator can plant a date-incoherent fraud subtype (a resale dated before its
supply) as labelled ground truth, and (2) a genuine held-out AP/AUC comparison
(with vs without the term) shows a strict, leakage-free improvement without
raising the hard-negative false-positive count. Until both hold, this is
evidence-only.

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


def cyclic_temporal_incoherence(edges: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Causality-violation motif ∈ [0, 1] — the fraction of hop→hop date
    orderings around the cycle that are IMPOSSIBLE for a single physical
    consignment.

    A carousel is a closed loop A→B→C→…→A. If real goods move, each member
    sells (its outgoing hop) no earlier than it was supplied (its incoming hop),
    so the hop dates around the loop are monotone non-decreasing with exactly ONE
    wrap-around descent (the closing edge). We count cyclic strict descents
    ``D = #{ i : date(edge_{(i+1) mod k}) < date(edge_i) }`` on the edges in
    cycle-traversal order, and report ``max(0, D-1) / max(1, k-1)``:

      * D ≤ 1  → 0.0  → a forward-in-time flow exists (real goods, or a
                        carefully-built fake) — nothing to see here.
      * D ≥ 2  → > 0  → at least one hop RESELLS before it was SUPPLIED
                        ("B sold to C on 2 Jun but only bought from A on 18 Jun"),
                        which is impossible for one consignment → paper carousel.

    Ties (same-day hops) are not descents, so a same-day loop scores 0 (already
    described by velocity/compactness). Rotation-invariant and O(k). Returns None
    if fewer than two hops or any hop lacks a parseable date.
    """
    dates = [_parse(e.get("date")) for e in edges]
    if len(dates) < 2 or any(d is None for d in dates):
        return None
    k = len(dates)
    descents = sum(1 for i in range(k) if dates[(i + 1) % k] < dates[i])
    return round(max(0, descents - 1) / max(1, k - 1), 4)


def temporal_descriptors(total_gst: float, date_span_days: int,
                          edges: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Bundle the temporal descriptors for a detected ring."""
    reg = inter_hop_regularity(edges)
    incoh = cyclic_temporal_incoherence(edges)
    return {
        "velocity_inr_per_day": velocity_inr_per_day(total_gst, date_span_days),
        "inter_hop_regularity": reg,
        "cyclic_temporal_incoherence": incoh,
        # human-readable investigative note
        "note": (
            f"₹{velocity_inr_per_day(total_gst, date_span_days):,.0f}/day over "
            f"{max(1, int(date_span_days))}d"
            + (f", cadence regularity {reg:.2f}" if reg is not None else "")
            + (f", IMPOSSIBLE loop timing {incoh:.2f} (resale precedes supply)"
               if incoh else "")
        ),
    }
