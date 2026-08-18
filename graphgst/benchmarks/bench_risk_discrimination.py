"""Benchmark: does the composed risk score discriminate ring members from noise?

Generates a synthetic dataset, runs reconcile + rings, feeds both into the
composer, and reports ROC-AUC + Precision@K on the binary task
"is this GSTIN a member of a planted ring".

No Neo4j needed — everything in-memory.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datagen.anomalies import inject_anomalies                    # noqa: E402
from datagen.catalog import HSN_CATALOG                            # noqa: E402
from datagen.config import GenerationConfig                        # noqa: E402
from datagen.emitters import emit                                  # noqa: E402
from datagen.network import sample_edges, sample_gstins            # noqa: E402
from datagen.rings import plant_rings                              # noqa: E402
from datagen.transactions import derive_returns, sample_transactions  # noqa: E402
from reconcile.engine import ReconcileConfig, run_reconcile        # noqa: E402
from rings.engine import EngineConfig, run_pipeline                # noqa: E402
from risk import ComposerConfig, RiskComposer, build_context_from_graph_source  # noqa: E402
from risk.scorers import (MLScorer, PropagationScorer, ReconcileScorer,  # noqa: E402
                          RingScorer, RuleScorer, TemporalScorer)


def _generate(cfg: GenerationConfig) -> None:
    gstins = sample_gstins(cfg)
    edges = sample_edges(cfg, gstins)
    bundles = sample_transactions(cfg, gstins, edges)
    ring_bundles, ring_g1, ring_g3, ring_tp, planted_rings = plant_rings(cfg, gstins)
    ring_ids = {b.invoice.invoice_id for b in ring_bundles}
    bundles = bundles + ring_bundles
    g1, g3, g2b, tp = derive_returns(cfg, gstins, bundles)
    g1.extend(ring_g1); g3.extend(ring_g3); tp.extend(ring_tp)
    bundles, g1, g3, tp, planted = inject_anomalies(
        cfg, bundles, g1, g3, tp,
        ring_invoice_ids=ring_ids, gstin_meta_records=gstins)
    emit(cfg, gstins, bundles, g1, g3, g2b, tp, planted, planted_rings)


def _read_csv(dir: str, name: str) -> list[dict]:
    with open(os.path.join(dir, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_graph_source(dir: str) -> dict:
    gstin_rows = _read_csv(dir, "gstins.csv")
    inv_rows = _read_csv(dir, "invoices.csv")
    ewb_rows = _read_csv(dir, "ewb.csv")
    pr_rows = _read_csv(dir, "pr.csv")
    g1_rows = _read_csv(dir, "gstr1.csv")
    g3_rows = _read_csv(dir, "gstr3b.csv")
    tp_rows = _read_csv(dir, "taxpayments.csv")

    for i in inv_rows:
        for k in ("taxable_value", "cgst", "sgst", "igst", "total_gst"):
            i[k] = float(i.get(k) or 0) if i.get(k) not in (None, "") else 0.0
        i["ewb_required"] = str(i.get("ewb_required", "")).lower() in ("true", "1")
    for p in pr_rows:
        for k in ("booked_amount", "booked_tax"):
            p[k] = float(p.get(k) or 0) if p.get(k) not in (None, "") else 0.0

    edges = []
    veh_by_inv = {e["invoice_id"]: e.get("vehicle_number") for e in ewb_rows}
    pin_by_gstin = {g["gstin_id"]: (g.get("pincode") or "")[:3] for g in gstin_rows}
    for inv in inv_rows:
        try:
            d = date.fromisoformat(inv["date"])
        except (KeyError, ValueError):
            d = None
        edges.append({
            "src": inv["supplier_gstin"], "dst": inv["buyer_gstin"],
            "invoice_id": inv["invoice_id"], "date": d,
            "amount": inv["taxable_value"], "gst_amount": inv["total_gst"],
            "vehicle_id": veh_by_inv.get(inv["invoice_id"]),
            "hsn": inv.get("hsn"), "pin_prefix": pin_by_gstin.get(inv["buyer_gstin"]),
        })

    return {
        "gstins": gstin_rows,
        "invoices": inv_rows,
        "pr": pr_rows,
        "edges": edges,
        "gstr1_keys": {(g["gstin"], g["period"]) for g in g1_rows},
        "gstr3b_keys": {(g["gstin"], g["period"]) for g in g3_rows},
        "settled_keys": {t["gstr3b_return_id"] for t in tp_rows
                          if (t.get("status") or "").upper() == "CLEARED"},
        "ewb_by_invoice": {e["invoice_id"] for e in ewb_rows if e.get("invoice_id")},
    }


def _member_meta(gstin_rows: list[dict]) -> dict[str, dict]:
    out = {}
    for g in gstin_rows:
        ds = g.get("directors") or ""
        out[g["gstin_id"]] = {"directors": [x for x in ds.split(";") if x]}
    return out


def _roc_auc(scores_labels: list[tuple[float, int]]) -> float:
    """Mann-Whitney U formulation for binary AUC. O(N log N)."""
    if not scores_labels:
        return 0.0
    pos = [s for s, y in scores_labels if y == 1]
    neg = [s for s, y in scores_labels if y == 0]
    if not pos or not neg:
        return float("nan")
    total = 0
    ties = 0
    for p in pos:
        for n in neg:
            if p > n:
                total += 1
            elif p == n:
                ties += 1
    return (total + 0.5 * ties) / (len(pos) * len(neg))


def _precision_at_k(scores_labels: list[tuple[float, int]], k: int) -> float:
    top_k = sorted(scores_labels, key=lambda x: -x[0])[:k]
    if not top_k:
        return 0.0
    return sum(y for _, y in top_k) / len(top_k)


def bench_prepared(cfg: GenerationConfig, out_dir: str) -> dict:
    """Run the risk-discrimination benchmark on a pre-generated dataset dir."""
    t_gen = 0.0

    with open(os.path.join(out_dir, "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)

    ring_members: set[str] = set()
    for pr in truth.get("planted_rings", []):
        ring_members.update(pr.get("members") or [])

    t1 = time.perf_counter()
    gs = _load_graph_source(out_dir)
    t_load = time.perf_counter() - t1

    # 1) reconcile
    t2 = time.perf_counter()
    events = run_reconcile(
        graph_source=gs,
        config=ReconcileConfig(include_matched=False, hsn_catalog=HSN_CATALOG),
    )
    t_reconcile = time.perf_counter() - t2

    # 2) rings
    t3 = time.perf_counter()
    rings = run_pipeline(
        graph_source={"edges": gs["edges"], "member_meta": _member_meta(gs["gstins"])},
        config=EngineConfig(hop_max=cfg.ring_size_max + 2, window_days=90,
                              persist=False, propagate=False),
    )
    t_rings = time.perf_counter() - t3

    # 3) risk composition
    ctx = build_context_from_graph_source(
        gs, match_events=events,
        detected_rings=[r.__dict__ for r in rings],
        member_meta=_member_meta(gs["gstins"]),
    )
    composer = RiskComposer(ComposerConfig(scorers=[
        RingScorer(weight=0.35),
        ReconcileScorer(weight=0.20),
        RuleScorer(weight=0.15),
        PropagationScorer(weight=0.15),
        TemporalScorer(weight=0.10),
        MLScorer(weight=0.10),
    ]))
    t4 = time.perf_counter()
    ranked = composer.compose_all(ctx)
    t_compose = time.perf_counter() - t4

    # 4) score against truth
    scores_labels = [(r.score, int(r.gstin_id in ring_members)) for r in ranked]
    auc = _roc_auc(scores_labels)

    band_counts = {"LOW": 0, "MED": 0, "HIGH": 0, "CRITICAL": 0}
    for r in ranked:
        band_counts[r.band] = band_counts.get(r.band, 0) + 1

    n_planted = len(ring_members & {r.gstin_id for r in ranked})

    return {
        "config": cfg.to_dict(),
        "timing_sec": {"generate": round(t_gen, 3),
                        "load_csv": round(t_load, 3),
                        "reconcile": round(t_reconcile, 3),
                        "rings": round(t_rings, 3),
                        "compose": round(t_compose, 3)},
        "counts": {"gstins": len(ranked), "planted_ring_members": n_planted,
                    "detected_rings": len(rings),
                    "match_events": len(events)},
        "roc_auc": round(auc, 3),
        "precision_at_k": {
            "10": round(_precision_at_k(scores_labels, 10), 3),
            "25": round(_precision_at_k(scores_labels, 25), 3),
            "50": round(_precision_at_k(scores_labels, 50), 3),
            "100": round(_precision_at_k(scores_labels, 100), 3),
        },
        "band_histogram": band_counts,
        "score_summary": {
            "median": round(statistics.median(r.score for r in ranked), 3),
            "p90": round(sorted(r.score for r in ranked)[int(0.9 * len(ranked))], 3)
                    if ranked else 0.0,
            "max": round(max((r.score for r in ranked), default=0.0), 3),
        },
        "sample_top": [
            {"gstin_id": r.gstin_id, "score": r.score, "band": r.band,
                "planted": r.gstin_id in ring_members,
                "top_scorer": max(r.contributions.items(), key=lambda kv: kv[1])[0]
                                if r.contributions else None,
                "n_reasons": len(r.reasons)}
            for r in ranked[:8]
        ],
    }


def bench(cfg: GenerationConfig) -> dict:
    _generate(cfg)
    return bench_prepared(cfg, cfg.out_dir)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-gstins", type=int, default=500)
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--n-rings", type=int, default=6)
    p.add_argument("--ring-size-min", type=int, default=3)
    p.add_argument("--ring-size-max", type=int, default=6)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", type=str, default="./_bench_risk")
    args = p.parse_args()
    cfg = GenerationConfig(
        n_gstins=args.n_gstins, months=args.months, n_rings=args.n_rings,
        ring_size_min=args.ring_size_min, ring_size_max=args.ring_size_max,
        seed=args.seed, out_dir=args.out_dir,
    )
    cfg.validate()
    print(json.dumps(bench(cfg), indent=2))


if __name__ == "__main__":
    main()
