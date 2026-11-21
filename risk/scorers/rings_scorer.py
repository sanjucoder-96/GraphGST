"""RingScorer — subscore = max ring-score across rings the entity is in.

Reads `ctx.detected_rings` (the rings.engine output). If a GSTIN is a
member of multiple detected rings, we take the max score — the worst
ring you're in is the one that puts you at risk — plus a Reason per
ring pointing at the persisted Ring node so the UI can highlight the
whole ring on click.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..context import ScorerContext
from ..reasons import Reason
from .base import ScorerResult


class RingScorer:
    name = "rings"

    def __init__(self, weight: float = 0.35, min_ring_score: float = 0.45):
        """min_ring_score filters out incidental low-score cycles.

        The ring engine (Phase 3) enumerates every cycle in each SCC —
        many are legitimate multi-hop trade loops with low six-signal
        scores. Only rings above this threshold credit their members
        for risk. Default 0.45 comes from the Phase 3 bench: F1 peaks
        at threshold 0.55, but 0.45 still keeps recall = 87 % while
        filtering >90 % of noise.
        """
        self.weight = weight
        self.min_ring_score = min_ring_score

    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        # Fast path: read the pre-indexed rings_by_gstin (populated by
        # `build_context_from_graph_source`). Fall back to a full scan if
        # the caller hydrated ScorerContext by hand and skipped indexing.
        source = ctx.rings_by_gstin.get(gstin_id) if ctx.rings_by_gstin else None
        if source is None:
            source = [r for r in ctx.detected_rings if gstin_id in (r.get("members") or [])]
        member_of: List[Dict[str, Any]] = [
            r for r in source if float(r.get("score", 0.0)) >= self.min_ring_score
        ]
        if not member_of:
            return ScorerResult(subscore=0.0, reasons=[])

        subscore = max(float(r.get("score", 0.0)) for r in member_of)
        reasons: List[Reason] = []
        for r in sorted(member_of, key=lambda x: -float(x.get("score", 0))):
            rid = r.get("ring_id", "?")
            size = len(r.get("members") or [])
            rscore = float(r.get("score", 0.0))
            signals = r.get("signals") or {}
            top_signal = max(signals.items(), key=lambda kv: float(kv[1])) if signals else ("?", 0.0)
            reasons.append(Reason(
                name=f"in-detected-ring",
                weight=rscore,
                detail=(
                    f"Member of ring {rid} (size {size}, score {rscore:.2f}); "
                    f"strongest signal: {top_signal[0]}={float(top_signal[1]):.2f}"
                ),
                evidence={"node_type": "Ring", "node_id": rid,
                            "path": "Ring→INCLUDES→GSTIN",
                            "ring_score": rscore,
                            "ring_size": size},
            ))
        return ScorerResult(subscore=subscore, reasons=reasons)
