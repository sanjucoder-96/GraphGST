"""FastAPI router mounted at /api/reconcile2 (Phase 2).

We keep the legacy /api/reconcile (V5) alive for the existing UI; the
new "2.0" route lives at /api/reconcile2 until Phase 6 rewires the
frontend. Endpoints:

    POST /api/reconcile2/run            run the pipeline (admin only if
                                        persist=true) and return events
    GET  /api/reconcile2/events         list persisted events, filterable
    GET  /api/reconcile2/summary        outcome-count summary from live graph
"""
from __future__ import annotations

import os
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from .engine import ReconcileConfig, run_reconcile

router = APIRouter()


def _require_admin(x_admin_token: str = Header(default="")) -> None:
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(503, "ADMIN_TOKEN not configured; persist=true disabled")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(401, "X-Admin-Token required")


class RunBody(BaseModel):
    persist: bool = False
    include_matched: bool = False
    amount_abs: float = 1.0
    amount_rel: float = 0.001
    date_days: int = 3
    invoice_id_jw: float = 0.90


@router.post("/run")
def run(
    body: RunBody,
    x_admin_token: str = Header(default=""),
) -> dict:
    if body.persist:
        _require_admin(x_admin_token=x_admin_token)
    cfg = ReconcileConfig(
        tolerances={
            "amount_abs": body.amount_abs,
            "amount_rel": body.amount_rel,
            "date_days": body.date_days,
            "invoice_id_jw": body.invoice_id_jw,
        },
        persist=body.persist,
        include_matched=body.include_matched,
    )
    events = run_reconcile(config=cfg)
    counts = Counter(e["outcome"] for e in events)
    severity_counts = Counter(e["severity"] for e in events)
    return {
        "count": len(events),
        "by_outcome": dict(counts),
        "by_severity": dict(severity_counts),
        "events": events[:500],   # cap payload size; full list persists to Neo4j
        "truncated": len(events) > 500,
    }


@router.get("/events")
def events(outcome: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)) -> dict:
    from .persist import list_events
    rows = list_events(outcome=outcome, limit=limit)
    return {"count": len(rows), "events": rows}


@router.get("/summary")
def summary() -> dict:
    """Fast summary via live re-run — cheaper than persisting on every read."""
    events = run_reconcile(config=ReconcileConfig(include_matched=False))
    counts = Counter(e["outcome"] for e in events)
    severity = Counter(e["severity"] for e in events)
    return {
        "total_events": len(events),
        "by_outcome": dict(counts),
        "by_severity": dict(severity),
    }
