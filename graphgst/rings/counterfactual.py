"""Break-the-ring analysis — pure in-memory, no Neo4j mutation.

For a detected ring with k edges we produce k hypothetical variants,
each missing one edge, and rescore. The edge whose removal drops the
final score the MOST is the recommended enforcement point.

R (recurrence) and H (historical prior) are ring-identity signals —
they don't change when we hypothetically drop an edge. We hold them
constant so the delta cleanly attributes to C, V, T, N.

Bias fix (Phase 3 revision)
---------------------------
The original implementation was systematically biased toward the seed
edge for two independent reasons:

  1. `closure_strength` included the seed edge in its own numerator
     (finding 1), so removing ANY non-seed edge left C clamped at 1.0
     while removing the seed edge zeroed C.

  2. Even after fixing (1), closure is defined relative to "the edge
     leaving canonical_members[0]". Removing that edge always yields
     C=0 (no seed left); removing any other edge merely trims the
     numerator. Deterministic seed bias.

The scoring fix (1) addresses the arithmetic asymmetry. Here we also
rotate `canonical_members` for each hypothetical: pick the
lex-smallest member whose outgoing edge is still in the reduced set as
the pseudo-seed. Every removal is scored under the same rules the
original ring was scored under, so the ranking reflects the fraud
pattern rather than lex-order.

Complexity O(k^2) per ring; for k <= 8 this is a rounding error.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .canonical import canonicalize
from .scoring import (
    DEFAULT_WEIGHTS,
    closure_strength,
    network_signal,
    temporal_compactness,
    value_similarity,
)


def _date_span_days(edges: Sequence[dict]) -> int:
    dates = [e["date"] for e in edges if e.get("date") is not None]
    if not dates:
        return 0
    return (max(dates) - min(dates)).days


def _rotate_members_for_reduced(
    members: Sequence[str], reduced_edges: Sequence[dict]
) -> Tuple[str, ...]:
    """Choose a fair pseudo-seed for a hypothetical (edge-removed) ring.

    Pick the lex-smallest member whose outgoing edge is STILL present
    in `reduced_edges` and rotate members to start with it. This makes
    C on the reduced ring symmetric to how C was computed on the
    original ring — every hypothetical gets a valid seed if one exists.
    """
    members = tuple(members)
    if not members or not reduced_edges:
        return members
    active_srcs = {e["src"] for e in reduced_edges}
    candidates = sorted(m for m in members if m in active_srcs)
    if not candidates:
        return members
    seed = candidates[0]
    idx = members.index(seed)
    return tuple(members[idx:] + members[:idx])


def _recompute_variable_signals(
    members: Sequence[str],
    edges: Sequence[dict],
    window_days: int,
    member_meta: Optional[Dict[str, Dict]],
) -> Dict[str, float]:
    return {
        "C": closure_strength(edges, members),
        "V": value_similarity(edges),
        "T": temporal_compactness(_date_span_days(edges), window_days=window_days),
        "N": network_signal(edges, members, member_meta=member_meta),
    }


def analyse_break(
    ring: Dict[str, Any],
    *,
    window_days: int = 30,
    member_meta: Optional[Dict[str, Dict]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Return per-edge score-drops + the recommended break edge."""
    members = tuple(ring["members"])
    edges = list(ring["edges"])
    if not edges:
        return {"break_edge": None, "per_edge": [], "tied_alternatives": []}

    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    R_const = float(ring.get("signals", {}).get("R", 0.0))
    H_const = float(ring.get("signals", {}).get("H", 0.0))
    orig_final = float(ring.get("score", ring.get("final", 0.0)))

    per_edge: List[Dict[str, Any]] = []
    for i, e in enumerate(edges):
        reduced = edges[:i] + edges[i + 1 :]
        # Fair seed for the reduced ring — see docstring.
        rotated_members = _rotate_members_for_reduced(members, reduced)
        variable = _recompute_variable_signals(
            rotated_members, reduced, window_days, member_meta
        )
        new_final = (
            w["C"] * variable["C"]
            + w["V"] * variable["V"]
            + w["T"] * variable["T"]
            + w["N"] * variable["N"]
            + w["R"] * R_const
            + w["H"] * H_const
        )
        per_edge.append(
            {
                "src": e["src"],
                "dst": e["dst"],
                "invoice_id": e.get("invoice_id"),
                "score_after": new_final,
                "score_drop": orig_final - new_final,
            }
        )

    per_edge_sorted = sorted(
        per_edge, key=lambda r: (-r["score_drop"], r["src"], r["dst"])
    )
    top = per_edge_sorted[0]
    tied = [
        r for r in per_edge_sorted[1:] if abs(r["score_drop"] - top["score_drop"]) < 1e-9
    ]
    return {
        "break_edge": top,
        "per_edge": per_edge,
        "tied_alternatives": tied,
    }


def canonicalise_ring_members(members: Sequence[str]) -> Tuple[str, ...]:
    return canonicalize(members)
