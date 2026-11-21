"""SCC gate — cheap Tarjan pass to shortlist candidate subgraphs.

A cycle can only live inside a strongly-connected component; running
Johnson on the whole graph is wasteful. We compute SCCs first and hand
Johnson each non-trivial SCC's induced subgraph.

We prefer Neo4j GDS (`gds.scc.stream`) when the plugin is loaded — the
computation stays in-database and doesn't require pulling every edge to
Python. If GDS isn't available we fall back to NetworkX.

GDS projections have global names inside the database. If any step
between project and drop throws, the projection LEAKS — subsequent
calls trip on the pre-existing name. So the projection lifecycle is
wrapped in try/finally: build in try, always drop (guarded by exists)
in finally.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import networkx as nx

logger = logging.getLogger(__name__)


def gds_available() -> bool:
    """Return True iff the Neo4j GDS plugin responds to a probe call."""
    try:
        from db import run_query
    except Exception:
        return False
    try:
        run_query("CALL gds.version() YIELD gdsVersion RETURN gdsVersion")
        return True
    except Exception:
        return False


def _drop_projection_if_exists(name: str) -> None:
    """Guarded drop — safe to call even if the projection doesn't exist."""
    try:
        from db import run_write
        run_write(
            "CALL gds.graph.exists($name) YIELD exists "
            "WITH exists WHERE exists "
            "CALL gds.graph.drop($name) YIELD graphName RETURN graphName",
            {"name": name},
        )
    except Exception:
        logger.exception("failed to drop GDS projection %s", name)


def sccs_networkx(graph: nx.DiGraph, min_size: int = 2) -> List[Set[str]]:
    """NetworkX SCC pass. Returns only non-trivial SCCs."""
    return [set(c) for c in nx.strongly_connected_components(graph) if len(c) >= min_size]


def sccs_gds(window_days: Optional[int] = None, min_size: int = 2) -> List[Set[str]]:
    """Compute SCCs in-database via GDS. Projection lifecycle is safe."""
    from db import run_query, run_write

    proj = "ring_proj"
    _drop_projection_if_exists(proj)  # clear any leaked prior state

    proj_edge_cypher = (
        "MATCH (a:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(b:GSTIN) "
        + ("WHERE i.invoice_date >= date() - duration({days:$window}) " if window_days else "")
        + "RETURN id(a) AS source, id(b) AS target"
    )

    try:
        run_write(
            "CALL gds.graph.project.cypher('ring_proj', $nodes, $edges, $cfg) "
            "YIELD graphName RETURN graphName",
            params={
                "nodes": "MATCH (g:GSTIN) RETURN id(g) AS id",
                "edges": proj_edge_cypher,
                "cfg": {"parameters": {"window": window_days or 0}},
            },
        )
        rows = run_query(
            "CALL gds.scc.stream('ring_proj') YIELD nodeId, componentId "
            "RETURN gds.util.asNode(nodeId).gstin_id AS gstin, componentId ORDER BY componentId"
        )
        buckets: Dict[Any, Set[str]] = {}
        for r in rows:
            buckets.setdefault(r["componentId"], set()).add(r["gstin"])
        return [s for s in buckets.values() if len(s) >= min_size]
    finally:
        _drop_projection_if_exists(proj)


def compute_sccs(
    graph: Optional[nx.DiGraph] = None,
    use_gds: bool = False,
    window_days: Optional[int] = None,
    min_size: int = 2,
) -> List[Set[str]]:
    if graph is not None:
        return sccs_networkx(graph, min_size=min_size)
    if use_gds and gds_available():
        try:
            return sccs_gds(window_days=window_days, min_size=min_size)
        except Exception:
            logger.exception("sccs_gds failed; falling back to NetworkX")
    from db import run_query
    edges_cy = (
        "MATCH (a:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(b:GSTIN) "
        + ("WHERE i.invoice_date >= date() - duration({days:$window}) " if window_days else "")
        + "RETURN a.gstin_id AS src, b.gstin_id AS dst"
    )
    rows = run_query(edges_cy, {"window": window_days} if window_days else None)
    G = nx.DiGraph()
    for r in rows:
        G.add_edge(r["src"], r["dst"])
    return sccs_networkx(G, min_size=min_size)
