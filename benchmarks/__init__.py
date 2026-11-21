"""benchmarks — unified measurement harness for Graph GST.

Every algorithmic claim in the project (ring detection F1,
reconciliation micro-F1, risk-composer ROC-AUC, lookalike hit@10) is
produced by a bench in this package. `run_all` runs them all on ONE
shared synthetic dataset, emits `benchmarks/latest.json`, and compares
against `benchmarks/baseline.json` with regression tolerances.
"""
from .compare import HEADLINE_METRICS, compare_reports, format_diff_table
from .run_all import METRICS_SCHEMA_VERSION, run_all

__all__ = [
    "run_all",
    "METRICS_SCHEMA_VERSION",
    "HEADLINE_METRICS",
    "compare_reports",
    "format_diff_table",
]
