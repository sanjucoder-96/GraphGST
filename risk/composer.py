"""RiskComposer — runs every scorer against a shared ScorerContext and
composes one final risk score per GSTIN.

Composition semantics
---------------------
Each scorer emits `ScorerResult(subscore ∈ [0,1], reasons=[Reason])`.
The composer:

  1. Clamps subscore into [0, 1].
  2. Multiplies by the scorer's registered global weight
     (sum-of-weights is normalized to 1.0 up front, so weights are
     relative not absolute).
  3. Sums contributions into `score`.
  4. Tags every reason with `scorer=<name>` and
     `contribution=reason.weight × scorer.weight` so the UI can group
     them and show per-reason % contribution to the final.
  5. Dedupes reasons by (scorer, name, evidence.node_id).
  6. Returns a `ComposedRisk` with the band lookup applied.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .context import ScorerContext
from .reasons import Reason, ReasonBand, band_for, dedupe_reasons
from .scorers.base import Scorer, ScorerResult

logger = logging.getLogger(__name__)


@dataclass
class ComposerConfig:
    scorers: Sequence[Scorer]
    top_reasons: int = 8

    def normalized_weights(self) -> Dict[str, float]:
        total = sum(max(0.0, s.weight) for s in self.scorers) or 1.0
        return {s.name: max(0.0, s.weight) / total for s in self.scorers}


@dataclass
class ComposedRisk:
    gstin_id: str
    score: float                       # ∈ [0, 1]
    band: str                          # LOW / MED / HIGH / CRITICAL
    contributions: Dict[str, float]    # scorer name → contribution to score
    reasons: List[Dict[str, Any]]      # top-N flat reasons, sorted by contribution
    # Meta
    scorers_fired: List[str]           # scorers that emitted ≥1 reason
    scorers_run: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RiskComposer:
    def __init__(self, config: ComposerConfig):
        self.config = config
        self._weights = config.normalized_weights()

    def compose(self, gstin_id: str, ctx: ScorerContext) -> ComposedRisk:
        contributions: Dict[str, float] = {}
        fired: List[str] = []
        run: List[str] = []
        all_reasons: List[Reason] = []

        for scorer in self.config.scorers:
            run.append(scorer.name)
            try:
                r: ScorerResult = scorer.score(gstin_id, ctx)
            except Exception:
                logger.exception("scorer %s failed for %s", scorer.name, gstin_id)
                continue
            sub = max(0.0, min(1.0, float(r.subscore)))
            w = self._weights.get(scorer.name, 0.0)
            contributions[scorer.name] = round(sub * w, 4)
            if r.reasons:
                fired.append(scorer.name)
                for reason in r.reasons:
                    all_reasons.append(reason.with_scorer(scorer.name, w))

        score = round(sum(contributions.values()), 4)
        band = band_for(score).value
        # Rank reasons by contribution (already computed) → take top N
        all_reasons = dedupe_reasons(all_reasons)
        all_reasons.sort(key=lambda r: (r.contribution or 0.0), reverse=True)
        top = [r.to_dict() for r in all_reasons[: self.config.top_reasons]]

        return ComposedRisk(
            gstin_id=gstin_id,
            score=score,
            band=band,
            contributions=contributions,
            reasons=top,
            scorers_fired=fired,
            scorers_run=run,
        )

    def compose_all(self, ctx: ScorerContext) -> List[ComposedRisk]:
        """Compose for every GSTIN in the context. Sorted by score desc."""
        ids = ctx.all_gstin_ids()
        out = [self.compose(gid, ctx) for gid in ids]
        out.sort(key=lambda r: r.score, reverse=True)
        return out
