"""Regression-comparator tests."""
from __future__ import annotations

import pytest

from benchmarks.compare import HEADLINE_METRICS, compare_reports, format_diff_table


def _report(**headlines):
    return {"headlines": {k: float(v) for k, v in headlines.items()},
             "git_commit": "abc"}


def test_no_baseline_marks_all_new():
    cur = _report(**{k: 0.9 for k in HEADLINE_METRICS})
    diff = compare_reports(None, cur, tolerance_abs=0.02)
    assert diff["ok"] is True
    assert {row["status"] for row in diff["rows"]} == {"NEW"}


def test_within_tolerance_is_unchanged_and_passes():
    base = _report(**{"ring.average_precision": 0.90, "reconcile.micro_f1": 0.95,
                        "reconcile.micro_precision": 0.90,
                        "reconcile.micro_recall": 0.99,
                        "risk.roc_auc": 0.90,
                        "risk.precision_at_50": 0.30,
                        "risk.precision_at_100": 0.25,
                        "embed.hit_at_10": 0.90,
                        "embed.cohesion_recall_at_10": 0.75})
    cur = _report(**{"ring.average_precision": 0.905, "reconcile.micro_f1": 0.948,
                       "reconcile.micro_precision": 0.905,
                       "reconcile.micro_recall": 0.985,
                       "risk.roc_auc": 0.91,
                       "risk.precision_at_50": 0.31,
                       "risk.precision_at_100": 0.24,
                       "embed.hit_at_10": 0.895,
                       "embed.cohesion_recall_at_10": 0.76})
    diff = compare_reports(base, cur, tolerance_abs=0.02)
    assert diff["ok"] is True
    statuses = {row["status"] for row in diff["rows"] if row["status"] != "INFO"}
    assert "REGRESSED" not in statuses
    assert "MISSING" not in statuses


def test_regression_beyond_tolerance_fails():
    base = _report(**{"ring.average_precision": 0.90})
    cur = _report(**{"ring.average_precision": 0.85})    # −0.05 > tolerance 0.02
    diff = compare_reports(base, cur, tolerance_abs=0.02)
    assert diff["ok"] is False
    ring_row = next(r for r in diff["rows"] if r["metric"] == "ring.average_precision")
    assert ring_row["status"] == "REGRESSED"
    assert ring_row["delta"] == pytest.approx(-0.05, abs=1e-6)


def test_improvement_beyond_tolerance_flagged_improved_but_still_passes():
    base = _report(**{"ring.average_precision": 0.90})
    cur = _report(**{"ring.average_precision": 0.95})
    diff = compare_reports(base, cur, tolerance_abs=0.02)
    assert diff["ok"] is True
    row = next(r for r in diff["rows"] if r["metric"] == "ring.average_precision")
    assert row["status"] == "IMPROVED"


def test_missing_metric_fails_run():
    base = _report(**{"ring.average_precision": 0.90})
    cur = _report()  # metric disappeared
    diff = compare_reports(base, cur, tolerance_abs=0.02)
    assert diff["ok"] is False
    row = next(r for r in diff["rows"] if r["metric"] == "ring.average_precision")
    assert row["status"] == "MISSING"


def test_extras_reported_as_info_only():
    cur = _report(**{"ring.average_precision": 0.9})
    cur["headlines"]["extra.metric.foo"] = 42.0
    diff = compare_reports(None, cur, tolerance_abs=0.02)
    extra = next(r for r in diff["rows"] if r["metric"] == "extra.metric.foo")
    assert extra["status"] == "INFO"
    assert diff["ok"] is True    # INFO metrics don't gate


def test_format_diff_table_produces_pass_or_fail_footer():
    diff = compare_reports(None, _report(**{"ring.average_precision": 0.9}), tolerance_abs=0.02)
    out = format_diff_table(diff)
    assert "ring.average_precision" in out
    assert "PASS" in out


def test_format_diff_table_fail_footer_on_regression():
    diff = compare_reports(_report(**{"ring.average_precision": 0.9}),
                             _report(**{"ring.average_precision": 0.5}),
                             tolerance_abs=0.02)
    out = format_diff_table(diff)
    assert "FAIL" in out
    assert "REGRESSED" in out
