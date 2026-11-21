"""MLScorer — IsolationForest without feature leakage.

V5's IsolationForest used the rule-based `risk_score` as a feature AND
implicitly as the label — so the model just re-learned the rule engine.
This scorer computes features that are all derived directly from graph
structure and invoice statistics, NOT from any existing risk output:

    log_out_count           – log1p of outgoing invoice count
    log_out_amount          – log1p of total outgoing invoice value
    unique_buyers           – distinct buyer count
    outgoing_period_span    – (max_date - min_date) in days
    self_loop               – 1 if entity supplies to itself
    burst_ratio             – peak_week / median_week outgoing count

Trained on all entities in the context (not persisted — retraining per
composition pass is cheap at this scale), then anomaly-scored each. The
score maps to [0,1] via a rank normalization so it's comparable across
runs and does not depend on the raw decision function's arbitrary range.
"""
from __future__ import annotations

import logging
import math
from collections import Counter
from datetime import date, datetime
from statistics import median
from typing import Dict, List, Optional

from ..context import ScorerContext
from ..reasons import Reason
from .base import ScorerResult

logger = logging.getLogger(__name__)


def _parse_date(x):
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


def _features_for(gstin_id: str, ctx: ScorerContext) -> List[float]:
    invs = ctx.invoices_by_gstin.get(gstin_id, [])
    n = len(invs)
    total = sum(float(i.get("total_gst", 0) or 0) for i in invs)
    buyers = {i.get("buyer_gstin") for i in invs if i.get("buyer_gstin")}
    dates = [d for d in (_parse_date(i.get("date")) for i in invs) if d is not None]
    span = (max(dates) - min(dates)).days if len(dates) >= 2 else 0
    self_loop = 1.0 if gstin_id in ctx.neighbors_out.get(gstin_id, set()) else 0.0

    # burst_ratio (peak week / median week)
    if len(dates) >= 3:
        weekly = Counter(d.isocalendar()[:2] for d in dates)
        med = max(1.0, median(weekly.values()))
        burst = max(weekly.values()) / med
    else:
        burst = 1.0

    return [
        math.log1p(n),
        math.log1p(total),
        float(len(buyers)),
        float(span),
        self_loop,
        float(burst),
    ]


class MLScorer:
    name = "ml"

    def __init__(self, weight: float = 0.10, contamination: str | float = "auto",
                 min_samples: int = 40):
        self.weight = weight
        self.contamination = contamination
        self.min_samples = min_samples
        self._cached_scores: Optional[Dict[str, float]] = None
        self._cached_ctx_id: Optional[int] = None
        self._cached_features: Dict[str, List[float]] = {}

    def _fit_and_score(self, ctx: ScorerContext) -> Dict[str, float]:
        """Train IsolationForest on ALL entities in ctx and return a
        rank-normalized anomaly score in [0, 1] per gstin_id."""
        try:
            import numpy as np
            from sklearn.ensemble import IsolationForest
        except Exception as e:
            logger.warning("MLScorer sklearn unavailable: %s — subscores will be 0", e)
            return {}

        ids = ctx.all_gstin_ids()
        if len(ids) < self.min_samples:
            return {}

        feats = []
        keep_ids = []
        for gid in ids:
            f = _features_for(gid, ctx)
            self._cached_features[gid] = f
            if any(v != v for v in f):
                continue  # skip NaN
            feats.append(f)
            keep_ids.append(gid)

        if len(feats) < self.min_samples:
            return {}

        X = np.asarray(feats, dtype=np.float32)
        model = IsolationForest(
            n_estimators=200,
            max_samples="auto",
            contamination=self.contamination,
            random_state=42,
            n_jobs=1,
        )
        model.fit(X)
        raw = -model.score_samples(X)   # higher = more anomalous
        order = raw.argsort()             # ascending
        ranks = raw.argsort().argsort()   # noqa: F841 (kept for readability)
        # Rank normalization: rank / (n-1) ∈ [0, 1]
        norm = raw.argsort().argsort() / max(1, len(raw) - 1)
        return {gid: float(v) for gid, v in zip(keep_ids, norm)}

    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        if self._cached_scores is None or self._cached_ctx_id != id(ctx):
            self._cached_scores = self._fit_and_score(ctx)
            self._cached_ctx_id = id(ctx)
        if not self._cached_scores or gstin_id not in self._cached_scores:
            return ScorerResult(subscore=0.0, reasons=[])
        s = float(self._cached_scores[gstin_id])
        if s < 0.5:
            # Below-median entities don't earn a reason (subscore still emitted)
            return ScorerResult(subscore=s, reasons=[])
        feats = self._cached_features.get(gstin_id, [])
        return ScorerResult(subscore=s, reasons=[Reason(
            name="if-anomaly",
            weight=s,
            detail=(
                f"Isolation Forest rank-anomaly {s:.2f}: "
                f"log_out_count={feats[0]:.2f}, unique_buyers={int(feats[2])}, "
                f"period_span={int(feats[3])}d, burst_ratio={feats[5]:.1f}"
                if feats else f"Isolation Forest anomaly {s:.2f}"
            ),
            evidence={"node_type": "GSTIN", "node_id": gstin_id,
                        "feature_vector": feats,
                        "features": [
                            "log_out_count", "log_out_amount", "unique_buyers",
                            "outgoing_period_span", "self_loop", "burst_ratio",
                        ]},
        )])
