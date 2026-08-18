"""FastAPI router at /api/risk/* — composed risk per GSTIN + summary."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .composer import ComposerConfig, RiskComposer
from .context import ScorerContext, build_context_from_graph_source
from .scorers import (MLScorer, PropagationScorer, ReconcileScorer,
                      RingScorer, RuleScorer, TemporalScorer)

router = APIRouter()


def default_composer() -> RiskComposer:
    """Six-scorer default. Weights sum ≈ 1.10 → normalized by the composer."""
    return RiskComposer(ComposerConfig(scorers=[
        RingScorer(weight=0.35),
        ReconcileScorer(weight=0.20),
        RuleScorer(weight=0.15),
        PropagationScorer(weight=0.15),
        TemporalScorer(weight=0.10),
        MLScorer(weight=0.10),
    ]))


class RunBody(BaseModel):
    limit: int = 100
    include_reasons: bool = True


@router.get("/gstin/{gstin_id}")
def gstin_risk(gstin_id: str) -> Dict[str, Any]:
    ctx = _hydrate_context_or_503()
    composer = default_composer()
    if gstin_id not in ctx.all_gstin_ids():
        raise HTTPException(404, f"GSTIN {gstin_id} not present in current graph")
    return composer.compose(gstin_id, ctx).to_dict()


@router.get("/summary")
def summary(limit: int = Query(50, ge=1, le=1000)) -> Dict[str, Any]:
    ctx = _hydrate_context_or_503()
    composer = default_composer()
    ranked = composer.compose_all(ctx)
    return {
        "count": len(ranked),
        "band_counts": _band_counts(ranked),
        "top": [r.to_dict() for r in ranked[:limit]],
    }


def _band_counts(ranked) -> Dict[str, int]:
    out: Dict[str, int] = {"LOW": 0, "MED": 0, "HIGH": 0, "CRITICAL": 0}
    for r in ranked:
        out[r.band] = out.get(r.band, 0) + 1
    return out


def _hydrate_context_or_503() -> ScorerContext:
    """Live-hydrate a ScorerContext from Neo4j + the reconcile & rings engines.
    Anything missing is tolerated (empty list); scorers degrade gracefully."""
    try:
        from reconcile.engine import ReconcileConfig, run_reconcile
        from rings.engine import EngineConfig, run_pipeline
        # Reconcile hydrates from Neo4j internally; use its as-is graph_source view.
        events = run_reconcile(config=ReconcileConfig(include_matched=False))
        # For rings we need the edge list. rings.engine also does its own hydrate.
        rings = run_pipeline(config=EngineConfig(persist=False, propagate=False))
        # Rebuild a ScorerContext from Neo4j directly to have all the fields.
        from reconcile.engine import _hydrate_from_neo4j
        gs = _hydrate_from_neo4j()
        return build_context_from_graph_source(
            gs,
            match_events=[e for e in events if e.get("outcome") != "MATCHED"],
            detected_rings=[
                r.__dict__ if hasattr(r, "__dict__") else r  # DetectedRing dataclass
                for r in rings
            ],
        )
    except Exception as e:
        raise HTTPException(503, f"risk context unavailable: {e}")
