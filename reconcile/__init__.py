"""reconcile — Graph-native reconciliation engine (Phase 2).

Produces first-class `MatchEvent` records for every invoice in the
graph. Each event carries an outcome from the full taxonomy
(`outcomes.OUTCOMES`), a severity, a signed delta (where numeric), and
a `Reason[]` list pointing at the exact evidence nodes that support the
classification.

Engine is Neo4j-optional: pass a `graph_source` dict for in-memory
processing (used by tests and benchmarks against Phase 1 truth.json),
or omit it to pull live from the graph via `db.run_query`.

The Reason schema is deliberately shared with rings/ (Phase 3) and will
be reused by the composable risk engine (Phase 4).
"""
from .engine import MatchEvent, ReconcileConfig, run_reconcile
from .fuzzy import (amount_close, date_close, invoice_id_match,
                    jaro_winkler, normalize_id)
from .outcomes import (OUTCOMES, SEVERITY, Reason, severity_for)

__all__ = [
    "MatchEvent",
    "ReconcileConfig",
    "run_reconcile",
    "amount_close",
    "date_close",
    "invoice_id_match",
    "jaro_winkler",
    "normalize_id",
    "OUTCOMES",
    "SEVERITY",
    "Reason",
    "severity_for",
]
