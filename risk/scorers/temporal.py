"""TemporalScorer — burst detection on per-GSTIN outgoing-invoice rate.

Simple, defensible: for each entity, bucket its outgoing invoices into
7-day windows and compare the max-week count to the median-week count.
A ratio ≥ `burst_threshold` fires a Reason. Also emits a "sudden new
neighbours" reason when the number of distinct counterparts in the
newest week exceeds the same-ratio test.

Neither test uses a black-box; both are ratios investigators can defend.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from statistics import median
from typing import Dict, List, Optional

from ..context import ScorerContext
from ..reasons import Reason
from .base import ScorerResult


def _parse_date(x) -> Optional[date]:
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


class TemporalScorer:
    name = "temporal"

    def __init__(self, weight: float = 0.10, burst_threshold: float = 4.0):
        self.weight = weight
        self.burst_threshold = burst_threshold

    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        invoices = ctx.invoices_by_gstin.get(gstin_id, [])
        if len(invoices) < 4:
            return ScorerResult(subscore=0.0, reasons=[])

        # Bucket into ISO week (year, week) → count, distinct counterparts
        weekly: Dict[tuple, int] = Counter()
        weekly_counterparts: Dict[tuple, set] = defaultdict(set)
        for inv in invoices:
            d = _parse_date(inv.get("date"))
            if d is None:
                continue
            key = d.isocalendar()[:2]           # (year, week)
            weekly[key] += 1
            buyer = inv.get("buyer_gstin")
            if buyer:
                weekly_counterparts[key].add(buyer)

        if not weekly:
            return ScorerResult(subscore=0.0, reasons=[])

        counts = list(weekly.values())
        med = max(1.0, median(counts))
        top_count = max(counts)
        ratio = top_count / med

        reasons: List[Reason] = []
        subscore = 0.0

        if ratio >= self.burst_threshold and len(counts) >= 3:
            # Saturating map: ratio 4 → 0.5, 8 → 0.75, 16 → 0.87
            w = 1.0 - pow(2.0, -(ratio - self.burst_threshold + 2) / 3.0)
            top_week = max(weekly.items(), key=lambda kv: kv[1])
            reasons.append(Reason(
                name="tx-burst",
                weight=min(1.0, max(0.0, w)),
                detail=(
                    f"Weekly outgoing invoice count peaked at {top_count} "
                    f"in {top_week[0][0]}-W{top_week[0][1]:02d} — "
                    f"{ratio:.1f}× the median week ({med:.1f})"
                ),
                evidence={"node_type": "GSTIN", "node_id": gstin_id,
                            "path": "GSTIN→ISSUED_INVOICE→Invoice",
                            "ratio": ratio, "peak_week": list(top_week[0])},
            ))
            subscore = max(subscore, w)

        # Sudden new-neighbor growth in the peak week
        top_key = max(weekly, key=lambda k: weekly[k])
        prev_counterparts: set = set()
        for k, cps in weekly_counterparts.items():
            if k < top_key:
                prev_counterparts.update(cps)
        new_in_peak = weekly_counterparts[top_key] - prev_counterparts
        if len(new_in_peak) >= 3 and len(new_in_peak) >= 0.5 * len(weekly_counterparts[top_key]):
            w2 = min(1.0, len(new_in_peak) / max(4, len(weekly_counterparts[top_key])))
            reasons.append(Reason(
                name="new-counterparts-burst",
                weight=w2,
                detail=(
                    f"{len(new_in_peak)} previously-unseen counterparts appeared "
                    f"in peak week {top_key[0]}-W{top_key[1]:02d} "
                    f"({len(new_in_peak)}/{len(weekly_counterparts[top_key])} of that week's buyers)"
                ),
                evidence={"node_type": "GSTIN", "node_id": list(new_in_peak)[:6],
                            "path": "GSTIN→ISSUED_INVOICE→Invoice→BILLED_TO→GSTIN"},
            ))
            subscore = max(subscore, w2)

        return ScorerResult(subscore=subscore, reasons=reasons)
