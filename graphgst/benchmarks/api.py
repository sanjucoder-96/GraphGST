"""FastAPI router at /api/benchmarks/*.

- GET /latest        — the latest recorded bench report.
- GET /baseline      — the checked-in baseline.
- GET /diff          — comparison between them (same shape as CLI).
- GET /model-card    — investigator-UI-friendly card summarizing headlines.
- POST /run          — (admin) run the bench, write latest, return diff.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from .compare import compare_reports, format_diff_table

router = APIRouter()

_BENCH_DIR = Path(__file__).resolve().parent
_LATEST = _BENCH_DIR / "latest.json"
_BASELINE = _BENCH_DIR / "baseline.json"


def _require_admin(x_admin_token: str = Header(default="")) -> None:
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(503, "ADMIN_TOKEN not configured; run disabled")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(401, "X-Admin-Token required")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/latest")
def latest() -> Dict[str, Any]:
    r = _read_json(_LATEST)
    if r is None:
        raise HTTPException(404, "no latest.json; run benchmarks first")
    return r


@router.get("/baseline")
def baseline() -> Dict[str, Any]:
    r = _read_json(_BASELINE)
    if r is None:
        raise HTTPException(404, "no baseline.json; run --write-baseline first")
    return r


@router.get("/diff")
def diff() -> Dict[str, Any]:
    cur = _read_json(_LATEST)
    if cur is None:
        raise HTTPException(404, "no latest.json; run benchmarks first")
    base = _read_json(_BASELINE)
    return compare_reports(base, cur)


@router.get("/model-card")
def model_card() -> Dict[str, Any]:
    """Compact "what does the system claim, with what number?" summary
    for the Investigator Console's Model Card page.

    Shape:
      {
        generated_at, git_commit, dataset_config,
        cards: [{
          module, headline, value, unit, baseline, delta, status, notes
        }, …]
      }
    """
    cur = _read_json(_LATEST)
    if cur is None:
        raise HTTPException(404, "no latest.json; run benchmarks first")
    base = _read_json(_BASELINE) or {}
    diff = compare_reports(base, cur)
    diff_by_metric = {r["metric"]: r for r in diff["rows"]}

    def _card(module: str, metric: str, headline: str, unit: str, notes: str) -> Dict[str, Any]:
        row = diff_by_metric.get(metric, {})
        return {
            "module": module,
            "metric": metric,
            "headline": headline,
            "value": row.get("current"),
            "baseline": row.get("baseline"),
            "delta": row.get("delta"),
            "status": row.get("status", "INFO"),
            "unit": unit,
            "notes": notes,
        }

    cards = [
        _card("rings", "ring.recall",
                "Ring member-multiset recall",
                "ratio",
                "Fraction of planted rings recovered by SCC → Johnson pipeline."),
        _card("reconcile", "reconcile.micro_f1",
                "Reconciliation micro-F1",
                "ratio",
                "Cascade-aware match of MatchEvent outcomes to planted anomalies."),
        _card("reconcile", "reconcile.micro_precision", "Precision", "ratio", ""),
        _card("reconcile", "reconcile.micro_recall", "Recall", "ratio", ""),
        _card("risk", "risk.roc_auc",
                "Composed risk ROC-AUC",
                "auc",
                "Binary rank task: is this GSTIN a planted ring member?"),
        _card("risk", "risk.precision_at_50",
                "Risk Precision@50",
                "ratio",
                "Of the top-50 ranked GSTINs, fraction that are planted ring members."),
        _card("risk", "risk.precision_at_100",
                "Risk Precision@100", "ratio", ""),
        _card("embed", "embed.hit_at_10",
                "Lookalike Hit@10",
                "ratio",
                "For each planted ring member, does its top-10 lookalike list "
                "contain ≥ 1 OTHER member of the same ring?"),
        _card("embed", "embed.cohesion_recall_at_10",
                "Lookalike Cohesion Recall@10",
                "ratio",
                "Mean fraction of a ring's other members appearing in each "
                "member's top-10 lookalikes."),
    ]

    return {
        "generated_at": cur.get("generated_at"),
        "git_commit": cur.get("git_commit"),
        "dataset_config": cur.get("config"),
        "tolerance_abs": diff.get("tolerance_abs"),
        "overall_pass": diff.get("ok"),
        "cards": cards,
    }


class _RunBody(dict):
    n_gstins: int = 500
    seed: int = 42


@router.post("/run", dependencies=[Depends(_require_admin)])
def run_now() -> Dict[str, Any]:
    """Run the full benchmark suite. Writes latest.json. Returns the diff.
    Admin-only because it takes ~10s of CPU."""
    from datagen.config import GenerationConfig
    from .run_all import run_all
    import tempfile

    cfg = GenerationConfig(
        n_gstins=500, months=3, n_rings=8,
        ring_size_min=3, ring_size_max=6, seed=42,
        out_dir=os.path.join(tempfile.gettempdir(), "graphgst_bench_all"),
    )
    report = run_all(cfg)
    with open(_LATEST, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    base = _read_json(_BASELINE) or {}
    return {"wrote": str(_LATEST),
             "diff": compare_reports(base, report),
             "headlines": report.get("headlines", {})}
