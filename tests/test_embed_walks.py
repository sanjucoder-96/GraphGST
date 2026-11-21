"""Tests for random-walk sampling and adjacency building."""
from __future__ import annotations

from embed.walks import biased_walks, build_adjacency


def test_build_adjacency_folds_directions_and_sums():
    edges = [
        {"src": "A", "dst": "B", "amount": 10_000},
        {"src": "A", "dst": "B", "amount": 20_000},
        {"src": "C", "dst": "B", "amount": 5_000},
        {"src": "A", "dst": "A"},   # self-loop dropped
    ]
    nb = build_adjacency(edges, amount_kicker=0.0001)
    # Symmetric
    assert "B" in dict(nb["A"])
    assert "A" in dict(nb["B"])
    # A-B: 2 invoices (count 2) + kicker (30_000 * 0.0001 = 3)
    ab = next(w for n, w in nb["A"] if n == "B")
    assert abs(ab - (2.0 + 3.0)) < 1e-6
    # No self-loop
    assert not any(n == "A" for n, _ in nb.get("A", []))


def test_biased_walks_length_and_start():
    nb = {"A": [("B", 1.0)], "B": [("A", 1.0), ("C", 1.0)],
            "C": [("B", 1.0)]}
    walks = biased_walks(nb, num_walks=3, walk_len=5, seed=1)
    # 3 walks/node * 3 nodes = 9 walks
    assert len(walks) == 3 * 3
    for w in walks:
        assert 1 <= len(w) <= 5
        assert w[0] in {"A", "B", "C"}


def test_biased_walks_deterministic_with_seed():
    nb = {"A": [("B", 1.0), ("C", 1.0)],
            "B": [("A", 1.0), ("C", 1.0)],
            "C": [("A", 1.0), ("B", 1.0)]}
    a = biased_walks(nb, num_walks=5, walk_len=10, seed=42)
    b = biased_walks(nb, num_walks=5, walk_len=10, seed=42)
    assert a == b


def test_biased_walks_p_return_bias():
    # High p (return) => walker should avoid backtracking
    nb = {"A": [("B", 1.0)], "B": [("A", 1.0), ("C", 1.0)],
            "C": [("B", 1.0), ("D", 1.0)], "D": [("C", 1.0)]}
    walks_lowp = biased_walks(nb, num_walks=20, walk_len=6, p=0.1, q=1.0, seed=7)
    walks_highp = biased_walks(nb, num_walks=20, walk_len=6, p=10.0, q=1.0, seed=7)
    # Count how often the walker returns to the previous node.
    def backtracks(walks):
        n = 0
        for w in walks:
            for i in range(2, len(w)):
                if w[i] == w[i - 2]:
                    n += 1
        return n
    # High p => bias divides weight by p => less likely to return
    assert backtracks(walks_highp) <= backtracks(walks_lowp)


def test_biased_walks_empty_graph_ok():
    walks = biased_walks({}, num_walks=5, walk_len=10, seed=1)
    assert walks == []
