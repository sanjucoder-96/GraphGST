"""Six-signal ring scorer with per-signal contribution attribution.

Every signal is normalised to [0, 1] so weights compare on equal
footing. The scorer is a pure function — no I/O — driven by the ring
dict (members + edges + optional member_meta) plus a small config bag.

Closure signal fix (Phase 3 revision)
-------------------------------------
The original `closure_strength` computed `sum(edge.gst_amount) /
originated_gst`, but `originated_gst` was itself the GST on the seed
edge — which was ALSO in the sum. Result: the ratio was >= 1 for any
ring with a valid seed, always clamped to 1.0, and the signal was
effectively binary (1.0 or 0.0).

The corrected formula excludes the seed edge from the numerator:

    C = clamp(returned / originated, 0, 1)

where:
    seed        = the edge leaving the canonical (lex-smallest) member
    originated  = seed.gst_amount
    returned    = sum(e.gst_amount for e in edges if e is not seed)

Interpretation: "of the GST that entered this ring at the seed, how
much of it came back around through the downstream hops?" A tight
circular refund shows returned ~= originated ~= 1.0; a leaky pattern
where later hops carry lower GST shows C < 1.

Other signals
-------------
V = value_similarity    = max(0, 1 - stdev(amounts) / mean(amounts))
T = temporal_compactness = max(0, 1 - date_span_days / window_days)
R = recurrence           = 1 - exp(-n_prior / tau), tau=3
N = network_signal       = 0.25*(shared_vehicle_frac + shared_director
                                  + shared_pin_prefix_frac
                                  + shared_hsn_frac)
H = historical_prior     = |{m in members : m ever seen in any prior Ring}|
                           / |members|

Final = sum_s (w_s * s), weights configurable, default 1/6 each.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Dict, Iterable, Mapping, Optional, Sequence

DEFAULT_WEIGHTS: Dict[str, float] = {
    "C": 1 / 6, "V": 1 / 6, "T": 1 / 6, "R": 1 / 6, "N": 1 / 6, "H": 1 / 6,
}

DEFAULT_WINDOW_DAYS = 30
RECURRENCE_TAU = 3.0


def _find_seed(edges: Sequence[dict], seed_src: str) -> Optional[dict]:
    return next((e for e in edges if e["src"] == seed_src), None)


def closure_strength(edges: Sequence[dict], canonical_members: Sequence[str]) -> float:
    """C — returned/originated GST, clamped to [0, 1].

    The seed edge is the outgoing edge from the canonical (lex-smallest)
    member. Its GST is the "originated" amount. The numerator sums the
    GST on all OTHER edges — the "returned" leg of the cycle. This
    formulation:
      * scores a perfectly balanced k-cycle where every edge carries
        equal GST at (k-1)/1 -> clamped to 1.0
      * scores a k-cycle where downstream edges carry less at
        sum(rest) / seed < 1.0
      * gives 0.0 when there is no seed edge in `edges` (e.g. after a
        counterfactual removal that dropped the seed).
    """
    if not edges:
        return 0.0
    if not canonical_members:
        return 0.0
    seed_src = canonical_members[0]
    seed = _find_seed(edges, seed_src)
    if seed is None:
        return 0.0
    originated = float(seed.get("gst_amount", 0) or 0)
    if originated <= 0:
        return 0.0
    returned = 0.0
    for e in edges:
        if e is seed:
            continue
        returned += float(e.get("gst_amount", 0) or 0)
    c = returned / originated
    if c < 0:
        return 0.0
    if c > 1:
        return 1.0
    return c


def value_similarity(edges: Sequence[dict]) -> float:
    amts = [float(e.get("amount", 0) or 0) for e in edges]
    if not amts:
        return 0.0
    m = mean(amts)
    if m <= 0:
        return 0.0
    s = pstdev(amts) if len(amts) > 1 else 0.0
    v = 1.0 - s / m
    return max(0.0, min(1.0, v))


def temporal_compactness(date_span_days: int, window_days: int = DEFAULT_WINDOW_DAYS) -> float:
    if window_days <= 0:
        return 0.0
    t = 1.0 - (float(date_span_days) / float(window_days))
    return max(0.0, min(1.0, t))


def recurrence(n_prior: int, tau: float = RECURRENCE_TAU) -> float:
    if n_prior <= 0:
        return 0.0
    return 1.0 - math.exp(-float(n_prior) / float(tau))


def _mode_fraction(edges: Sequence[dict], field: str) -> float:
    """Fraction-of-edges that share the mode value, rescaled so
    all-unique → 0 and all-same → 1.

    The naive `top / n` returns 1/n when every value is unique — that
    would treat "3 different vehicles across 3 edges" as a shared-vehicle
    signal of 1/3, silently poisoning the network_signal. Rescale to
    `(top - 1) / (n - 1)` so uniformly-distinct values contribute nothing.
    """
    n = len(edges)
    if n < 2:
        return 0.0
    vals = [e.get(field) for e in edges if e.get(field) is not None and e.get(field) != ""]
    if not vals:
        return 0.0
    top = max(vals.count(v) for v in set(vals))
    return (top - 1) / (n - 1)


def network_signal(
    edges: Sequence[dict],
    members: Sequence[str],
    member_meta: Optional[Mapping[str, Mapping]] = None,
) -> float:
    veh = _mode_fraction(edges, "vehicle_id")
    hsn = _mode_fraction(edges, "hsn")
    pin = _mode_fraction(edges, "pin_prefix")
    director = 0.0
    if member_meta:
        dirs = [set((member_meta.get(m) or {}).get("directors") or []) for m in members]
        if dirs and all(len(d) > 0 for d in dirs):
            common = set.intersection(*dirs)
            director = 1.0 if common else 0.0
    return 0.25 * (veh + director + pin + hsn)


def historical_prior(members: Sequence[str], seen_members: Iterable[str]) -> float:
    m = list(members)
    if not m:
        return 0.0
    seen = set(seen_members or [])
    hit = sum(1 for g in m if g in seen)
    return hit / len(m)


def score_ring(
    members: Sequence[str],
    edges: Sequence[dict],
    date_span_days: int,
    *,
    n_prior: int = 0,
    seen_members: Optional[Iterable[str]] = None,
    member_meta: Optional[Mapping[str, Mapping]] = None,
    weights: Optional[Mapping[str, float]] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Dict:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)
    signals = {
        "C": closure_strength(edges, members),
        "V": value_similarity(edges),
        "T": temporal_compactness(date_span_days, window_days=window_days),
        "R": recurrence(n_prior),
        "N": network_signal(edges, members, member_meta=member_meta),
        "H": historical_prior(members, seen_members or []),
    }
    contribution = {k: w[k] * signals[k] for k in signals}
    final = sum(contribution.values())
    if final > 0:
        share = {k: contribution[k] / final for k in contribution}
    else:
        share = {k: 0.0 for k in contribution}
    return {
        "signals": signals,
        "weights": w,
        "contribution": contribution,
        "share": share,
        "final": final,
    }
