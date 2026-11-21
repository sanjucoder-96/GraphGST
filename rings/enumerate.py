"""Bounded Johnson's algorithm on each SCC-induced subgraph."""
from __future__ import annotations

from typing import Iterable, List, Sequence, Set, Tuple

import networkx as nx


def build_digraph(edges: Iterable[dict]) -> nx.DiGraph:
    G = nx.DiGraph()
    for e in edges:
        s = e["src"]; d = e["dst"]
        G.add_node(s); G.add_node(d)
        G.add_edge(s, d)
    return G


def enumerate_cycles_in_scc(
    graph: nx.DiGraph, scc: Set[str], hop_max: int = 8
) -> List[Tuple[str, ...]]:
    if len(scc) < 2:
        return []
    H = graph.subgraph(scc).copy()
    out: List[Tuple[str, ...]] = []
    try:
        it = nx.simple_cycles(H, length_bound=hop_max)
    except TypeError:
        it = (c for c in nx.simple_cycles(H) if len(c) <= hop_max)
    for cyc in it:
        if len(cyc) < 2:
            continue
        out.append(tuple(cyc))
    return out


def enumerate_cycles(
    edges: Iterable[dict], sccs: Sequence[Set[str]], hop_max: int = 8
) -> List[Tuple[str, ...]]:
    G = build_digraph(edges)
    cycles: List[Tuple[str, ...]] = []
    for scc in sccs:
        cycles.extend(enumerate_cycles_in_scc(G, scc, hop_max=hop_max))
    return cycles
