"""Benchmark: reconcile precision/recall/F1 per outcome against datagen truth.

Generates a synthetic dataset with a rich mix of planted anomalies,
runs the reconcile engine in-memory (no Neo4j needed), then matches
emitted MatchEvents against truth.json's `planted_anomalies` to score:

    for each outcome type:
      TP = events whose (invoice_id, outcome) matches a planted anomaly
      FP = events on an invoice with no planted anomaly of that type
      FN = planted anomalies with no matching emitted event
      P  = TP / (TP + FP);  R = TP / (TP + FN);  F1 = 2PR/(P+R)

Notes on scoring:
  * The engine may correctly detect a defect that datagen didn't plant
    (e.g. an incidental duplicate invoice_id in normal population).
    Those show up as FPs against truth.
  * MATCHED events are excluded — they are the "no defect" background.
  * CANCELLED_SUPPLIER is scored at the GSTIN level (any event on any
    invoice from that supplier counts as a hit).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
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


def _generate(cfg: GenerationConfig) -> None:
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
        gstin_meta_records=gstins)
    emit(cfg, gstins, bundles, g1, g3, g2b, tp, planted_anoms, planted_rings)


def _load_graph_source(dir: str) -> dict:
    def _read(name):
        with open(os.path.join(dir, name), encoding="utf-8") as f:
            return list(csv.DictReader(f))

    gstins_rows = _read("gstins.csv")
    invoice_rows = _read("invoices.csv")
    ewb_rows = _read("ewb.csv")
    pr_rows = _read("pr.csv")
    g1_rows = _read("gstr1.csv")
    g3_rows = _read("gstr3b.csv")
    tp_rows = _read("taxpayments.csv")

    # coerce numerics
    for i in invoice_rows:
        for k in ("taxable_value", "cgst", "sgst", "igst", "total_gst"):
            v = i.get(k)
            i[k] = float(v) if v not in (None, "") else 0.0
        i["ewb_required"] = str(i.get("ewb_required", "")).lower() in ("true", "1")
    for p in pr_rows:
        for k in ("booked_amount", "booked_tax"):
            v = p.get(k)
            p[k] = float(v) if v not in (None, "") else 0.0

    gstr1_keys = {(g["gstin"], g["period"]) for g in g1_rows}
    gstr3b_keys = {(g["gstin"], g["period"]) for g in g3_rows}
    settled_keys = {t["gstr3b_return_id"] for t in tp_rows if (t.get("status") or "").upper() == "CLEARED"}
    ewb_by_invoice = {e["invoice_id"] for e in ewb_rows if e.get("invoice_id")}

    return {
        "invoices": invoice_rows,
        "pr": pr_rows,
        "gstins": gstins_rows,
        "gstr1_keys": gstr1_keys,
        "gstr3b_keys": gstr3b_keys,
        "settled_keys": settled_keys,
        "ewb_by_invoice": ewb_by_invoice,
    }


def _score(events: list[dict], truth: dict, gstins: list[dict],
             hsn_catalog: dict, invoices: list[dict] | None = None) -> dict:
    invoices = invoices or []
    # Index invoices for cascade expansion:
    #   (supplier_gstin, period) -> [invoice_id, ...]
    by_sup_period: dict[tuple[str, str], list[str]] = defaultdict(list)
    inv_by_id: dict[str, dict] = {}
    for i in invoices:
        by_sup_period[(i["supplier_gstin"], i["period"])].append(i["invoice_id"])
        inv_by_id[i["invoice_id"]] = i

    # Outcomes that cascade to every invoice in a (supplier, period).
    # Engine precedence: GSTR1 > GSTR3B > TAX_PAYMENT (only one fires per
    # invoice). So when we cascade-expand, we must ALSO respect that
    # precedence: if a (supplier, period) had MISSING_GSTR1 planted, its
    # invoices are expected to raise MISSING_GSTR1 only, NOT the two
    # lower-precedence outcomes (the engine won't fire them).
    _CASCADE_PRIORITY = {
        "MISSING_GSTR1": 3, "MISSING_GSTR3B": 2, "MISSING_TAX_PAYMENT": 1,
    }
    cascade_seed_priority: dict[tuple[str, str], int] = {}
    cascade_seed_outcome: dict[tuple[str, str], str] = {}

    expected: dict[tuple[str, str], list[dict]] = defaultdict(list)
    cancelled_gstins: set[str] = set()
    for a in truth.get("planted_anomalies", []):
        t = a.get("type")
        if t == "CANCELLED_SUPPLIER":
            cancelled_gstins.add(a.get("gstin_id"))
            continue
        iid = a.get("invoice_id") or a.get("of_invoice")
        if not iid:
            continue
        expected[(iid, t)].append(a)
        if t in _CASCADE_PRIORITY:
            inv = inv_by_id.get(iid)
            if not inv:
                continue
            key = (inv["supplier_gstin"], inv["period"])
            prio = _CASCADE_PRIORITY[t]
            if prio > cascade_seed_priority.get(key, 0):
                cascade_seed_priority[key] = prio
                cascade_seed_outcome[key] = t

    for key, top_outcome in cascade_seed_outcome.items():
        for cascade_iid in by_sup_period.get(key, []):
            expected[(cascade_iid, top_outcome)].append({"_cascade": True})

    # CANCELLED_SUPPLIER — planted at the GSTIN level. Every invoice from
    # a cancelled supplier is expected to raise CANCELLED_SUPPLIER.
    for i in invoices:
        if i["supplier_gstin"] in cancelled_gstins:
            expected[(i["invoice_id"], "CANCELLED_SUPPLIER")].append(
                {"_cascade": True, "type": "CANCELLED_SUPPLIER",
                 "supplier": i["supplier_gstin"]})

    # Build actual outcome sets from events
    actual: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in events:
        if e["outcome"] == "MATCHED":
            continue
        actual[(e["invoice_id"], e["outcome"])].append(e)

    outcomes = sorted(set(o for _, o in expected) | set(o for _, o in actual))

    per_outcome = {}
    for o in outcomes:
        exp_keys = {k for k in expected if k[1] == o}
        act_keys = {k for k in actual if k[1] == o}
        tp = len(exp_keys & act_keys)
        fp = len(act_keys - exp_keys)
        fn = len(exp_keys - act_keys)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        per_outcome[o] = {"tp": tp, "fp": fp, "fn": fn,
                            "precision": round(p, 3),
                            "recall": round(r, 3),
                            "f1": round(f, 3),
                            "n_planted": len(exp_keys),
                            "n_detected": len(act_keys)}

    # Cancelled supplier — score at the GSTIN level (any invoice event counts)
    detected_cancelled = {e["supplier_gstin"] for e in events
                            if e["outcome"] == "CANCELLED_SUPPLIER"}
    ctp = len(cancelled_gstins & detected_cancelled)
    cfp = len(detected_cancelled - cancelled_gstins)
    cfn = len(cancelled_gstins - detected_cancelled)
    per_outcome["CANCELLED_SUPPLIER (gstin-level)"] = {
        "tp": ctp, "fp": cfp, "fn": cfn,
        "precision": round(ctp / (ctp + cfp), 3) if (ctp + cfp) else 0.0,
        "recall":    round(ctp / (ctp + cfn), 3) if (ctp + cfn) else 0.0,
        "f1":        round(2 * ctp / (2 * ctp + cfp + cfn), 3) if (2 * ctp + cfp + cfn) else 0.0,
        "n_planted": len(cancelled_gstins),
        "n_detected": len(detected_cancelled),
    }
    return per_outcome


def bench_prepared(cfg: GenerationConfig, out_dir: str) -> dict:
    """Run the reconcile PRF benchmark on an already-generated dataset dir."""
    t_gen = 0.0

    with open(os.path.join(out_dir, "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)

    t1 = time.perf_counter()
    graph_source = _load_graph_source(out_dir)
    t_load = time.perf_counter() - t1

    t2 = time.perf_counter()
    events = run_reconcile(
        graph_source=graph_source,
        config=ReconcileConfig(include_matched=False, hsn_catalog=HSN_CATALOG),
    )
    t_reconcile = time.perf_counter() - t2

    per_outcome = _score(events, truth, graph_source["gstins"], HSN_CATALOG,
                          invoices=graph_source["invoices"])
    # totals ignoring MATCHED
    tp_total = sum(v["tp"] for v in per_outcome.values())
    fp_total = sum(v["fp"] for v in per_outcome.values())
    fn_total = sum(v["fn"] for v in per_outcome.values())
    p = tp_total / (tp_total + fp_total) if (tp_total + fp_total) else 0.0
    r = tp_total / (tp_total + fn_total) if (tp_total + fn_total) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0

    return {
        "config": cfg.to_dict(),
        "timing_sec": {"generate": round(t_gen, 3),
                        "load_csv": round(t_load, 3),
                        "reconcile": round(t_reconcile, 3)},
        "counts": {"events_emitted": len(events),
                    "planted_anomalies": len(truth.get("planted_anomalies", [])),
                    "invoices": len(graph_source["invoices"])},
        "micro": {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)},
        "per_outcome": per_outcome,
    }


def bench(cfg: GenerationConfig) -> dict:
    _generate(cfg)
    return bench_prepared(cfg, cfg.out_dir)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-gstins", type=int, default=800)
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--n-rings", type=int, default=6)
    p.add_argument("--ring-size-min", type=int, default=3)
    p.add_argument("--ring-size-max", type=int, default=6)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", type=str, default="./datagen_output_reconcile_bench")
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
