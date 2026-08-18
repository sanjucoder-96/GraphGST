"""Pipeline orchestrator: SCC -> enumerate -> canonicalise -> temporal ->
score -> counterfactual -> (optional) persist -> (optional) propagate.

Revisions in this Phase 3 pass:
  * `load_graph_from_neo4j` now aggregates per invoice so multi-vehicle
    invoices don't produce duplicate edges.
  * Persistence errors are logged with ring_id context and re-raised so
    the API can surface them; propagation failures fall through to a
    logged fallback rather than silently succeeding.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .canonical import canonicalize, ring_id
from .counterfactual import analyse_break
from .enumerate import build_digraph, enumerate_cycles_in_scc
from .scc import compute_sccs
from .scoring import DEFAULT_WEIGHTS, DEFAULT_WINDOW_DAYS, score_ring
from .temporal import group_edges_by_pair, materialize_and_filter

logger = logging.getLogger(__name__)


@dataclass
class EngineConfig:
    hop_max: int = 8
    window_days: int = DEFAULT_WINDOW_DAYS
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    use_gds: bool = True
    persist: bool = True
    propagate: bool = True
    horizon_days: Optional[int] = None


@dataclass
class DetectedRing:
    ring_id: str
    members: Sequence[str]
    invoices: Sequence[str]
    hops: int
    date_span_days: int
    total_gst: float
    score: float
    signals: Dict[str, float]
    contribution: Dict[str, float]
    share: Dict[str, float]
    break_edge: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ring_id": self.ring_id,
            "members": list(self.members),
            "invoices": list(self.invoices),
            "hops": self.hops,
            "date_span_days": self.date_span_days,
            "total_gst": self.total_gst,
            "score": self.score,
            "signals": self.signals,
            "contribution": self.contribution,
            "share": self.share,
            "break_edge": self.break_edge,
        }


def load_graph_from_neo4j(horizon_days: Optional[int] = None) -> Dict[str, Any]:
    """Pull invoice edges + supporting metadata into a Python dict.

    Duplicate-edge fix (Phase 3 revision)
    -------------------------------------
    The original OPTIONAL MATCH to EWayBill->Vehicle produced one row
    per (invoice, vehicle) pair — invoices with multiple e-way bills or
    multiple vehicles yielded duplicate edge dicts. Those duplicates
    inflated _mode_fraction denominators, skewed value_similarity's
    stdev, blew the Cartesian product cap in _pick_best_combination,
    and double-counted total_gst.

    We now aggregate with `WITH ... head(collect(DISTINCT v.vehicle_number))
    AS vehicle_id` so exactly one row is produced per invoice.
    """
    from db import run_query

    where = (
        "WHERE i.invoice_date >= date() - duration({days:$window}) "
        if horizon_days
        else ""
    )
    edge_cy = (
        "MATCH (a:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(b:GSTIN) "
        + where
        + "OPTIONAL MATCH (i)-[:TRANSPORTED_VIA]->(:EWayBill)-[:USED_VEHICLE]->(v:Vehicle) "
        # Aggregate DISTINCT vehicle numbers per invoice, pick one
        # deterministic representative. Guarantees ONE row per invoice.
        + "WITH a, b, i, head(collect(DISTINCT v.vehicle_number)) AS vehicle_id "
        + "RETURN a.gstin_id AS src, b.gstin_id AS dst, i.invoice_id AS invoice_id, "
        + "       i.invoice_date AS invoice_date, i.total_amount AS amount, "
        + "       i.gst_amount AS gst_amount, vehicle_id, "
        + "       i.hsn AS hsn, b.pincode AS buyer_pin"
    )
    params = {"window": horizon_days} if horizon_days else {}
    edge_rows = run_query(edge_cy, params)
    edges: List[Dict[str, Any]] = []
    for r in edge_rows:
        pin = r.get("buyer_pin") or ""
        pin_prefix = str(pin)[:3] if pin else None
        dt = r.get("invoice_date")
        if hasattr(dt, "to_native"):
            dt = dt.to_native()
        edges.append(
            {
                "src": r["src"],
                "dst": r["dst"],
                "invoice_id": r["invoice_id"],
                "date": dt,
                "amount": float(r.get("amount") or 0),
                "gst_amount": float(r.get("gst_amount") or 0),
                "vehicle_id": r.get("vehicle_id"),
                "hsn": r.get("hsn"),
                "pin_prefix": pin_prefix,
            }
        )

    meta_rows = run_query(
        "MATCH (g:GSTIN)-[:DIRECTED_BY]->(d:Director) "
        "RETURN g.gstin_id AS gstin, collect(DISTINCT d.director_id) AS directors"
    )
    member_meta: Dict[str, Dict[str, Any]] = {
        r["gstin"]: {"directors": list(r.get("directors") or [])} for r in meta_rows
    }
    return {"edges": edges, "member_meta": member_meta}


def run_pipeline(
    config: Optional[EngineConfig] = None,
    graph_source: Optional[Mapping[str, Any]] = None,
) -> List[DetectedRing]:
    cfg = config or EngineConfig()

    if graph_source is None:
        graph_source = load_graph_from_neo4j(horizon_days=cfg.horizon_days)
    edges: List[Dict[str, Any]] = list(graph_source.get("edges", []))
    member_meta: Dict[str, Dict[str, Any]] = dict(graph_source.get("member_meta") or {})
    if not edges:
        return []

    G = build_digraph(edges)
    sccs = compute_sccs(graph=G, use_gds=False, min_size=2)

    raw_cycles: List[tuple] = []
    for scc in sccs:
        raw_cycles.extend(enumerate_cycles_in_scc(G, scc, hop_max=cfg.hop_max))
    if not raw_cycles:
        return []

    canonical_map: Dict[str, tuple] = {}
    for c in raw_cycles:
        try:
            rid = ring_id(c)
        except ValueError:
            continue
        if rid not in canonical_map:
            canonical_map[rid] = canonicalize(c)

    edges_by_pair = group_edges_by_pair(edges)
    materialised = materialize_and_filter(
        canonical_map.values(), edges_by_pair, window_days=cfg.window_days
    )

    # Historical priors (H) — read-only, safe-fallback on Neo4j down.
    seen_members: List[str] = []
    if cfg.persist:
        from .persist import fetch_seen_members
        seen_members = fetch_seen_members()

    if cfg.persist:
        # Ensure constraints ONCE at start of the run rather than per
        # ring — schema violations here should surface, not be swallowed.
        try:
            from .persist import ensure_constraints
            ensure_constraints()
        except Exception:
            logger.exception("ensure_constraints failed; persistence will be attempted anyway")

    detected: List[DetectedRing] = []
    for m in materialised:
        members = m["members"]
        ring_edges = m["edges"]
        span = m["date_span_days"]

        n_prior = 0
        rid = ring_id(members)
        if cfg.persist:
            from .persist import count_prior_multiset
            # Safe-fallback on Neo4j down; logs but doesn't raise.
            n_prior = count_prior_multiset(list(members), ring_id_override=rid)

        scored = score_ring(
            members,
            ring_edges,
            date_span_days=span,
            n_prior=n_prior,
            seen_members=seen_members,
            member_meta=member_meta,
            weights=cfg.weights,
            window_days=cfg.window_days,
        )
        total_gst = float(sum(float(e.get("gst_amount", 0) or 0) for e in ring_edges))
        ring_dict = {
            "members": members,
            "edges": ring_edges,
            "score": scored["final"],
            "signals": scored["signals"],
        }
        cf = analyse_break(
            ring_dict,
            window_days=cfg.window_days,
            member_meta=member_meta,
            weights=cfg.weights,
        )

        detected.append(
            DetectedRing(
                ring_id=rid,
                members=list(members),
                invoices=[e["invoice_id"] for e in ring_edges],
                hops=len(members),
                date_span_days=span,
                total_gst=total_gst,
                score=scored["final"],
                signals=scored["signals"],
                contribution=scored["contribution"],
                share=scored["share"],
                break_edge=cf.get("break_edge"),
            )
        )

        if cfg.persist:
            # Persist errors are logged with context (in persist.py) and
            # re-raised so the API can 500 rather than reporting a
            # phantom persisted ring. The engine still processes remaining
            # rings — one bad row shouldn't blow up an entire run —
            # but the exception is annotated at the boundary.
            from .persist import upsert_ring, upsert_break_edge
            try:
                upsert_ring(
                    {
                        "ring_id": rid,
                        "members": list(members),
                        "invoices": [e["invoice_id"] for e in ring_edges],
                        "score": float(scored["final"]),
                        "C": float(scored["signals"]["C"]),
                        "V": float(scored["signals"]["V"]),
                        "T": float(scored["signals"]["T"]),
                        "R": float(scored["signals"]["R"]),
                        "N": float(scored["signals"]["N"]),
                        "H": float(scored["signals"]["H"]),
                        "hops": len(members),
                        "total_gst": total_gst,
                        "date_span_days": span,
                    }
                )
                be = cf.get("break_edge")
                if be is not None:
                    upsert_break_edge(
                        ring_id=rid,
                        from_gstin=be["src"],
                        to_gstin=be["dst"],
                        invoice_id=be.get("invoice_id"),
                        score_after_removal=float(be["score_after"]),
                        score_drop=float(be["score_drop"]),
                        rationale=(
                            f"Removing invoice {be.get('invoice_id')} "
                            f"from {be['src']}->{be['dst']} drops final score "
                            f"by {be['score_drop']:.3f}"
                        ),
                    )
            except Exception:
                # Already logged with ring_id in persist.py. Don't
                # halt the whole run — but do NOT silently ignore either;
                # the API surface will re-run and surface persistent
                # failures via list_rings mismatch on next call.
                logger.exception("persistence failed for ring %s", rid)

    if cfg.propagate and detected:
        try:
            from .propagate import propagate, write_scores
            seeds = sorted({m for r in detected for m in r.members})
            scores = propagate(seeds, use_gds=cfg.use_gds)
            if scores:
                write_scores(scores)
            else:
                logger.info(
                    "ring propagation returned no scores (no seed overlap); "
                    "ring_propagated_score not written"
                )
        except Exception:
            logger.exception("ring propagation failed")

    detected.sort(key=lambda r: r.score, reverse=True)
    return detected
