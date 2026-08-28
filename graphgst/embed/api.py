"""FastAPI router at /api/embed/*.

- POST /train                    — retrain from the live graph, persist artifacts.
- GET  /lookalike/{gstin_id}     — top-K cosine-similar GSTINs.
- GET  /status                   — last trained-at, node count, config.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from .lookalike import LookalikeIndex
from .persist import DEFAULT_ARTIFACT_DIR, load_index, load_meta, save_index
from .train import EmbedConfig, EmbedModel, train

router = APIRouter()


from security import require_admin as _require_admin


class TrainBody(BaseModel):
    dim: int = 64
    walks_per_node: int = 10
    walk_len: int = 20
    window: int = 5
    neg_k: int = 5
    p: float = 1.0
    q: float = 1.0
    seed: int = 42


@router.post("/train", dependencies=[Depends(_require_admin)])
def train_endpoint(body: TrainBody) -> Dict[str, Any]:
    edges = _hydrate_edges_from_neo4j()
    cfg = EmbedConfig(
        dim=body.dim, walks_per_node=body.walks_per_node,
        walk_len=body.walk_len, window=body.window, neg_k=body.neg_k,
        p=body.p, q=body.q, seed=body.seed,
    )
    model = train(graph_source={"edges": edges}, config=cfg)
    fp = _graph_fingerprint()
    save = save_index(model, graph_fingerprint=fp)
    return {"trained": True, "n_indexed": len(model.ids), "stats": model.stats,
             "graph_fingerprint": fp, "artifacts": save}


@router.get("/lookalike/{gstin_id}")
def lookalike_endpoint(gstin_id: str, k: int = Query(5, ge=1, le=100)) -> Dict[str, Any]:
    index = load_index()
    if index is None:
        raise HTTPException(404, "no trained embeddings; POST /api/embed/train first")
    hits = index.similar_to(gstin_id, k=k)
    return {"gstin_id": gstin_id, "k": k, "neighbours": [
        {"gstin_id": g, "similarity": round(s, 4)} for g, s in hits
    ]}


@router.get("/status")
def status_endpoint() -> Dict[str, Any]:
    meta = load_meta()
    if meta is None:
        return {"trained": False, "stale": True}
    stored = meta.get("graph_fingerprint") or {}
    try:
        current = _graph_fingerprint()
    except Exception:
        current = {}
    # Stale if the graph changed since training (or the model predates fingerprint
    # tracking, i.e. stored is empty). Mirrors risk materialization staleness.
    stale = (not stored) or (bool(current) and stored != current)
    return {"trained": True, "n_indexed": len(meta.get("ids") or []),
             "config": meta.get("config"), "stats": meta.get("stats"),
             "saved_at": meta.get("saved_at"), "shape": meta.get("shape"),
             "graph_fingerprint": stored, "current_fingerprint": current,
             "stale": stale}


def _graph_fingerprint() -> dict:
    """Reuse the risk-materialization fingerprint as the graph version. It is a
    conservative superset of the embed-relevant inputs (invoice edge topology),
    so it may occasionally over-invalidate (a redundant retrain) but never marks
    a genuinely changed graph as fresh."""
    try:
        from risk.materialize import current_fingerprint
        return current_fingerprint()
    except Exception:
        return {}


def _hydrate_edges_from_neo4j() -> List[dict]:
    """Pull the invoice projection from Neo4j — same shape as the rings engine
    expects. ORDER BY makes edge arrival order (and thus the float weight
    accumulation in build_adjacency) deterministic → byte-reproducible artifact."""
    from db import run_query
    rows = run_query(
        "MATCH (a:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(b:GSTIN) "
        "RETURN a.gstin_id AS src, b.gstin_id AS dst, "
        "       coalesce(i.taxable_value, i.amount, 0) AS amount, i.invoice_id AS inv "
        "ORDER BY src, dst, inv"
    )
    return [{"src": r["src"], "dst": r["dst"],
              "amount": float(r["amount"] or 0)} for r in rows]
