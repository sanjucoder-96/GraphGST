"""PropagationScorer — personalized PageRank seeded from confirmed ring members.

Every GSTIN in `ctx.detected_rings[*]["members"]` is a seed. We run
personalized PageRank over the invoice-projection edges, then normalize
by the max mass so the winner scores 1.0 and everyone else is
relative. Seeds themselves are excluded from the emitted reason list
(they already have a stronger reason from RingScorer).
"""
from __future__ import annotations

import logging
from typing import Dict

from ..context import ScorerContext
from ..reasons import Reason
from .base import ScorerResult

logger = logging.getLogger(__name__)


def _networkx_ppr(ctx: ScorerContext, seeds: set[str]) -> Dict[str, float]:
    try:
        import networkx as nx
    except Exception as e:
        logger.warning("PropagationScorer needs networkx: %s", e)
        return {}
    G = nx.DiGraph()
    for e in ctx.edges:
        s, d = e.get("src"), e.get("dst")
        if s and d:
            G.add_edge(s, d)
    if G.number_of_nodes() == 0:
        return {}
    seeds_in = seeds & set(G.nodes())
    if not seeds_in:
        return {}
    personalization = {n: (1.0 if n in seeds_in else 0.0) for n in G.nodes()}
    try:
        pr = nx.pagerank(G, alpha=0.85, personalization=personalization,
                          max_iter=100, tol=1e-6)
    except Exception:
        logger.exception("PPR failed")
        return {}
    top = max(pr.values()) if pr else 0.0
    if top <= 0:
        return {}
    return {k: v / top for k, v in pr.items()}


class PropagationScorer:
    name = "propagate"

    def __init__(self, weight: float = 0.15, min_ring_score: float = 0.45):
        """Only seed PPR from rings above min_ring_score — otherwise
        every incidental cycle poisons the propagation with noise."""
        self.weight = weight
        self.min_ring_score = min_ring_score
        self._cached: Dict[str, float] | None = None
        self._cached_ctx_id: int | None = None
        self._seed_set: set[str] = set()

    def _run(self, ctx: ScorerContext) -> None:
        seeds: set[str] = set()
        for r in ctx.detected_rings:
            if float(r.get("score", 0.0)) < self.min_ring_score:
                continue
            seeds.update(r.get("members") or [])
        self._seed_set = seeds
        self._cached = _networkx_ppr(ctx, seeds) if seeds else {}
        self._cached_ctx_id = id(ctx)

    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        if self._cached is None or self._cached_ctx_id != id(ctx):
            self._run(ctx)
        if not self._cached:
            return ScorerResult(subscore=0.0, reasons=[])
        s = float(self._cached.get(gstin_id, 0.0))
        if s <= 0.05:
            return ScorerResult(subscore=0.0, reasons=[])
        # Seeds get zero contribution — they're already flagged by RingScorer
        if gstin_id in self._seed_set:
            return ScorerResult(subscore=0.0, reasons=[])
        return ScorerResult(subscore=s, reasons=[Reason(
            name="ring-adjacent",
            weight=s,
            detail=(
                f"Personalized-PageRank mass {s:.2f} from {len(self._seed_set)} "
                f"confirmed-ring seed(s) — this entity trades close to the ring "
                f"even though it is not itself a member"
            ),
            evidence={"node_type": "GSTIN", "node_id": gstin_id,
                        "seed_count": len(self._seed_set)},
        )])
