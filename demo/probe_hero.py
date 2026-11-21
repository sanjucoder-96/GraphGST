"""Regenerate `demo/scenario.py`'s HERO_RING constants from live datagen.

Run this after ANY change to datagen (network, transactions, rings,
anomalies) to check whether the hero ring's shape drifted. If any of
the printed values differ from what's in `scenario.py`, update the
constants there and re-run `python -m demo.verify` to lock in the
new baseline.

Usage
-----
    python -m demo.probe_hero
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _reexec_with_hashseed_if_needed() -> None:
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    import subprocess
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    ret = subprocess.call([sys.executable, "-m", "demo.probe_hero", *sys.argv[1:]], env=env)
    sys.exit(ret)


def main() -> int:
    _reexec_with_hashseed_if_needed()

    from datagen.anomalies import inject_anomalies
    from datagen.config import GenerationConfig
    from datagen.emitters import emit
    from datagen.network import sample_edges, sample_gstins
    from datagen.rings import plant_rings
    from datagen.transactions import derive_returns, sample_transactions
    from embed import EmbedConfig, LookalikeIndex, train as train_embed
    from rings.engine import EngineConfig, run_pipeline

    from .scenario import DEMO_MONTHS, DEMO_N_GSTINS, DEMO_N_RINGS, DEMO_SEED, HERO_RING

    tmp = os.path.join(os.path.dirname(__file__), "_probe_tmp")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    cfg = GenerationConfig(n_gstins=DEMO_N_GSTINS, months=DEMO_MONTHS,
                             n_rings=DEMO_N_RINGS, ring_size_min=3,
                             ring_size_max=6, seed=DEMO_SEED, out_dir=tmp)
    cfg.validate()
    gstins = sample_gstins(cfg)
    edges_pop = sample_edges(cfg, gstins)
    bundles = sample_transactions(cfg, gstins, edges_pop)
    ring_bundles, r_g1, r_g3, r_tp, planted_rings = plant_rings(cfg, gstins)
    ring_ids = {b.invoice.invoice_id for b in ring_bundles}
    bundles = bundles + ring_bundles
    g1, g3, g2b, tp = derive_returns(cfg, gstins, bundles)
    g1.extend(r_g1); g3.extend(r_g3); tp.extend(r_tp)
    bundles, g1, g3, tp, planted_a = inject_anomalies(
        cfg, bundles, g1, g3, tp,
        ring_invoice_ids=ring_ids, gstin_meta_records=gstins,
    )
    emit(cfg, gstins, bundles, g1, g3, g2b, tp, planted_a, planted_rings)

    hero = planted_rings[0]
    hero_members = list(hero["members"])

    # Build edges + run ring engine — use the SAME shape demo/verify uses
    # so scores match. That means: pin_prefix comes from the buyer GSTIN's
    # pincode[:3], and member_meta.directors from the GSTIN row.
    import csv
    with open(os.path.join(tmp, "ewb.csv"), encoding="utf-8") as f:
        ewb_rows = list(csv.DictReader(f))
    with open(os.path.join(tmp, "invoices.csv"), encoding="utf-8") as f:
        inv_rows = list(csv.DictReader(f))
    with open(os.path.join(tmp, "gstins.csv"), encoding="utf-8") as f:
        gstin_rows = list(csv.DictReader(f))
    veh_by_inv = {e["invoice_id"]: e.get("vehicle_number") for e in ewb_rows}
    pin_by_gstin = {g["gstin_id"]: (g.get("pincode") or "")[:3] for g in gstin_rows}
    dirs_by_gstin = {g["gstin_id"]: [d for d in (g.get("directors") or "").split(";") if d]
                        for g in gstin_rows}
    edges_shape = []
    for r in inv_rows:
        try:
            d = date.fromisoformat(r["date"])
        except (KeyError, ValueError):
            d = None
        edges_shape.append({
            "src": r["supplier_gstin"], "dst": r["buyer_gstin"],
            "invoice_id": r["invoice_id"], "date": d,
            "amount": float(r.get("taxable_value") or 0),
            "gst_amount": float(r.get("total_gst") or 0),
            "vehicle_id": veh_by_inv.get(r["invoice_id"]),
            "hsn": r.get("hsn"),
            "pin_prefix": pin_by_gstin.get(r["buyer_gstin"]),
        })
    rings = run_pipeline(
        graph_source={"edges": edges_shape,
                        "member_meta": {gid: {"directors": dl} for gid, dl in dirs_by_gstin.items()}},
        config=EngineConfig(hop_max=8, window_days=90, persist=False, propagate=False),
    )
    detected = next((r for r in rings if set(r.members) == set(hero_members)), None)

    # Embed lookalike counts for each hero member
    model = train_embed(
        graph_source={"edges": [{"src": e["src"], "dst": e["dst"],
                                      "amount": e["amount"]} for e in edges_shape]},
        config=EmbedConfig(dim=64, walks_per_node=15, walk_len=25, seed=42),
    )
    idx = LookalikeIndex(ids=list(model.ids), matrix=model.matrix)
    hits_per_seed = []
    for m in hero_members:
        top10 = idx.similar_to(m, k=10)
        hits_per_seed.append(sum(1 for gid, _ in top10 if gid in hero_members))

    # Print the constants block ready for scenario.py
    print("== Suggested demo/scenario.py values ==")
    payload = {
        "planted_id": hero["ring_id"],
        "detected_id": (detected.ring_id if detected else None),
        "size": hero["size"],
        "state": "Maharashtra" if all(m.startswith("27") for m in hero_members) else "unknown",
        "hsn": hero.get("hsn"),
        "members": hero_members,
        "invoices": hero["invoices"],
        "common_vehicle": hero.get("common_vehicle"),
        "shared_director": hero.get("shared_director"),
        "hop_inflation": hero.get("hop_inflation"),
        "temporal_window_days": hero.get("temporal_window_days"),
        "closure_start_date": hero.get("closure_start_date"),
        "total_ring_gst_rupees": hero.get("total_ring_gst"),
        "expected_score": (round(detected.score, 3) if detected else None),
        "expected_signals": ({k: round(v, 2) for k, v in detected.signals.items()}
                                 if detected else {}),
        "break_edge_invoice": (detected.break_edge or {}).get("invoice_id") if detected else None,
        "embed_lookalike_min_hero_in_top10": min(hits_per_seed) if hits_per_seed else 0,
        "embed_lookalike_per_seed": hits_per_seed,
    }
    print(json.dumps(payload, indent=2, default=str))
    print()
    # Diff against current. Only compare keys that ALREADY exist in
    # HERO_RING (probing may compute extra info the scenario doesn't
    # need). Numeric comparisons use 2-decimal tolerance.
    def _close(a, b) -> bool:
        if isinstance(a, float) and isinstance(b, float):
            return round(a, 2) == round(b, 2)
        if isinstance(a, dict) and isinstance(b, dict):
            return all(_close(a.get(k), b.get(k)) for k in set(a) | set(b))
        return a == b

    drift = {}
    for k, cur in HERO_RING.items():
        if k not in payload:
            continue
        v = payload[k]
        if not _close(cur, v):
            drift[k] = {"scenario.py": cur, "probed": v}

    if drift:
        print("== DRIFT DETECTED ==")
        print(json.dumps(drift, indent=2, default=str))
        rc = 1
    else:
        print("== NO DRIFT — scenario.py is in sync with datagen ==")
        rc = 0

    shutil.rmtree(tmp, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
