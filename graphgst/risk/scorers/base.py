"""Scorer protocol + result dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable

from ..context import ScorerContext
from ..reasons import Reason


@dataclass(slots=True)
class ScorerResult:
    """One scorer's answer for one GSTIN.

    subscore ∈ [0, 1] — scorer's own opinion of how risky the entity is.
    reasons  — the Reason list backing that opinion.
    The composer clamps subscore into [0, 1], multiplies by the scorer's
    global weight, and calls `Reason.with_scorer(name, weight)` to
    attach scorer + contribution fields to each reason.
    """
    subscore: float = 0.0
    reasons: List[Reason] = field(default_factory=list)


@runtime_checkable
class Scorer(Protocol):
    """Every scorer exposes a name, a global weight, and score()."""
    name: str
    weight: float

    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        ...
