"""Benchmark: ring-detection recall against datagen truth.

Generates a synthetic dataset, feeds the invoices into the ring engine
via the in-memory graph_source path (no Neo4j needed), and compares
detected rings against planted_rings in truth.json.

Reports:
  * planted_rings recovered (recall) — matched by ring_id AND by
    member-multiset (in case canonicalisation differs).
  * detected rings that are NOT planted (potential FPs).
  * total wall-clock.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

# make the project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datagen.anomalies import inject_anomalies                    # noqa: E402
from datagen.config import GenerationConfig                        # noqa: E402
from datagen.emitters import emit                                  # noqa: E402
from datagen.network import sample_edges, sample_gstins            # noqa: E402
from datagen.rings import plant_rings                              # noqa: E402
from datagen.transactions import derive_returns, sample_transactions  # noqa: E402
from rings.engine import EngineConfig, run_pipeline                # noqa: E402


def _generate(cfg: GenerationConfig) -> str:
    """Run the full datagen pipeline and return the output dir."""
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
    emit(cfg, gstins, bundles, g1, g3, g2b, tp, planted_anoms, planted_rings)
    return cfg.out_dir


def _load_edges_from_csv(dir: str) -> tuple[list[dict], dict[str, dict]]:
    """Build the engine's graph_source shape from datagen CSVs."""
    gstins_path = os.path.join(dir, "gstins.csv")
    invoices_path = os.path.join(dir, "invoices.csv")
    ewb_path = os.path.join(dir, "ewb.csv")

    with open(gstins_path, encoding="utf-8") as f:
        gstins = list(csv.DictReader(f))
    with open(invoices_path, encoding="utf-8") as f:
        invoices = list(csv.DictReader(f))
    with open(ewb_path, encoding="utf-8") as f:
        ewbs = list(csv.DictReader(f))

    veh_by_invoice = {e["invoice_id"]: e.get("vehicle_number") for e in ewbs}
    pin_by_gstin = {g["gstin_id"]: (g.get("pincode") or "")[:3] for g in gstins}
    dirs_by_gstin = {
        g["gstin_id"]: [d for d in (g.get("directors") or "").split(";") if d]
        for g in gstins
    }

    edges: list[dict] = []
    for inv in invoices:
        dt = inv.get("date")
        try:
            edge_date = date.fromisoformat(dt) if dt else None
        except ValueError:
            edge_date = None
        edges.append({
            "src": inv["supplier_gstin"],
            "dst": inv["buyer_gstin"],
            "invoice_id": inv["invoice_id"],
            "date": edge_date,
            "amount": float(inv.get("taxable_value", 0) or 0),
            "gst_amount": float(inv.get("total_gst", 0) or 0),
            "vehicle_id": veh_by_invoice.get(inv["invoice_id"]),
            "hsn": inv.get("hsn"),
            "pin_prefix": pin_by_gstin.get(inv["buyer_gstin"]),
        })
    member_meta = {gid: {"directors": dl} for gid, dl in dirs_by_gstin.items()}
    return edges, member_meta


def _canonical_members(seq):
    """Rotate to start at lex-smallest, return as tuple."""
    if not seq:
        return tuple()
    i = min(range(len(seq)), key=lambda k: seq[k])
    return tuple(seq[i:]) + tuple(seq[:i])


def bench(cfg: GenerationConfig) -> dict:
    t0 = time.perf_counter()
    out_dir = _generate(cfg)
    t_gen = time.perf_counter() - t0

    # Load truth
    with open(os.path.join(out_dir, "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)
    planted = truth.get("planted_rings", [])
    planted_by_members = {
        _canonical_members(r["members"]): r for r in planted
    }

    # Build in-memory graph_source
    t1 = time.perf_counter()
    edges, member_meta = _load_edges_from_csv(out_dir)
    t_load = time.perf_counter() - t1

    # Run detection
    t2 = time.perf_counter()
    engine_cfg = EngineConfig(
        hop_max=cfg.ring_size_max + 2,
        window_days=90,
        persist=False,
        propagate=False,   # bench runs without Neo4j — skip PageRank propagation
    )
    detected = run_pipeline(config=engine_cfg,
                             graph_source={"edges": edges, "member_meta": member_meta})
    t_detect = time.perf_counter() - t2

    # Match by canonical member-multiset (order-agnostic set of members).
    detected_by_members = {}
    for d in detected:
        key = _canonical_members(tuple(d.members))
        detected_by_members[key] = d

    recovered = []
    missed = []
    for pkey, prow in planted_by_members.items():
        if pkey in detected_by_members:
            recovered.append((prow, detected_by_members[pkey]))
        else:
            # Also try a "set of members" match (a subring of the planted).
            planted_set = frozenset(pkey)
            hit = next(
                (d for k, d in detected_by_members.items()
                 if frozenset(k).issubset(planted_set)
                 and len(k) >= min(3, len(pkey))),
                None,
            )
            if hit is not None:
                recovered.append((prow, hit))
            else:
                missed.append(prow)

    # Detected rings not in truth — count as potential FPs (may be legitimate
    # tiny cycles emerging from the normal population).
    fp = [d for k, d in detected_by_members.items() if k not in planted_by_members]

    return {
        "config": {
            "n_gstins": cfg.n_gstins, "months": cfg.months,
            "n_rings_planted": cfg.n_rings, "seed": cfg.seed,
        },
        "counts": {
            "edges": len(edges), "planted_rings": len(planted),
            "detected_rings": len(detected),
            "recovered_rings": len(recovered),
            "missed_rings": len(missed),
            "non_planted_detected": len(fp),
        },
        "recall": (len(recovered) / len(planted)) if planted else None,
        "timing_sec": {
            "generate": round(t_gen, 3),
            "load_csv": round(t_load, 3),
            "detect": round(t_detect, 3),
        },
        "sample_recovered": [
            {
                "ring_id_truth": p["ring_id"],
                "ring_id_detected": d.ring_id,
                "members": list(d.members),
                "score": round(d.score, 3),
                "signals": {k: round(v, 3) for k, v in d.signals.items()},
                "size": len(d.members),
            }
            for p, d in recovered[:3]
        ],
        "sample_missed": [
            {"ring_id": p["ring_id"], "size": p["size"], "members": p["members"]}
            for p in missed[:3]
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-gstins", type=int, default=800)
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--n-rings", type=int, default=8)
    p.add_argument("--ring-size-min", type=int, default=3)
    p.add_argument("--ring-size-max", type=int, default=6)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", type=str, default="./datagen_output_bench")
    args = p.parse_args()

    cfg = GenerationConfig(
        n_gstins=args.n_gstins,
        months=args.months,
        n_rings=args.n_rings,
        ring_size_min=args.ring_size_min,
        ring_size_max=args.ring_size_max,
        seed=args.seed,
        out_dir=args.out_dir,
    )
    cfg.validate()

    report = bench(cfg)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
