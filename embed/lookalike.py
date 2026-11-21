"""Cosine k-NN over trained embeddings.

`LookalikeIndex` wraps a normalized matrix and returns top-K similar
GSTINs for a query in O(V · dim) per call — fine for V ≤ 50 000. When
scale demands it, swap in FAISS behind the same interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

import numpy as np


@dataclass
class LookalikeIndex:
    ids: List[str]
    matrix: np.ndarray            # (V, dim); expected to be L2-normalized
    id_to_idx: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id_to_idx:
            self.id_to_idx = {gid: i for i, gid in enumerate(self.ids)}

    def similar_to(
        self, gstin_id: str, k: int = 5,
        exclude: Sequence[str] = (),
    ) -> List[Tuple[str, float]]:
        idx = self.id_to_idx.get(gstin_id)
        if idx is None or self.matrix.shape[0] == 0:
            return []
        # rows are unit-length → dot product = cosine similarity
        sims = self.matrix @ self.matrix[idx]
        excluded = set(exclude) | {gstin_id}
        # Argpartition top-(k + |excluded|), then argsort just that head.
        overflow = k + len(excluded) + 1
        overflow = min(overflow, len(sims))
        top_idx = np.argpartition(-sims, overflow - 1)[:overflow]
        top_sorted = top_idx[np.argsort(-sims[top_idx])]
        out: List[Tuple[str, float]] = []
        for i in top_sorted:
            gid = self.ids[int(i)]
            if gid in excluded:
                continue
            out.append((gid, float(sims[int(i)])))
            if len(out) >= k:
                break
        return out


def lookalike(
    model_or_index, gstin_id: str, k: int = 5,
    exclude: Sequence[str] = (),
) -> List[Tuple[str, float]]:
    """Convenience wrapper: accepts either an `EmbedModel` or a
    `LookalikeIndex`."""
    if isinstance(model_or_index, LookalikeIndex):
        return model_or_index.similar_to(gstin_id, k=k, exclude=exclude)
    # duck-typed EmbedModel
    idx = LookalikeIndex(ids=list(model_or_index.ids),
                            matrix=np.asarray(model_or_index.matrix))
    return idx.similar_to(gstin_id, k=k, exclude=exclude)
