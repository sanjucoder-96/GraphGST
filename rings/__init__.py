"""Circular Trading Intelligence Engine — Phase 3.

Composable ring-detection pipeline. Import the top-level orchestrator:

    from rings.engine import run_pipeline, EngineConfig

Each stage is also usable standalone; see the individual modules.
"""
from .canonical import canonicalize, ring_id, dedup_cycles
from .engine import EngineConfig, run_pipeline, DetectedRing

__all__ = [
    "canonicalize",
    "ring_id",
    "dedup_cycles",
    "EngineConfig",
    "run_pipeline",
    "DetectedRing",
]
