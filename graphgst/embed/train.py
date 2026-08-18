"""Learn dense per-GSTIN vectors from a corpus of random walks.

Method: PMI-SVD.  Levy & Goldberg (2014) showed that Skip-Gram with
Negative Sampling (the objective node2vec/DeepWalk optimise) is an
implicit factorisation of the shifted Pointwise Mutual Information
matrix:

    SPPMI(w, c) = max(0, log( P(w, c) / (P(w) · P(c)) ) − log k)

where `k` is the negative-sampling ratio. Truncated SVD of SPPMI gives
node2vec-equivalent vectors in pure numpy — no gensim, no torch.

Complexity: O(V · dim²) for the top-`dim` SVD, O(V · window · walks)
for co-occurrence counting. For our benchmark scale (V ≤ 10 000)
training finishes in well under a second.
"""
from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from .walks import Neighbours, biased_walks, build_adjacency

logger = logging.getLogger(__name__)


@dataclass
class EmbedConfig:
    dim: int = 64
    walks_per_node: int = 10
    walk_len: int = 20
    window: int = 5
    neg_k: int = 5           # SPPMI shift parameter
    p: float = 1.0
    q: float = 1.0
    seed: int = 42
    min_count: int = 1       # drop nodes seen < min_count times in the corpus
    amount_kicker: float = 0.0001


@dataclass
class EmbedModel:
    ids: List[str]                      # node ordering (matrix row index)
    matrix: np.ndarray                  # shape (N, dim); L2-normalized
    config: EmbedConfig
    stats: Dict[str, Any] = field(default_factory=dict)

    def id_to_index(self) -> Dict[str, int]:
        return {gid: i for i, gid in enumerate(self.ids)}


def _cooccurrence(
    walks: Sequence[Sequence[str]], window: int
) -> tuple[Counter, Counter, int]:
    """Symmetric co-occurrence counts. Returns (pair_counts, node_counts, N_pairs)."""
    pair: Counter = Counter()
    node: Counter = Counter()
    n_pairs = 0
    for walk in walks:
        L = len(walk)
        for i in range(L):
            w = walk[i]
            node[w] += 1
            lo = max(0, i - window)
            hi = min(L, i + window + 1)
            for j in range(lo, hi):
                if i == j:
                    continue
                c = walk[j]
                pair[(w, c)] += 1
                n_pairs += 1
    return pair, node, n_pairs


def _build_sppmi(
    pair: Counter, node: Counter, n_pairs: int, neg_k: int, min_count: int
) -> tuple[List[str], np.ndarray]:
    ids = [w for w, c in node.items() if c >= min_count]
    ids.sort()
    idx = {w: i for i, w in enumerate(ids)}
    V = len(ids)
    if V == 0:
        return [], np.zeros((0, 0), dtype=np.float32)
    total_words = sum(node[w] for w in ids)
    log_k = math.log(max(1, neg_k))
    log_total = math.log(max(1, total_words))
    M = np.zeros((V, V), dtype=np.float32)
    for (w, c), n in pair.items():
        if w not in idx or c not in idx:
            continue
        # PMI = log[ P(w,c) / P(w)P(c) ]
        #     = log[ n · total_words / (node[w] · node[c]) ]  (using pair counts)
        pmi = math.log(n) + log_total - math.log(node[w]) - math.log(node[c])
        sppmi = pmi - log_k
        if sppmi > 0:
            M[idx[w], idx[c]] = sppmi
    return ids, M


def _truncated_svd(M: np.ndarray, dim: int, seed: int = 42) -> np.ndarray:
    V = M.shape[0]
    if V == 0:
        return np.zeros((0, dim), dtype=np.float32)
    dim = int(min(dim, V - 1)) if V >= 2 else 1
    # Deterministic randomised SVD for speed. For V ≤ 5000 this is a
    # rounding error, but caps memory nicely at larger scale.
    try:
        from numpy.linalg import svd
        U, s, _Vt = svd(M, full_matrices=False)
        vecs = U[:, :dim] * np.sqrt(s[:dim])
    except Exception:
        logger.exception("SVD failed; falling back to random projection")
        rng = np.random.default_rng(seed)
        R = rng.standard_normal((V, dim)).astype(np.float32)
        vecs = M @ R
    # L2-normalize so cosine sim = dot product
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms > 0, norms, 1.0)
    return (vecs / norms).astype(np.float32)


def train(
    graph_source: Optional[Mapping[str, Any]] = None,
    neighbours: Optional[Neighbours] = None,
    config: Optional[EmbedConfig] = None,
) -> EmbedModel:
    """Train an embedding model. Give it either a `graph_source` dict (an
    `edges` key like rings.engine expects) or a pre-built `neighbours`
    dict. Returns an `EmbedModel` with L2-normalized rows."""
    cfg = config or EmbedConfig()
    if neighbours is None:
        edges = list((graph_source or {}).get("edges") or [])
        neighbours = build_adjacency(edges, amount_kicker=cfg.amount_kicker)
    if not neighbours:
        return EmbedModel(ids=[], matrix=np.zeros((0, cfg.dim), dtype=np.float32),
                            config=cfg, stats={"n_nodes": 0, "n_walks": 0})

    walks = biased_walks(
        neighbours, num_walks=cfg.walks_per_node, walk_len=cfg.walk_len,
        p=cfg.p, q=cfg.q, seed=cfg.seed,
    )
    pair, node, n_pairs = _cooccurrence(walks, window=cfg.window)
    ids, M = _build_sppmi(pair, node, n_pairs, neg_k=cfg.neg_k,
                            min_count=cfg.min_count)
    vecs = _truncated_svd(M, cfg.dim, seed=cfg.seed)
    return EmbedModel(
        ids=ids, matrix=vecs, config=cfg,
        stats={
            "n_nodes": len(neighbours),
            "n_indexed": len(ids),
            "n_walks": len(walks),
            "n_pairs": n_pairs,
            "sppmi_density": float((M > 0).mean()) if M.size else 0.0,
        },
    )
