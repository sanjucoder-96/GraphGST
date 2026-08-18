"""Compare a fresh bench report against a stored baseline.

We report each headline metric with the baseline value, the new value,
the absolute delta, and a status:
    IMPROVED          new > baseline + tolerance
    UNCHANGED         |delta| <= tolerance
    REGRESSED         new < baseline - tolerance
    NEW               metric present now but not in baseline
    MISSING           metric present in baseline but not now

The overall run passes iff zero metrics are REGRESSED or MISSING.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Metrics used to gate the run. Adding a metric here means CI will fail
# if it regresses beyond tolerance. Keep this list tight — headline
# claims only. Everything else lives inside `benches/*/report`.
HEADLINE_METRICS: List[str] = [
    "ring.recall",
    "reconcile.micro_f1",
    "reconcile.micro_precision",
    "reconcile.micro_recall",
    "risk.roc_auc",
    "risk.precision_at_50",
    "risk.precision_at_100",
    "embed.hit_at_10",
    "embed.cohesion_recall_at_10",
]


def compare_reports(
    baseline: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    tolerance_abs: float = 0.02,
) -> Dict[str, Any]:
    """Return a structured comparison.

    `ok` is True iff zero REGRESSED / MISSING metrics.
    """
    base_headlines = (baseline or {}).get("headlines") or {}
    cur_headlines = current.get("headlines") or {}

    rows: List[Dict[str, Any]] = []
    ok = True
    for metric in HEADLINE_METRICS:
        b = base_headlines.get(metric)
        c = cur_headlines.get(metric)
        if b is None and c is None:
            continue
        if b is None:
            rows.append({"metric": metric, "baseline": None, "current": c,
                            "delta": None, "status": "NEW"})
            continue
        if c is None:
            rows.append({"metric": metric, "baseline": b, "current": None,
                            "delta": None, "status": "MISSING"})
            ok = False
            continue
        delta = float(c) - float(b)
        if delta > tolerance_abs:
            status = "IMPROVED"
        elif delta < -tolerance_abs:
            status = "REGRESSED"
            ok = False
        else:
            status = "UNCHANGED"
        rows.append({
            "metric": metric,
            "baseline": round(float(b), 4),
            "current": round(float(c), 4),
            "delta": round(delta, 4),
            "status": status,
        })
    # Metrics in current that aren't in HEADLINE_METRICS aren't gated but
    # still reported as informational.
    extras = sorted(set(cur_headlines) - set(HEADLINE_METRICS))
    for metric in extras:
        rows.append({"metric": metric, "baseline": None,
                        "current": float(cur_headlines[metric]),
                        "delta": None, "status": "INFO"})

    return {
        "ok": ok,
        "tolerance_abs": tolerance_abs,
        "baseline_git_commit": (baseline or {}).get("git_commit"),
        "current_git_commit": current.get("git_commit"),
        "rows": rows,
    }


def format_diff_table(diff: Dict[str, Any]) -> str:
    """Pretty-print the diff as a monospace table."""
    lines: List[str] = []
    lines.append(f"{'metric':32s}  {'baseline':>10s}  {'current':>10s}  "
                    f"{'delta':>10s}  status")
    lines.append("-" * 82)
    def _fmt(v):
        return "-" if v is None else f"{float(v):>10.4f}"
    for row in diff["rows"]:
        lines.append(
            f"{row['metric']:32s}  {_fmt(row['baseline'])}  "
            f"{_fmt(row['current'])}  {_fmt(row['delta'])}  {row['status']}"
        )
    lines.append("-" * 82)
    status = "PASS" if diff["ok"] else "FAIL"
    lines.append(f"overall: {status}  (tolerance ±{diff['tolerance_abs']})")
    return "\n".join(lines)
