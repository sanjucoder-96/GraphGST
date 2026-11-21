"""embed — graph-native GSTIN embeddings + vendor lookalike (Phase 5).

Turns the invoice-projection graph into per-GSTIN dense vectors via
random walks + PMI-SVD (a Levy-Goldberg-style implicit factorization
that produces node2vec-quality embeddings in pure numpy — no gensim, no
torch, no external service).

Once trained, the `LookalikeIndex` returns cosine-k-NN neighbours in
constant time per query. The Investigator UI (Phase 6) can render a
"Related Vendors" strip via `GET /api/embed/lookalike/{gstin_id}`.
"""
from .lookalike import LookalikeIndex, lookalike
from .persist import DEFAULT_ARTIFACT_DIR, load_index, save_index
from .train import EmbedConfig, EmbedModel, train
from .walks import biased_walks, build_adjacency

__all__ = [
    "LookalikeIndex",
    "lookalike",
    "EmbedConfig",
    "EmbedModel",
    "train",
    "biased_walks",
    "build_adjacency",
    "load_index",
    "save_index",
    "DEFAULT_ARTIFACT_DIR",
]
