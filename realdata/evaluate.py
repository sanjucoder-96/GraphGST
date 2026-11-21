"""In-memory real-data analysis: run Graph GST's engines over a
`CanonicalDataset` WITHOUT Neo4j, and produce an honest report.

Guarantees: uses the SAME ring engine + risk composer the product uses; runs
in-memory (persist=False) so it never mutates Neo4j or reads the benchmark
baseline; ground-truth metrics appear ONLY when the dataset carries labels.

Adds (Phase 6-7): explainable EVIDENCE CHAINS for candidate rings
(GSTIN A → Invoice → GSTIN B → … → A with dates/amounts/tax), and writes a
non-sensitive aggregate `realdata/reports/latest.json` (Phase 8).
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .schemas.canonical import CanonicalDataset, to_ring_graph_source, to_risk_graph_source
from .validation.quality import feature_availability


def _band(s: float) -> str:
    return "CRITICAL" if s >= 0.45 else "HIGH" if s >= 0.30 else "MED" if s >= 0.15 else "LOW"


# ── Descriptive graph statistics ─────────────────────────────────────────────

def graph_statistics(ds: CanonicalDataset) -> Dict[str, Any]:
    import networkx as nx
    G = nx.DiGraph()
    total_value = 0.0
    pair_txn = defaultdict(int)
    for t in ds.txns:
        pair_txn[(t.supplier_id, t.buyer_id)] += 1
        if t.taxable_value is not None:
            total_value += t.taxable_value
    for (s, d), c in pair_txn.items():
        G.add_edge(s, d, count=c)
    wccs = list(nx.weakly_connected_components(G))
    sccs = [c for c in nx.strongly_connected_components(G) if len(c) > 1]
    mutual = sum(1 for u, v in G.edges() if G.has_edge(v, u))
    return {
        "entities": G.number_of_nodes(), "transactions": len(ds.txns),
        "distinct_directed_edges": G.number_of_edges(), "total_value": round(total_value, 2),
        "weakly_connected_components": len(wccs),
        "largest_wcc_size": max((len(c) for c in wccs), default=0),
        "cyclic_sccs": len(sccs), "entities_in_cycles": sum(len(c) for c in sccs),
        "largest_scc_size": max((len(c) for c in sccs), default=0),
        "mutual_edge_pairs": mutual // 2,
        "avg_out_degree": round(sum(d for _, d in G.out_degree()) / max(1, G.number_of_nodes()), 2),
    }


# ── Ring detection (product engine, in-memory) + evidence chains ─────────────

def _txn_index(ds: CanonicalDataset):
    idx = defaultdict(list)
    for t in ds.txns:
        idx[(t.supplier_id, t.buyer_id)].append(t)
    return idx


def _evidence_chain(members, invoice_set, idx) -> List[Dict[str, Any]]:
    """Reconstruct the explainable walk A → Invoice → B → … → A for one ring."""
    chain = []
    k = len(members)
    for i in range(k):
        src, dst = members[i], members[(i + 1) % k]
        cands = idx.get((src, dst), [])
        pick = next((t for t in cands if t.txn_id in invoice_set), cands[0] if cands else None)
        if pick is None:
            continue
        chain.append({
            "step": i + 1, "from": src, "to": dst, "invoice_id": pick.txn_id,
            "date": pick.date, "amount": pick.taxable_value,
            "tax": pick.tax_amount, "reconciliation_state": pick.status or "unknown",
        })
    return chain


def detect_rings(ds: CanonicalDataset, hop_max: int = 6, evidence_n: int = 5) -> Dict[str, Any]:
    from rings.engine import EngineConfig, run_pipeline
    gs = to_ring_graph_source(ds)
    cfg = EngineConfig(hop_max=hop_max, persist=False, propagate=False, use_gds=False)
    t0 = time.time()
    rings = run_pipeline(cfg, graph_source=gs)
    elapsed = round(time.time() - t0, 2)
    rings_sorted = sorted(rings, key=lambda r: r.score, reverse=True)

    band_counts: Dict[str, int] = defaultdict(int)
    for r in rings:
        band_counts[_band(r.score)] += 1

    idx = _txn_index(ds)
    inv_map = {t.txn_id: t for t in ds.txns}
    top = []
    for r in rings_sorted[:15]:
        inv_set = set(r.invoices)
        top.append({
            "ring_id": r.ring_id, "members": list(r.members), "hops": r.hops,
            "score": round(r.score, 4), "band": _band(r.score),
            "signals": {k: round(v, 3) for k, v in r.signals.items()},
            "n_invoices": len(r.invoices),
            "ring_value": round(sum((inv_map[iid].taxable_value or 0.0)
                                    for iid in inv_set if iid in inv_map), 2),
        })

    # explainable evidence chains for the top-N candidate rings
    evidence = []
    for r in rings_sorted[:evidence_n]:
        chain = _evidence_chain(list(r.members), set(r.invoices), idx)
        evidence.append({
            "ring_id": r.ring_id, "score": round(r.score, 4), "band": _band(r.score),
            "members": list(r.members), "chain": chain,
        })

    members_full = sorted({m for r in rings for m in r.members})
    return {
        "hop_max": hop_max, "rings_detected": len(rings), "elapsed_s": elapsed,
        "band_counts": dict(band_counts), "top_rings": top,
        "evidence_chains": evidence, "members_in_rings": len(members_full),
        "_members_full": members_full,
    }


# ── Partial risk (composer, in-memory) ───────────────────────────────────────

def partial_risk(ds: CanonicalDataset, detected_rings: Optional[List[dict]] = None) -> Dict[str, Any]:
    from risk.api import default_composer
    from risk.context import build_context_from_graph_source
    gs = to_risk_graph_source(ds)
    ctx = build_context_from_graph_source(gs, detected_rings=detected_rings or [])
    composed = default_composer().compose_all(ctx)
    band_counts: Dict[str, int] = defaultdict(int)
    entity_scores: Dict[str, float] = {}
    dicts = []
    for c in composed:
        d = c.to_dict()
        dicts.append(d)
        band_counts[d.get("band", "LOW")] += 1
        gid = d.get("gstin_id")
        if gid is not None:
            entity_scores[gid] = float(d.get("score", 0) or 0)
    top = sorted(dicts, key=lambda d: d.get("score", 0), reverse=True)[:10]
    return {
        "note": ("PARTIAL composite: only the ring + temporal scorers have inputs; "
                 "reconcile/rules need GSTR filings + status this dataset lacks."),
        "scored_entities": len(composed), "band_counts": dict(band_counts),
        "top_entities": [{"gstin_id": t.get("gstin_id"), "score": round(t.get("score", 0), 4),
                          "band": t.get("band"),
                          "contributions": {k: round(v, 3) for k, v in (t.get("contributions") or {}).items()}}
                         for t in top],
        "_entity_scores": entity_scores,
    }


# ── Temporal ─────────────────────────────────────────────────────────────────

def temporal_summary(ds: CanonicalDataset) -> Optional[Dict[str, Any]]:
    dated = [t.date for t in ds.txns if t.date]
    if not dated:
        return None
    by_month: Dict[str, int] = defaultdict(int)
    for d in dated:
        by_month[d[:7]] += 1
    return {"dated_transactions": len(dated), "date_min": min(dated), "date_max": max(dated),
            "months_covered": len(by_month), "transactions_by_month": dict(sorted(by_month.items()))}


# ── Supervised eval (only if labels) ─────────────────────────────────────────

def supervised_eval(ds: CanonicalDataset, ring_members_full: set,
                    entity_scores: Dict[str, float]) -> Optional[Dict[str, Any]]:
    truth_pos = set()
    for t in ds.txns:
        if t.label:
            truth_pos.add(t.supplier_id)
            truth_pos.add(t.buyer_id)
    if not truth_pos:
        return None
    all_entities = {e.entity_id for e in ds.entities}

    pred = set(ring_members_full)
    tp = len(pred & truth_pos); fp = len(pred - truth_pos); fn = len(truth_pos - pred)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    base_rate = len(truth_pos) / max(1, len(all_entities))
    ring_prf = {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4),
                "recall": round(rec, 4), "f1": round(f1, 4),
                "precision_lift_vs_base": round((tp / len(pred)) / base_rate, 2) if (pred and base_rate) else None}

    risk_rank = None
    ranked = [(eid, entity_scores.get(eid, 0.0)) for eid in all_entities]
    y = [1 if eid in truth_pos else 0 for eid, _ in ranked]
    s = [sc for _, sc in ranked]
    if 0 < sum(y) < len(y):
        try:
            from sklearn.metrics import roc_auc_score
            auc = float(roc_auc_score(y, s))
        except Exception:
            auc = None
        order = sorted(range(len(ranked)), key=lambda i: s[i], reverse=True)
        def _p_at(k):
            k = min(k, len(order))
            return round(sum(y[i] for i in order[:k]) / k, 4) if k else None
        risk_rank = {"roc_auc": round(auc, 4) if auc is not None else None,
                     "precision_at_50": _p_at(50), "precision_at_100": _p_at(100),
                     "base_rate": round(base_rate, 4)}

    return {
        "caveat": ("Labels denote money-laundering / fraud in the SOURCE domain, a documented ANALOG of "
                   "GST circular trading — not identical. Measures concentration on labelled-illicit "
                   "entities on an independent labelled graph, not GST-specific accuracy."),
        "labelled_positive_entities": len(truth_pos), "total_entities": len(all_entities),
        "prevalence": round(base_rate, 4), "ring_membership_vs_labels": ring_prf,
        "risk_ranking_vs_labels": risk_rank or {"status": "skipped", "reason": "degenerate label set"},
    }


# ── Orchestration ────────────────────────────────────────────────────────────

def evaluate(ds: CanonicalDataset, hop_max: int = 6) -> Dict[str, Any]:
    features = feature_availability(ds)
    report: Dict[str, Any] = {
        "dataset": {"name": ds.name, "source_url": ds.source_url, "license": ds.license,
                    "description": ds.description, "is_real_taxpayer_data": ds.is_real_taxpayer_data,
                    "anonymized": ds.anonymized, "notes": ds.notes},
        "feature_availability": [r.__dict__ for r in features],
        "graph_statistics": graph_statistics(ds),
    }
    rings = detect_rings(ds, hop_max=hop_max)
    ring_members_full = set(rings.pop("_members_full", []))
    risk = partial_risk(ds, detected_rings=[{"members": r["members"], "score": r["score"]}
                                            for r in rings["top_rings"]])
    entity_scores = risk.pop("_entity_scores", {})
    report["ring_detection"] = rings
    report["risk_scoring_partial"] = risk
    tmp = temporal_summary(ds)
    report["temporal"] = tmp if tmp else {"status": "skipped", "reason": "no per-transaction dates"}

    if any(t.label is not None for t in ds.txns):
        report["evaluation_mode"] = "GROUND_TRUTH (supervised)"
        report["supervised_evaluation"] = supervised_eval(ds, ring_members_full, entity_scores) or {
            "status": "no positive labels present"}
    else:
        report["evaluation_mode"] = "UNSUPERVISED (no labels — real-world analysis only)"
        report["supervised_evaluation"] = {
            "status": "not applicable",
            "reason": "dataset has no fraud/ring labels; reporting graph structure and detected "
                      "suspicious cycles instead of precision/recall."}
    return report


# ── Rendering + CLI ──────────────────────────────────────────────────────────

def render_markdown(report: Dict[str, Any]) -> str:
    d, gs, rd = report["dataset"], report["graph_statistics"], report["ring_detection"]
    L = ["# Real-data evaluation — " + d["name"], "",
         f"**Source:** {d['source_url']}  ", f"**License:** {d['license']}  ",
         f"**Real taxpayer data:** {'yes' if d['is_real_taxpayer_data'] else 'NO (public / anonymised / synthetic)'}  ",
         f"**Anonymized:** {'yes' if d.get('anonymized') else 'no'}  ",
         f"**Evaluation mode:** {report['evaluation_mode']}", "",
         "> " + d["description"], "", "## Feature availability", "",
         "| Feature | Can run? | Why |", "|---|:--:|---|"]
    for r in report["feature_availability"]:
        L.append(f"| {r['feature']} | **{r['can_run']}** | {r['reason']} |")
    L += ["", "## Graph statistics (measured — REAL-DATA OBSERVATIONS, not verified fraud)", "",
          f"- Entities: **{gs['entities']:,}** · Transactions: **{gs['transactions']:,}** · Distinct directed edges: **{gs['distinct_directed_edges']:,}**",
          f"- Total transaction value: **{gs['total_value']:,.0f}**",
          f"- Weakly-connected components: {gs['weakly_connected_components']:,} (largest {gs['largest_wcc_size']:,})",
          f"- Cyclic groups (SCC>1): **{gs['cyclic_sccs']}** · entities that can be in a ring: **{gs['entities_in_cycles']}** (largest SCC {gs['largest_scc_size']})",
          f"- Reciprocal supplier↔buyer pairs (2-cycles): **{gs['mutual_edge_pairs']:,}**", "",
          "## Candidate circular-trading rings (Graph GST engine)", "",
          f"- Cycle bound: ≤ **{rd['hop_max']} hops** (logged bound; the largest SCC combinatorially explodes beyond this)",
          f"- Candidate rings: **{rd['rings_detected']:,}** in {rd['elapsed_s']}s · entities in rings: **{rd['members_in_rings']}**",
          f"- Band distribution: {rd['band_counts']}", "",
          "Top candidates (NOT confirmed fraud):", "",
          "| Ring | Hops | Score | Band | Value |", "|---|:--:|--:|:--:|--:|"]
    for r in rd["top_rings"][:10]:
        L.append(f"| `{r['ring_id']}` | {r['hops']} | {r['score']} | {r['band']} | {r['ring_value']:,.0f} |")
    # evidence chains
    L += ["", "## Explainable evidence chains (top candidates)", ""]
    for ev in rd.get("evidence_chains", [])[:3]:
        L.append(f"**`{ev['ring_id']}`** — score {ev['score']} ({ev['band']}) — investigation candidate:")
        L.append("")
        for step in ev["chain"]:
            amt = f"{step['amount']:,.0f}" if step['amount'] is not None else "—"
            tax = f"{step['tax']:,.0f}" if step['tax'] is not None else "—"
            dt = step['date'] or "no-date"
            L.append(f"- `{step['from']}` → invoice `{step['invoice_id']}` ({dt}, value {amt}, tax {tax}, recon {step['reconciliation_state']}) → `{step['to']}`")
        L.append("")
    tmp = report.get("temporal", {})
    L += ["## Temporal", ""]
    L.append(f"_Skipped — {tmp['reason']}._" if tmp.get("status") == "skipped"
             else f"- Dated transactions: {tmp.get('dated_transactions'):,} · range {tmp.get('date_min')} → {tmp.get('date_max')} · {tmp.get('months_covered')} month(s)")
    rk = report.get("risk_scoring_partial", {})
    L += ["", "## Risk scoring (partial composite)", "", f"_{rk.get('note','')}_", "",
          f"- Scored entities: {rk.get('scored_entities')} · bands: {rk.get('band_counts')}"]
    se = report.get("supervised_evaluation", {})
    L += ["", "## Evaluation vs ground truth", ""]
    if report["evaluation_mode"].startswith("GROUND_TRUTH") and "ring_membership_vs_labels" in se:
        L += [f"> {se['caveat']}", "",
              f"- Labelled-illicit entities: {se['labelled_positive_entities']:,} / {se['total_entities']:,} (prevalence {se['prevalence']})",
              f"- **Ring membership vs labels:** {se['ring_membership_vs_labels']}",
              f"- **Risk ranking vs labels:** {se['risk_ranking_vs_labels']}"]
    else:
        L.append(f"_{se.get('reason', se.get('status',''))}_")
    return "\n".join(L)


def _write_latest_json(report: Dict[str, Any], reports_dir: str) -> None:
    """Non-sensitive aggregate snapshot (Phase 8). No entity ids, no chains."""
    import json
    import os
    gs, rd = report["graph_statistics"], report["ring_detection"]
    se = report.get("supervised_evaluation", {})
    snap = {
        "dataset": report["dataset"]["name"],
        "evaluation_mode": report["evaluation_mode"],
        "is_real_taxpayer_data": report["dataset"]["is_real_taxpayer_data"],
        "anonymized": report["dataset"].get("anonymized"),
        "graph": {k: gs[k] for k in ("entities", "transactions", "distinct_directed_edges",
                                     "total_value", "cyclic_sccs", "entities_in_cycles",
                                     "mutual_edge_pairs")},
        "rings": {"candidates": rd["rings_detected"], "hop_max": rd["hop_max"],
                  "entities_in_rings": rd["members_in_rings"], "band_counts": rd["band_counts"]},
        "supervised": {k: se.get(k) for k in ("ring_membership_vs_labels", "risk_ranking_vs_labels",
                                              "prevalence")} if "ring_membership_vs_labels" in se else None,
    }
    os.makedirs(reports_dir, exist_ok=True)
    with open(os.path.join(reports_dir, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, default=str)


def main():
    import argparse
    import json
    import os
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from .registry import load_dataset, ADAPTERS
    from .validation.quality import validate_and_normalize

    ap = argparse.ArgumentParser(description="Evaluate Graph GST on a real/public dataset (in-memory).")
    ap.add_argument("--source", "--dataset", dest="dataset", required=True, choices=sorted(ADAPTERS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--hop-max", type=int, default=4, help="cycle length bound (default 4; ≥5 explodes on dense graphs)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ds = load_dataset(args.dataset, limit=args.limit)
    ds, _ = validate_and_normalize(ds)
    report = evaluate(ds, hop_max=args.hop_max)

    reports_root = os.path.join(os.path.dirname(__file__), "reports")
    out_dir = args.out or os.path.join(reports_root, args.dataset)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "evaluation_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    md = render_markdown(report)
    with open(os.path.join(out_dir, "evaluation_report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    _write_latest_json(report, reports_root)
    print(md)
    print(f"\n[evaluate] wrote evaluation_report.{{json,md}} -> {out_dir}  + reports/latest.json")


if __name__ == "__main__":
    main()
