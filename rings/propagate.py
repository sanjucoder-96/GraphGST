"""Personalised PageRank propagation seeded from confirmed rings.

Uses Neo4j GDS `pageRank` with `sourceNodes` when available, and
`networkx.pagerank(personalization=...)` as the fallback.

Seed-overlap semantics fix (Phase 3 revision)
---------------------------------------------
The original NetworkX fallback silently substituted a plain (uniform)
PageRank when no ring member existed in the graph. That produced a
non-zero `ring_propagated_score` on EVERY GSTIN with no actual
relationship to any detected ring — misleading downstream consumers
that ranked by this property.

The fix: when no seed overlaps the graph, we return {} and
`write_scores` no-ops. The property is left unset (or at its last
valid value) rather than filled with a synthesised score that means
nothing.

Projection lifecycle for GDS is also wrapped in try/finally so a
failed pageRank call doesn't leak the projection.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

import networkx as nx

from .scc import gds_available, _drop_projection_if_exists

logger = logging.getLogger(__name__)


def _gds_propagate(seed_gstins: List[str]) -> Dict[str, float]:
    from db import run_query, run_write

    proj = "ring_prop"
    _drop_projection_if_exists(proj)

    try:
        run_write(
            "CALL gds.graph.project.cypher('ring_prop', $nodes, $edges) "
            "YIELD graphName RETURN graphName",
            params={
                "nodes": "MATCH (g:GSTIN) RETURN id(g) AS id",
                "edges": (
                    "MATCH (a:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(b:GSTIN) "
                    "RETURN id(a) AS source, id(b) AS target"
                ),
            },
        )
        rows = run_query(
            "MATCH (g:GSTIN) WHERE g.gstin_id IN $seeds RETURN collect(id(g)) AS ids",
            {"seeds": seed_gstins},
        )
        seed_ids = rows[0]["ids"] if rows else []
        if not seed_ids:
            # No seed overlap — do NOT run a uniform PageRank and
            # pretend it's a ring-propagated score.
            return {}
        scores_rows = run_query(
            "CALL gds.pageRank.stream('ring_prop', {sourceNodes: $seeds, dampingFactor: 0.85}) "
            "YIELD nodeId, score "
            "RETURN gds.util.asNode(nodeId).gstin_id AS gstin, score",
            {"seeds": seed_ids},
        )
        return {r["gstin"]: float(r["score"]) for r in scores_rows}
    finally:
        _drop_projection_if_exists(proj)


def _networkx_propagate(
    seed_gstins: List[str], graph: Optional[nx.DiGraph] = None
) -> Dict[str, float]:
    if graph is None:
        from db import run_query
        rows = run_query(
            "MATCH (a:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(b:GSTIN) "
            "RETURN a.gstin_id AS src, b.gstin_id AS dst"
        )
        G = nx.DiGraph()
        for r in rows:
            G.add_edge(r["src"], r["dst"])
    else:
        G = graph
    if G.number_of_nodes() == 0:
        return {}
    seeds = [s for s in seed_gstins if s in G]
    if not seeds:
        # No seed overlap: the caller asked for a PERSONALISED
        # propagation. Returning uniform PageRank here would lie about
        # provenance — downstream ranking would think rings caused
        # scores that have no relation to any detected ring. Return {}
        # so write_scores no-ops.
        logger.info(
            "ring propagation skipped: none of %d seed GSTINs are in the graph",
            len(seed_gstins),
        )
        return {}
    personalization = {n: (1.0 if n in seeds else 0.0) for n in G.nodes}
    pr = nx.pagerank(G, personalization=personalization)
    return {k: float(v) for k, v in pr.items()}


def write_scores(scores: Dict[str, float]) -> int:
    if not scores:
        return 0
    from db import run_write
    payload = [{"gstin": g, "score": s} for g, s in scores.items()]
    rows = run_write(
        "UNWIND $rows AS row "
        "MATCH (g:GSTIN {gstin_id: row.gstin}) "
        "SET g.ring_propagated_score = row.score "
        "RETURN count(g) AS n",
        {"rows": payload},
    )
    return int(rows[0]["n"]) if rows else 0


def propagate(
    seed_gstins: Iterable[str],
    *,
    use_gds: bool = True,
    graph: Optional[nx.DiGraph] = None,
) -> Dict[str, float]:
    seeds = list(seed_gstins)
    if graph is not None:
        return _networkx_propagate(seeds, graph=graph)
    if use_gds and gds_available():
        try:
            return _gds_propagate(seeds)
        except Exception:
            logger.exception("_gds_propagate failed; falling back to NetworkX")
    return _networkx_propagate(seeds)
