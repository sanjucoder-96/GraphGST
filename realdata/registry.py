"""Adapter registry — maps a dataset name to its adapter module."""
from __future__ import annotations

from typing import Optional

from .schemas.canonical import CanonicalDataset

ADAPTERS = {
    "iron_dealers": "realdata.adapters.iron_dealers",
    "ibm_aml": "realdata.adapters.ibm_aml",
}


def load_dataset(name: str, limit: Optional[int] = None) -> CanonicalDataset:
    if name not in ADAPTERS:
        raise SystemExit(f"unknown dataset '{name}'. Known: {', '.join(ADAPTERS)}")
    import importlib
    mod = importlib.import_module(ADAPTERS[name])
    return mod.load(limit=limit)
