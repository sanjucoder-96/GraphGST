"""FastAPI router mounted at /api/datagen.

Endpoints:

    POST /api/datagen/generate  — run the generator, return counts + path
    POST /api/datagen/load      — load an existing generated dir into Neo4j
    GET  /api/datagen/truth     — read truth.json from a generated dir
    GET  /api/datagen/status    — count generated dirs on the server

Loading and generating are ADMIN-only — they can mutate the graph and
consume disk. Both check X-Admin-Token. Reading truth.json is public.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from .cli import build_config as _cli_build_config
from .config import GenerationConfig
from .anomalies import inject_anomalies
from .emitters import emit
from .network import sample_edges, sample_gstins
from .rings import plant_rings
from .transactions import derive_returns, sample_transactions

# Use the SHARED, constant-time admin guard (hmac.compare_digest) rather than a
# local `!=` comparison. The previous local copy compared tokens with `!=`,
# which is timing-variable and diverged from every other router's guard.
from security import require_admin as _require_admin


router = APIRouter()


class GenerateBody(BaseModel):
    # Whitelist a subset of the most useful knobs for the API. The full
    # config remains available via CLI.
    n_gstins: int = 1_000
    months: int = 6
    normal_share: float = 0.90
    recon_issue_share: float = 0.06
    circular_share: float = 0.03
    duplicate_share: float = 0.01
    n_rings: int = 15
    ring_size_min: int = 3
    ring_size_max: int = 8
    seed: int = 42
    out_dir: str = "./datagen_output"


@router.post("/generate", dependencies=[Depends(_require_admin)])
def generate(body: GenerateBody) -> dict:
    cfg = GenerationConfig(**body.model_dump())
    cfg.validate()
    gstins = sample_gstins(cfg)
    edges = sample_edges(cfg, gstins)
    bundles = sample_transactions(cfg, gstins, edges)
    ring_bundles, ring_g1, ring_g3, ring_tp, planted_rings = plant_rings(cfg, gstins)
    ring_ids = {b.invoice.invoice_id for b in ring_bundles}
    bundles = bundles + ring_bundles
    g1, g3, g2b, tp = derive_returns(cfg, gstins, bundles)
    g1.extend(ring_g1); g3.extend(ring_g3); tp.extend(ring_tp)
    bundles, g1, g3, tp, planted_anoms = inject_anomalies(
        cfg, bundles, g1, g3, tp,
        ring_invoice_ids=ring_ids,
        gstin_meta_records=gstins,
    )
    counts = emit(cfg, gstins, bundles, g1, g3, g2b, tp, planted_anoms, planted_rings)
    return {"ok": True, "out_dir": os.path.abspath(cfg.out_dir), "counts": counts,
            "planted_rings": len(planted_rings), "planted_anomalies": len(planted_anoms)}


@router.post("/load", dependencies=[Depends(_require_admin)])
def load(dir: str = Query(..., description="Path to a datagen output directory")) -> dict:
    from security import resolve_within
    from .loader import load_directory
    safe = resolve_within(dir)                 # blocks path traversal
    if not safe.is_dir():
        raise HTTPException(404, "Directory not found")
    stats = load_directory(str(safe))
    return {"ok": True, "loaded": stats}


@router.get("/truth")
def read_truth(dir: str = Query(...)) -> dict:
    # Path-traversal safe: `dir` must resolve under an allowed data root.
    from security import resolve_within
    safe = resolve_within(dir)
    tpath = safe / "truth.json"
    if not tpath.exists():
        raise HTTPException(404, "truth.json not found")
    with open(tpath, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/status")
def status_ep() -> dict:
    """List generated directories under CWD that contain a truth.json."""
    cwd = os.getcwd()
    found = []
    for entry in os.scandir(cwd):
        if entry.is_dir():
            tp = os.path.join(entry.path, "truth.json")
            if os.path.exists(tp):
                found.append({"path": entry.path, "size_bytes": os.path.getsize(tp)})
    return {"cwd": cwd, "generated_datasets": found}
