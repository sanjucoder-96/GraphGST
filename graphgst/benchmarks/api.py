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


from security import require_admin as _require_admin


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
        _card("rings", "ring.average_precision",
                "Ring detection — Average Precision",
                "ratio",
                "Threshold-free ranking quality on HARD data (rings with dropped "
                "shared-vehicle/director tells, jittered timing, broken near-rings, "
                "and legitimate cyclic-trade negatives). AP over score-ranked "
                "detected cycles vs closed planted rings."),
        _card("rings", "ring.f1_at_thresh",
                "Ring detection F1 @0.45",
                "ratio",
                "F1 at the fixed 0.45 RingScorer prior (not eval-tuned). See the "
                "full precision/recall sweep in the report."),
        _card("reconcile", "reconcile.micro_f1",
                "Reconciliation micro-F1",
                "ratio",
                "Cascade-aware match of MatchEvent outcomes to planted anomalies."),
        _card("reconcile", "reconcile.micro_precision", "Reconciliation precision", "ratio", ""),
        _card("reconcile", "reconcile.micro_recall", "Reconciliation recall", "ratio", ""),
        _card("risk", "risk.recon_auc",
                "Composed risk — ROC-AUC (ring-independent)",
                "auc",
                "Honest task: rank GSTINs by composed risk against a "
                "RING-INDEPENDENT label (supplier of a planted reconciliation "
                "anomaly, ring members excluded). The circular ring-membership "
                "AUC is reported separately and NOT gated (audit F1)."),
        _card("risk", "risk.recon_p_at_50",
                "Risk Precision@50 (ring-independent)",
                "ratio",
                "Of the top-50 GSTINs by composed risk, fraction that are true "
                "reconciliation-anomaly suppliers."),
        _card("embed", "embed.structural_hit_at_10",
                "Lookalike structural Hit@10",
                "ratio",
                "For each ring member, does its top-10 lookalike list contain a "
                "same-ring member that is NOT a direct transaction partner "
                "(≥2 hops in the cycle)? Isolates genuine structural similarity "
                "from trivial adjacency (audit F3)."),
        _card("embed", "embed.cohesion_recall_at_10",
                "Lookalike cohesion recall@10",
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
        n_gstins=500, months=3, n_rings=12,
        ring_size_min=3, ring_size_max=6, seed=42,
        ring_difficulty=0.6, ring_broken_share=0.25, n_hard_negatives=5,
        out_dir=os.path.join(tempfile.gettempdir(), "graphgst_bench_all"),
    )
    report = run_all(cfg)
    with open(_LATEST, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    base = _read_json(_BASELINE) or {}
    return {"wrote": str(_LATEST),
             "diff": compare_reports(base, report),
             "headlines": report.get("headlines", {})}
