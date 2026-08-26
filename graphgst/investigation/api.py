"""FastAPI router at /api/cases/* — the canonical investigation API.

Mounted from main.py:
    from investigation.api import router as cases_router
    app.include_router(cases_router, prefix="/api/cases", tags=["cases"])

GET /api/cases            → ranked CaseList from materialized risk (cheap read)
GET /api/cases/{gstin_id} → one coherent Case (entity+risk+rings+reconciliation
                            +exposure+related+timeline+subgraph) in a single call
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from schemas import Case, CaseList

from . import service

router = APIRouter()


@router.get("/", response_model=CaseList)
def list_cases(
    band: Optional[str] = Query(None, description="LOW|MED|HIGH|CRITICAL"),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=1000),
    q: Optional[str] = Query(None, description="free-text over gstin/name/reasons"),
) -> CaseList:
    try:
        return service.list_cases(band=band, min_score=min_score, limit=limit, q=q)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"case list unavailable: {e}")


@router.get("/{gstin_id}", response_model=Case)
def get_case(
    gstin_id: str,
    subgraph: bool = Query(True, description="include the 1-hop invoice subgraph"),
) -> Case:
    try:
        case = service.get_case(gstin_id, include_subgraph=subgraph)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"case unavailable: {e}")
    if case is None:
        raise HTTPException(404, f"no entity {gstin_id} in the current graph")
    return case
