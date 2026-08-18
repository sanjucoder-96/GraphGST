"""ScorerContext — the shared read-only bundle every scorer sees.

Rather than have each scorer hydrate its own view of the graph, the
composer builds ONE context up front (either from a Neo4j round-trip or
from an in-memory `graph_source` dict), then hands it to every scorer.
This keeps scorer code Neo4j-agnostic and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple


@dataclass
class ScorerContext:
    """Snapshot of everything the scorers might need for one composition pass."""
    # ── Core graph slices ────────────────────────────────────────────
    gstins: List[Dict[str, Any]] = field(default_factory=list)
    invoices: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)        # rings-style edge list

    # ── Filing / payment state (fast lookups) ────────────────────────
    gstr1_keys: Set[Tuple[str, str]] = field(default_factory=set)
    gstr3b_keys: Set[Tuple[str, str]] = field(default_factory=set)
    settled_keys: Set[str] = field(default_factory=set)
    ewb_by_invoice: Set[str] = field(default_factory=set)

    # ── Derived (populated by build_context_from_graph_source) ───────
    invoices_by_gstin: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    neighbors_out: Dict[str, Set[str]] = field(default_factory=dict)
    neighbors_in: Dict[str, Set[str]] = field(default_factory=dict)
    supplier_status: Dict[str, str] = field(default_factory=dict)

    # ── Optional cross-engine inputs ─────────────────────────────────
    match_events: List[Dict[str, Any]] = field(default_factory=list)  # reconcile output
    detected_rings: List[Dict[str, Any]] = field(default_factory=list)  # rings output
    member_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # ── Derived indexes for scorer perf ──────────────────────────────
    rings_by_gstin: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    events_by_supplier: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # ── Convenience ──────────────────────────────────────────────────
    def all_gstin_ids(self) -> List[str]:
        return [g["gstin_id"] for g in self.gstins if g.get("gstin_id")]


def build_context_from_graph_source(
    graph_source: Mapping[str, Any],
    match_events: Optional[Sequence[dict]] = None,
    detected_rings: Optional[Sequence[dict]] = None,
    member_meta: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> ScorerContext:
    """Build a ScorerContext from the graph_source dict shape used by
    `reconcile.engine.run_reconcile` and `rings.engine.run_pipeline`."""
    ctx = ScorerContext(
        gstins=list(graph_source.get("gstins") or []),
        invoices=list(graph_source.get("invoices") or []),
        edges=list(graph_source.get("edges") or []),
        gstr1_keys=set(graph_source.get("gstr1_keys") or ()),
        gstr3b_keys=set(graph_source.get("gstr3b_keys") or ()),
        settled_keys=set(graph_source.get("settled_keys") or ()),
        ewb_by_invoice=set(graph_source.get("ewb_by_invoice") or ()),
        match_events=list(match_events or []),
        detected_rings=list(detected_rings or []),
        member_meta={k: dict(v) for k, v in (member_meta or {}).items()},
    )
    # Index invoices by supplier for fast per-GSTIN scoring.
    for inv in ctx.invoices:
        sup = inv.get("supplier_gstin")
        if sup:
            ctx.invoices_by_gstin.setdefault(sup, []).append(inv)
    # Build adjacency from the edge list (used by TemporalScorer for burst
    # detection and by PropagationScorer's fallback).
    for e in ctx.edges:
        s, d = e.get("src"), e.get("dst")
        if s and d:
            ctx.neighbors_out.setdefault(s, set()).add(d)
            ctx.neighbors_in.setdefault(d, set()).add(s)
    for g in ctx.gstins:
        gid = g.get("gstin_id")
        st = g.get("status", "Active")
        if gid:
            ctx.supplier_status[gid] = st
    # Pre-index rings by member and events by supplier so scorers don't
    # rescan the full list per GSTIN — takes composer runtime from
    # O(N × R + N × E) to O(N).
    for r in ctx.detected_rings:
        for m in r.get("members") or []:
            ctx.rings_by_gstin.setdefault(m, []).append(r)
    for e in ctx.match_events:
        sup = e.get("supplier_gstin")
        if sup:
            ctx.events_by_supplier.setdefault(sup, []).append(e)
    return ctx
