"""FastAPI router for the Circular Trading Intelligence Engine.

Mount from main.py:

    from rings.api import router as rings_router
    app.include_router(rings_router, prefix="/api/rings", tags=["rings"])
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from security import require_admin as _require_admin

from .engine import EngineConfig, run_pipeline

router = APIRouter()


class DetectRequest(BaseModel):
    hop_max: int = Field(8, ge=2, le=16)
    window_days: int = Field(30, ge=1, le=365)
    weights: Optional[Dict[str, float]] = Field(None)
    use_gds: bool = True
    # Write flags default to FALSE. Both `persist` (writes Ring/Break nodes) and
    # `propagate` (writes ring_propagated_score) mutate Neo4j; an earlier version
    # defaulted both to True with NO auth on this route, so an unauthenticated
    # POST wrote to the graph. Detection-for-display now needs no token; writing
    # requires the admin token (see the guard in detect_rings, and docs/SECURITY.md).
    persist: bool = False
    propagate: bool = False
    horizon_days: Optional[int] = Field(None)


class DetectedRingOut(BaseModel):
    ring_id: str
    members: List[str]
    invoices: List[str]
    hops: int
    date_span_days: int
    total_gst: float
    score: float
    signals: Dict[str, float]
    contribution: Dict[str, float]
    share: Dict[str, float]
    break_edge: Optional[Dict[str, Any]]


@router.post("/detect", response_model=List[DetectedRingOut])
def detect_rings(
    req: DetectRequest,
    x_admin_token: str = Header(default=""),
) -> List[DetectedRingOut]:
    # Any Neo4j-mutating run must be authenticated; a pure read (the default,
    # and what the frontend sends) is open.
    if req.persist or req.propagate:
        _require_admin(x_admin_token=x_admin_token)
    cfg = EngineConfig(
        hop_max=req.hop_max,
        window_days=req.window_days,
        weights=req.weights or EngineConfig().weights,
        use_gds=req.use_gds,
        persist=req.persist,
        propagate=req.propagate,
        horizon_days=req.horizon_days,
    )
    try:
        rings = run_pipeline(cfg)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"detection failed: {e}")
    return [DetectedRingOut(**r.to_dict()) for r in rings]


@router.get("/")
def list_rings(
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    from .persist import list_rings as _list_rings
    try:
        rows = _list_rings()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"list failed: {e}")
    return [r for r in rows if (r.get("score") or 0) >= min_score][:limit]


@router.get("/{ring_id}")
def get_ring(ring_id: str) -> Dict[str, Any]:
    from .persist import get_ring as _get_ring
    try:
        r = _get_ring(ring_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"get failed: {e}")
    if r is None:
        raise HTTPException(status_code=404, detail=f"ring not found: {ring_id}")
    return r
