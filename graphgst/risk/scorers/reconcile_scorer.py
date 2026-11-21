"""ReconcileScorer — subscore from MatchEvents where this GSTIN is the supplier.

Aggregates event severities into a bounded subscore and emits one Reason
per distinct outcome type touching the entity. Severity table (INFO/LOW/
MED/HIGH/CRITICAL) maps to numeric weights.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import List

from ..context import ScorerContext
from ..reasons import Reason
from .base import ScorerResult

_SEV_WEIGHT = {
    "INFO": 0.0, "LOW": 0.15, "MEDIUM": 0.40, "MED": 0.40,
    "HIGH": 0.70, "CRITICAL": 1.00,
}


class ReconcileScorer:
    name = "reconcile"

    def __init__(self, weight: float = 0.15, saturate_at: int = 8):
        """`saturate_at` = number of high-severity events at which the
        scorer's subscore hits its per-event ceiling. Prevents a supplier
        with 300 amount-mismatches from dwarfing a supplier with one
        cancelled-status event."""
        self.weight = weight
        self.saturate_at = max(1, saturate_at)

    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        # Fast path via the pre-indexed events_by_supplier; fall back to
        # a full scan when a caller hand-built ScorerContext.
        related = (ctx.events_by_supplier.get(gstin_id)
                     if ctx.events_by_supplier else None)
        if related is None:
            related = [e for e in ctx.match_events
                        if e.get("supplier_gstin") == gstin_id]
        if not related:
            return ScorerResult(subscore=0.0, reasons=[])

        by_outcome: dict[str, list[dict]] = defaultdict(list)
        for e in related:
            by_outcome[e.get("outcome", "?")].append(e)

        reasons: List[Reason] = []
        best_weight = 0.0
        for outcome, evs in by_outcome.items():
            sev = evs[0].get("severity", "MEDIUM")
            base = _SEV_WEIGHT.get(sev, 0.4)
            # Sub-linear scaling in n
            count = len(evs)
            scale = 1.0 - pow(0.5, count / self.saturate_at)  # asymptotes to 1
            w = base * scale
            if w > best_weight:
                best_weight = w
            example_ids = [e["invoice_id"] for e in evs[:3] if e.get("invoice_id")]
            reasons.append(Reason(
                name=f"reconcile-{outcome.lower().replace('_','-')}",
                weight=w,
                detail=(
                    f"{count} {outcome} event(s) — severity {sev} · "
                    f"e.g. invoice(s) {', '.join(example_ids) or '?'}"
                ),
                evidence={
                    "node_type": "MatchEvent",
                    "node_id": [e["event_id"] for e in evs[:5]],
                    "path": "MatchEvent→ABOUT→Invoice",
                    "outcome": outcome, "severity": sev, "count": count,
                },
            ))
        return ScorerResult(subscore=best_weight, reasons=reasons)
