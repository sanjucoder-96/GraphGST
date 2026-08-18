"""Persist embeddings + node ids to disk. .npy for the matrix, .json for
the id ordering + config + training stats."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from .lookalike import LookalikeIndex
from .train import EmbedConfig, EmbedModel

DEFAULT_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "embed_artifacts")


def _paths(artifact_dir: str) -> tuple[str, str]:
    os.makedirs(artifact_dir, exist_ok=True)
    return (os.path.join(artifact_dir, "embeddings.npy"),
             os.path.join(artifact_dir, "embeddings.meta.json"))


def save_index(model: EmbedModel, artifact_dir: str = DEFAULT_ARTIFACT_DIR) -> dict:
    npy_path, meta_path = _paths(artifact_dir)
    np.save(npy_path, model.matrix)
    meta = {
        "ids": model.ids,
        "config": asdict(model.config),
        "stats": model.stats,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "shape": list(model.matrix.shape),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return {"npy": npy_path, "meta": meta_path, "shape": meta["shape"]}


def load_index(artifact_dir: str = DEFAULT_ARTIFACT_DIR) -> Optional[LookalikeIndex]:
    npy_path, meta_path = _paths(artifact_dir)
    if not (os.path.exists(npy_path) and os.path.exists(meta_path)):
        return None
    matrix = np.load(npy_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return LookalikeIndex(ids=list(meta["ids"]), matrix=matrix)


def load_meta(artifact_dir: str = DEFAULT_ARTIFACT_DIR) -> Optional[dict]:
    _, meta_path = _paths(artifact_dir)
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)
