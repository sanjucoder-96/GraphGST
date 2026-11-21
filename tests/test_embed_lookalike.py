"""Tests for the LookalikeIndex + persistence roundtrip."""
from __future__ import annotations

import os
import tempfile

import numpy as np

from embed.lookalike import LookalikeIndex, lookalike
from embed.persist import load_index, save_index
from embed.train import EmbedConfig, EmbedModel


def _fixture_index() -> LookalikeIndex:
    # Three unit vectors in 3D
    ids = ["A", "B", "C"]
    m = np.array([
        [1.0, 0.0, 0.0],   # A
        [0.99, 0.0, 0.14],  # B — very close to A
        [0.0, 0.0, 1.0],   # C — orthogonal to A
    ], dtype=np.float32)
    # normalize
    m = m / np.linalg.norm(m, axis=1, keepdims=True)
    return LookalikeIndex(ids=ids, matrix=m)


def test_similar_to_excludes_self():
    idx = _fixture_index()
    hits = idx.similar_to("A", k=3)
    ids = [g for g, _ in hits]
    assert "A" not in ids


def test_similar_to_orders_by_similarity():
    idx = _fixture_index()
    hits = idx.similar_to("A", k=2)
    # B closer to A than C
    assert [g for g, _ in hits] == ["B", "C"]
    assert hits[0][1] > hits[1][1]


def test_similar_to_unknown_returns_empty():
    idx = _fixture_index()
    assert idx.similar_to("Z", k=5) == []


def test_similar_to_respects_exclude():
    idx = _fixture_index()
    hits = idx.similar_to("A", k=5, exclude=["B"])
    assert [g for g, _ in hits] == ["C"]


def test_lookalike_convenience_accepts_model_or_index():
    idx = _fixture_index()
    model = EmbedModel(ids=idx.ids, matrix=idx.matrix, config=EmbedConfig(dim=3))
    a = lookalike(model, "A", k=2)
    b = lookalike(idx, "A", k=2)
    assert [g for g, _ in a] == [g for g, _ in b]


def test_persist_roundtrip():
    idx = _fixture_index()
    model = EmbedModel(ids=idx.ids, matrix=idx.matrix, config=EmbedConfig(dim=3),
                        stats={"n_nodes": 3})
    with tempfile.TemporaryDirectory() as d:
        saved = save_index(model, artifact_dir=d)
        assert os.path.exists(saved["npy"])
        loaded = load_index(artifact_dir=d)
        assert loaded is not None
        assert loaded.ids == idx.ids
        assert np.allclose(loaded.matrix, idx.matrix, atol=1e-6)
