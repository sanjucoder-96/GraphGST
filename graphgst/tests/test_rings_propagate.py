"""Propagate — including the no-seed-overlap fix."""
import networkx as nx
import pytest

from rings.propagate import _networkx_propagate, propagate


def _small_graph():
    G = nx.DiGraph()
    G.add_edge("A", "B"); G.add_edge("B", "C"); G.add_edge("C", "A")
    G.add_edge("D", "E"); G.add_edge("E", "F")
    return G


def test_propagate_with_seed_overlap_returns_scores():
    G = _small_graph()
    out = propagate(["A"], graph=G)
    assert "A" in out and out["A"] > 0
    # Non-seed nodes reachable from A get non-zero mass.
    assert out["B"] > 0
    assert out["C"] > 0


def test_propagate_no_seed_overlap_returns_empty():
    """REGRESSION: without seed overlap the fallback used to substitute
    a plain PageRank and mislabel it as ring-propagated. Post-fix, we
    return {} so write_scores no-ops.
    """
    G = _small_graph()
    out = propagate(["Z_never_in_graph"], graph=G)
    assert out == {}


def test_propagate_empty_graph_returns_empty():
    G = nx.DiGraph()
    out = propagate(["A"], graph=G)
    assert out == {}


def test_propagate_partial_seed_overlap_uses_only_present_seeds():
    G = _small_graph()
    # "A" is in graph, "Z" is not. Should personalise on "A" alone.
    out = propagate(["A", "Z"], graph=G)
    assert out and "A" in out and out["A"] > 0
