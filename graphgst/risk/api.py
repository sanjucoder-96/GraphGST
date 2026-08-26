"""FastAPI router at /api/risk/* — composed risk per GSTIN + summary + refresh.

The composer is the single canonical risk source. `/summary` and `/gstin/{id}`
compose live (explainable, on-demand); `POST /refresh` (admin) materializes the
composed risk onto the graph so cheap indexed reads (case list, dashboard,
vendors) reflect it. Every response carries `materialization.stale` so stale
risk is never silently served as current.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException, Query

from security import require_admin as _require_admin

from .composer import ComposerConfig, RiskComposer
from .context import ScorerContext
from .scorers import (MLScorer, PropagationScorer, ReconcileScorer,
                      RingScorer, RuleScorer, TemporalScorer)

router = APIRouter()


def default_composer() -> RiskComposer:
    """Default composer — four scorers with positive/neutral marginal value.

    MLScorer and PropagationScorer were REMOVED from the default after the
    ablation study (benchmarks/ablation/ablate_risk.py, audit F1/F2) showed
    they have NEGATIVE marginal AUC on the ring-independent reconciliation
    label (removing ML *improves* recon-AUC by ~0.05; removing propagation by
    ~0.005). They remain importable and are still measured in the ablation;
    they are not shipped in the default because "AI that subtracts signal" is
    not defensible. Re-enable only if a future ablation on hardened data shows
    positive value.

    Weights are PRINCIPLED PRIORS, not eval-tuned: reconciliation is the
    strongest single evidence of a concrete compliance failure; ring
    membership is confirmed circular trading; rules capture filing/status
    red flags; temporal captures burst behaviour. The composer normalises
    them, so they are relative.
    """
    return RiskComposer(ComposerConfig(scorers=[
        ReconcileScorer(weight=0.35),
        RingScorer(weight=0.30),
        RuleScorer(weight=0.20),
        TemporalScorer(weight=0.15),
    ]))


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
    # Enrich the top rows with entity metadata (name/state/scenario/status) so
    # UI clients can render a real investigation queue directly from the modern,
    # explainable composer — no second round-trip to the legacy vendor endpoint.
    meta = {g.get("gstin_id"): g for g in ctx.gstins}
    top = []
    for r in ranked[:limit]:
        d = r.to_dict()
        g = meta.get(d["gstin_id"], {})
        d["name"] = g.get("name")
        d["state"] = g.get("state_code")
        d["scenario"] = g.get("scenario")
        d["status"] = g.get("status")
        top.append(d)
    from .materialize import read_materialization_status
    return {
        "count": len(ranked),
        "band_counts": _band_counts(ranked),
        "materialization": read_materialization_status(),
        "top": top,
    }


@router.post("/refresh")
def refresh_risk(
    persist_intelligence: bool = Query(
        True, description="also detect+persist rings and reconcile+persist events"),
    x_admin_token: str = Header(default=""),
) -> Dict[str, Any]:
    """Materialize composed risk onto the graph (admin). This is the canonical
    'make risk current' operation — it recomputes the composer once and writes
    risk_score/risk_band/reasons onto every GSTIN + updates the RiskMeta stamp,
    so subsequent reads are cheap and consistent."""
    _require_admin(x_admin_token=x_admin_token)
    from .materialize import materialize_risk, refresh_intelligence
    try:
        if persist_intelligence:
            return refresh_intelligence(persist=True)
        return materialize_risk()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"risk refresh failed: {e}")


@router.get("/materialization")
def materialization_status() -> Dict[str, Any]:
    """Report whether materialized risk is current vs the live graph fingerprint."""
    from .materialize import read_materialization_status
    try:
        return read_materialization_status()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"materialization status unavailable: {e}")


def _band_counts(ranked) -> Dict[str, int]:
    out: Dict[str, int] = {"LOW": 0, "MED": 0, "HIGH": 0, "CRITICAL": 0}
    for r in ranked:
        out[r.band] = out.get(r.band, 0) + 1
    return out


def _hydrate_context_or_503() -> ScorerContext:
    """Live-hydrate a ScorerContext via the single shared hydrator (one graph
    hydration; merges the edge list so TemporalScorer/PropagationScorer see the
    neighbour graph). Anything missing degrades gracefully."""
    try:
        from .hydrate import hydrate_context
        ctx, _rings, _events = hydrate_context()
        return ctx
    except Exception as e:
        raise HTTPException(503, f"risk context unavailable: {e}")
