"""risk — composable risk engine (Phase 4).

Every scorer (rules, rings, reconcile, temporal, ML, propagation) emits a
list of `Reason` objects with a subscore in [0, 1] and a weight. The
`RiskComposer` combines them into one GSTIN-level score plus a flat,
sortable Reason list that the investigator UI renders directly.

Public exports:

    from risk import RiskComposer, ComposerConfig, ScorerContext, Reason
    from risk.scorers import (RuleScorer, RingScorer, ReconcileScorer,
                              TemporalScorer, MLScorer, PropagationScorer)
"""
from .composer import ComposedRisk, ComposerConfig, RiskComposer
from .context import ScorerContext, build_context_from_graph_source
from .reasons import Reason, ReasonBand

__all__ = [
    "ComposedRisk",
    "ComposerConfig",
    "RiskComposer",
    "ScorerContext",
    "build_context_from_graph_source",
    "Reason",
    "ReasonBand",
]
