"""Random-walk sampling for node2vec-style embeddings.

Node2vec's contribution over DeepWalk is a biased random walker: at each
step, hyperparameters `p` (return) and `q` (in-out) control whether the
walk prefers to backtrack, stay local, or explore. We implement the
biased sampler with alias tables so per-step cost is O(1) after the
one-time O(E) preprocessing.

Both directions of every edge are used when building the adjacency
(a supplier's neighbourhood in the trade graph includes both buyers and
sellers), and edge weights sum invoice counts + a small amount-derived
kicker so a supplier with 1000 tiny invoices to a shell isn't equal to
a supplier with 5 large invoices to real companies.
"""
from __future__ import annotations

import math
import random
from typing import Dict, Iterable, List, Sequence, Tuple


Neighbours = Dict[str, List[Tuple[str, float]]]


def build_adjacency(
    edges: Iterable[dict],
    amount_kicker: float = 0.0001,
) -> Neighbours:
    """Fold a directed edge list into an undirected weighted graph.

    Weight for (a, b) is the number of invoices between them plus
    `amount_kicker × total_amount` so high-value relationships nudge
    the walker toward economically-important neighbours.
    """
    w: Dict[Tuple[str, str], float] = {}
    for e in edges:
        s, d = e.get("src"), e.get("dst")
        if not s or not d or s == d:
            continue
        key = (s, d) if s < d else (d, s)
        w[key] = w.get(key, 0.0) + 1.0 + amount_kicker * float(e.get("amount", 0) or 0)

    nb: Neighbours = {}
    for (a, b), weight in w.items():
        nb.setdefault(a, []).append((b, weight))
        nb.setdefault(b, []).append((a, weight))
    # Deterministic ordering
    for k in nb:
        nb[k].sort()
    return nb


def _alias_setup(probs: Sequence[float]) -> Tuple[List[int], List[float]]:
    """Vose's alias method for O(1) sampling from a discrete distribution."""
    n = len(probs)
    prob = [0.0] * n
    alias = [0] * n
    scaled = [p * n for p in probs]
    small: List[int] = []
    large: List[int] = []
    for i, s in enumerate(scaled):
        (small if s < 1.0 else large).append(i)
    while small and large:
        s = small.pop()
        l = large.pop()
        prob[s] = scaled[s]
        alias[s] = l
        scaled[l] = scaled[l] + scaled[s] - 1.0
        if scaled[l] < 1.0:
            small.append(l)
        else:
            large.append(l)
    while large:
        prob[large.pop()] = 1.0
    while small:
        prob[small.pop()] = 1.0
    return alias, prob


def _alias_draw(alias: Sequence[int], prob: Sequence[float], rng: random.Random) -> int:
    n = len(alias)
    i = rng.randrange(n)
    return i if rng.random() < prob[i] else alias[i]


def biased_walks(
    neighbours: Neighbours,
    num_walks: int = 10,
    walk_len: int = 20,
    p: float = 1.0,
    q: float = 1.0,
    seed: int = 42,
) -> List[List[str]]:
    """Generate biased random walks per node2vec §3.2.

    * `p` — return parameter. High = walks avoid the previous node.
    * `q` — in-out parameter. High = walks stay local (BFS-like).
    * Default p=1, q=1 = plain DeepWalk. p=1, q=0.5 = more macro-view.
    """
    rng = random.Random(seed)
    nodes = sorted(neighbours.keys())
    walks: List[List[str]] = []

    # Node alias tables — probability of the FIRST step from each node
    node_alias: Dict[str, Tuple[List[int], List[float], List[str]]] = {}
    for u, nbs in neighbours.items():
        if not nbs:
            continue
        w = [wt for _, wt in nbs]
        total = sum(w) or 1.0
        alias, prob = _alias_setup([x / total for x in w])
        node_alias[u] = (alias, prob, [n for n, _ in nbs])

    # Edge alias tables — probability of the NEXT step conditioned on
    # coming FROM `prev` and standing AT `curr`. Precomputed lazily
    # (huge graphs would want this precomputed; for our scale it's fine).
    edge_alias: Dict[Tuple[str, str], Tuple[List[int], List[float], List[str]]] = {}

    def _get_edge_alias(prev: str, curr: str):
        key = (prev, curr)
        cache = edge_alias.get(key)
        if cache is not None:
            return cache
        nbs = neighbours.get(curr, [])
        prev_nbs = {n for n, _ in neighbours.get(prev, [])}
        biased: List[float] = []
        names: List[str] = []
        for nxt, wt in nbs:
            if nxt == prev:
                bias = wt / p
            elif nxt in prev_nbs:
                bias = wt  # distance-1 from prev
            else:
                bias = wt / q
            biased.append(bias); names.append(nxt)
        total = sum(biased) or 1.0
        alias, prob = _alias_setup([x / total for x in biased])
        cache = (alias, prob, names)
        edge_alias[key] = cache
        return cache

    for _ in range(num_walks):
        # Shuffle start-order for well-mixed corpora
        order = list(nodes)
        rng.shuffle(order)
        for start in order:
            if start not in node_alias:
                walks.append([start])
                continue
            walk = [start]
            # First step from `start`
            alias, prob, names = node_alias[start]
            walk.append(names[_alias_draw(alias, prob, rng)])
            # Subsequent biased steps
            while len(walk) < walk_len:
                curr = walk[-1]
                prev = walk[-2]
                if curr not in neighbours or not neighbours[curr]:
                    break
                alias, prob, names = _get_edge_alias(prev, curr)
                walk.append(names[_alias_draw(alias, prob, rng)])
            walks.append(walk)
    return walks
