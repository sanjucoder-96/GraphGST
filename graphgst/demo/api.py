"""FastAPI router at /api/demo/*.

Endpoints:

    POST /reset         — reset demo state (admin only if Neo4j reload=true)
    GET  /status        — current demo state
    GET  /story         — narrator script + hero ring + step expectations
    GET  /verify        — run the story verifier and return the result
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from .reset import read_status, reset as reset_demo
from .scenario import HERO_RING
from .story import story_json
from .verify import verify_story

router = APIRouter()


from security import require_admin as _require_admin


@router.get("/status")
def status_endpoint() -> Dict[str, Any]:
    s = read_status()
    if s is None:
        return {"initialized": False,
                 "hint": "POST /api/demo/reset or run `python -m demo.reset` first"}
    return {"initialized": True, **{k: v for k, v in s.items()
                                      if k not in ("planted_rings",)}}


@router.get("/story")
def story_endpoint() -> Dict[str, Any]:
    return story_json()


@router.get("/hero")
def hero_endpoint() -> Dict[str, Any]:
    """The hero ring's canonical properties (for the frontend to
    render deep-links, badges, and the demo strip)."""
    return {"hero_ring": HERO_RING}


@router.post("/reset", dependencies=[Depends(_require_admin)])
def reset_endpoint(load_neo4j: bool = Query(True)) -> Dict[str, Any]:
    """Reset demo state. `load_neo4j=false` regenerates the CSV
    artifacts only; the graph DB is left untouched."""
    status = reset_demo(load_neo4j=load_neo4j)
    return {
        "generated_at": status.get("generated_at"),
        "counts": status.get("counts"),
        "neo4j_loaded": status.get("neo4j_loaded"),
        "neo4j_error": status.get("neo4j_error"),
    }


@router.get("/verify")
def verify_endpoint() -> Dict[str, Any]:
    """Run the demo story verifier against the current in-memory state.
    Returns exit_code 0 in the response when every assertion holds."""
    res = verify_story()
    return {"exit_code": 0 if res["ok"] else 1, **res}
