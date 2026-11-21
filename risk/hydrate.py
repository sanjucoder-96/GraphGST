"""Single, shared live-hydration for the risk composer.

Before this module `risk/api._hydrate_context_or_503` hydrated the graph THREE
times per call (once inside run_reconcile, once inside run_pipeline, and once
more directly) AND passed a graph_source with NO `edges` key to
build_context_from_graph_source — so `ctx.edges` was empty and the neighbour
indexes (`neighbors_out/in`) were never built.

`hydrate_context()` hydrates the invoice/entity view once, pulls the ring-shaped
edge list once, runs reconcile + rings against those in-memory views, and merges
the edges into the context. Note: of the DEFAULT four scorers, none consumes the
neighbour indexes — TemporalScorer reads `invoices_by_gstin` (from invoices), not
edges. The neighbour graph feeds PropagationScorer, which is NOT in the default
composer; the merge keeps the context complete and correct for when propagation
is enabled (and for the ablation), at the cost of one extra read. It returns
(context, detected_rings, match_events) so callers that also persist rings/events
don't recompute them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .context import ScorerContext, build_context_from_graph_source


def _member_meta(gstin_rows: List[dict]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for g in gstin_rows or []:
        ds = g.get("directors") or ""
        if isinstance(ds, str):
            ds = [x for x in ds.split(";") if x]
        out[g.get("gstin_id")] = {"directors": list(ds or [])}
    return out


def hydrate_context(
    persist_rings: bool = False,
    persist_events: bool = False,
) -> Tuple[ScorerContext, List[Any], List[dict]]:
    """Hydrate a ScorerContext + detected rings + non-MATCHED events from Neo4j.

    persist_rings/persist_events control whether the ring and reconcile passes
    also write their results back to Neo4j (used by the materialization/refresh
    path). Per-request callers leave both False.
    """
    from reconcile.engine import (ReconcileConfig, _hydrate_from_neo4j,
                                   run_reconcile)
    from rings.engine import EngineConfig, load_graph_from_neo4j, run_pipeline

    # 1) One entity/invoice/filing hydration (gstins, invoices, pr, keys).
    gs = _hydrate_from_neo4j()

    # 2) One ring-shaped edge hydration; merge edges into the same graph_source
    #    so the context's neighbour indexes (TemporalScorer, PropagationScorer)
    #    are populated instead of empty.
    ring_gs = load_graph_from_neo4j()
    gs["edges"] = ring_gs.get("edges", [])
    member_meta = ring_gs.get("member_meta") or _member_meta(gs.get("gstins", []))

    # 3) Reconcile + rings on the already-hydrated views (no re-hydrate).
    events = run_reconcile(
        graph_source=gs,
        config=ReconcileConfig(include_matched=False, persist=persist_events),
    )
    rings = run_pipeline(
        graph_source={"edges": gs["edges"], "member_meta": member_meta},
        config=EngineConfig(persist=persist_rings, propagate=False),
    )

    ctx = build_context_from_graph_source(
        gs,
        match_events=[e for e in events if e.get("outcome") != "MATCHED"],
        detected_rings=[r.to_dict() if hasattr(r, "to_dict") else r for r in rings],
        member_meta=member_meta,
    )
    return ctx, rings, events
