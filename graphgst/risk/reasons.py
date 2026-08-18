"""Reason — the shared evidence contract.

Both `rings/scoring.py` (as `contribution` dicts) and `reconcile/outcomes.py`
(as a dataclass) already emit reason-shaped payloads. This module is the
canonical definition. New scorers use `Reason` directly; existing modules
can dict-import-and-adapt via `from_dict` when they cross this boundary.

Design notes
------------
* `weight` is the scorer-local salience of THIS reason (0..1). The
  composer multiplies by the scorer's global weight to get the actual
  contribution to the final score.
* `evidence` is a small dict pointing at the cited graph node(s) so
  the UI can highlight a subgraph on click. Keys we normalize on:
      node_type   – "GSTIN" | "Invoice" | "Ring" | "MatchEvent" | ...
      node_id     – string OR list[string]
      path        – optional "GSTIN→ISSUED_INVOICE→Invoice" hint for the UI
* `scorer` is set by the composer after collection so the UI can group
  reasons by their originating scorer. Scorer code should NOT set it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


class ReasonBand(str, Enum):
    """Coarse severity band. UI uses this only for the amber "watch it now"
    dot on the risk header — the numeric score is authoritative."""
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


def band_for(score: float) -> ReasonBand:
    """Score → band. Thresholds match the UI's severity pills:
    LOW <0.30 · MED <0.55 · HIGH <0.80 · CRITICAL ≥0.80"""
    if score >= 0.80:
        return ReasonBand.CRITICAL
    if score >= 0.55:
        return ReasonBand.HIGH
    if score >= 0.30:
        return ReasonBand.MED
    return ReasonBand.LOW


@dataclass(slots=True)
class Reason:
    name: str
    weight: float                              # scorer-local salience [0, 1]
    detail: str                                # UI-renderable one-liner
    evidence: Dict[str, Any] = field(default_factory=dict)
    scorer: Optional[str] = None               # composer sets this
    contribution: Optional[float] = None       # composer sets this too

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Drop scorer/contribution when unset — keeps the wire clean.
        if d.get("scorer") is None:
            d.pop("scorer", None)
        if d.get("contribution") is None:
            d.pop("contribution", None)
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Reason":
        return Reason(
            name=str(d.get("name", "")),
            weight=float(d.get("weight", 0.0)),
            detail=str(d.get("detail", "")),
            evidence=dict(d.get("evidence") or {}),
            scorer=d.get("scorer"),
            contribution=(
                float(d["contribution"]) if d.get("contribution") is not None else None
            ),
        )

    def with_scorer(self, scorer_name: str, scorer_weight: float) -> "Reason":
        """Return a copy tagged with the scorer name and its contribution
        to the composed score = weight × scorer_weight."""
        return replace(
            self,
            scorer=scorer_name,
            contribution=round(float(self.weight) * float(scorer_weight), 4),
        )


def dedupe_reasons(reasons: Iterable[Reason]) -> List[Reason]:
    """Deduplicate by (scorer, name, evidence.node_id) — keep the reason
    with the largest weight. Investigators only want to see each specific
    tell once."""
    best: Dict[tuple, Reason] = {}
    for r in reasons:
        node_id = r.evidence.get("node_id")
        if isinstance(node_id, list):
            node_id = tuple(node_id)
        key = (r.scorer, r.name, node_id)
        cur = best.get(key)
        if cur is None or r.weight > cur.weight:
            best[key] = r
    return list(best.values())
