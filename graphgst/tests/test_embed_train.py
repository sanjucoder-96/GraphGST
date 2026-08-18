"""Training end-to-end: PMI matrix + SVD → L2-normalized embedding."""
from __future__ import annotations

import numpy as np

from embed.train import EmbedConfig, _build_sppmi, _cooccurrence, train


def test_train_empty_returns_zero_shape():
    m = train(graph_source={"edges": []}, config=EmbedConfig(dim=8))
    assert m.matrix.shape == (0, 8)
    assert m.ids == []


def test_train_produces_normalized_rows():
    # Two triangles A-B-C and D-E-F, connected by an A-D bridge.
    edges = [
        {"src": "A", "dst": "B", "amount": 100}, {"src": "B", "dst": "C", "amount": 100},
        {"src": "C", "dst": "A", "amount": 100},
        {"src": "D", "dst": "E", "amount": 100}, {"src": "E", "dst": "F", "amount": 100},
        {"src": "F", "dst": "D", "amount": 100},
        {"src": "A", "dst": "D", "amount": 100},
    ]
    m = train(graph_source={"edges": edges},
                config=EmbedConfig(dim=6, walks_per_node=20, walk_len=15, seed=42))
    assert m.matrix.shape[0] == 6         # 6 distinct nodes
    assert m.matrix.shape[1] <= 6
    # Every row unit-length (L2-normalized).
    norms = np.linalg.norm(m.matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_train_clusters_triangle_members():
    """Triangle mates should be closer to each other than to a bridged
    other-cluster node."""
    edges = [
        {"src": "A", "dst": "B", "amount": 100},
        {"src": "B", "dst": "C", "amount": 100},
        {"src": "C", "dst": "A", "amount": 100},
        {"src": "D", "dst": "E", "amount": 100},
        {"src": "E", "dst": "F", "amount": 100},
        {"src": "F", "dst": "D", "amount": 100},
        {"src": "A", "dst": "D", "amount": 1},   # weak bridge
    ]
    m = train(graph_source={"edges": edges},
                config=EmbedConfig(dim=6, walks_per_node=40, walk_len=20, seed=7))
    idx = m.id_to_index()
    def sim(a, b):
        return float(m.matrix[idx[a]] @ m.matrix[idx[b]])
    # Same-cluster pairs (A,B), (B,C), (A,C) should be closer to each
    # other than to a cross-cluster node D.
    same = (sim("A", "B") + sim("B", "C") + sim("A", "C")) / 3.0
    cross = (sim("A", "D") + sim("B", "D") + sim("C", "D")) / 3.0
    assert same > cross


def test_sppmi_shift_zeros_low_pmi():
    # Two nodes co-occur exactly at random => PMI ≈ 0 => SPPMI shift < 0 => zero
    from collections import Counter
    pair = Counter([("A", "B"), ("B", "A")])
    node = Counter({"A": 100, "B": 100})
    ids, M = _build_sppmi(pair, node, n_pairs=2, neg_k=5, min_count=1)
    assert set(ids) == {"A", "B"}
    # AB / (100 * 100) = tiny → PMI is very negative → SPPMI clipped to 0
    assert M[ids.index("A"), ids.index("B")] == 0.0


def test_cooccurrence_symmetric_within_window():
    pair, node, n = _cooccurrence([["A", "B", "C"]], window=2)
    # Each of the 6 unordered ordered pairs shows up once
    assert pair[("A", "B")] == 1 and pair[("B", "A")] == 1
    assert pair[("A", "C")] == 1 and pair[("C", "A")] == 1
    assert pair[("B", "C")] == 1 and pair[("C", "B")] == 1
    assert node["A"] == node["B"] == node["C"] == 1
