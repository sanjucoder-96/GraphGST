"""Temporal-window filter + invoice-tuple materialisation.

Johnson gives us cycles as MEMBER tuples. Each hop (src, dst) may have
several invoices between those two GSTINs; the temporal filter picks
ONE invoice per hop such that all k chosen invoices fit inside
`window_days`. If no combination fits, the cycle is dropped.

Algorithm: enumerate combinations for small option-products, else fall
back to a greedy median-anchor pick. The greedy sort is None-safe:
dates missing on some edges no longer crash the whole pass.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from itertools import product
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def group_edges_by_pair(edges: Iterable[dict]) -> Dict[Tuple[str, str], List[dict]]:
    buckets: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for e in edges:
        buckets[(e["src"], e["dst"])].append(e)
    return dict(buckets)


def _date_span_days(edges: Sequence[dict]) -> int:
    dates = [e["date"] for e in edges if e.get("date") is not None]
    if not dates:
        return 0
    return (max(dates) - min(dates)).days


def _none_safe_date_key(edge: dict):
    """Sort key that lets edges with missing dates coexist with real dates.

    Python 3 raises TypeError on `None < date(...)`; we push None to the
    end by comparing a boolean first.
    """
    d = edge.get("date")
    return (d is None, d)


def _pick_best_combination(
    options: Sequence[Sequence[dict]], window_days: int, combo_cap: int = 2048
) -> Optional[List[dict]]:
    total = 1
    for o in options:
        if not o:
            return None
        total *= len(o)
    if total <= combo_cap:
        best: Optional[List[dict]] = None
        best_span: Optional[int] = None
        for combo in product(*options):
            span = _date_span_days(combo)
            if span > window_days:
                continue
            if best_span is None or span < best_span:
                best = list(combo); best_span = span
        return best
    # Greedy median-anchor fallback. None-safe sort — some edges may
    # lack invoice_date; we push them to the end and skip them for the
    # median pick when we can.
    anchors: List[dict] = []
    for o in options:
        dated = sorted(o, key=_none_safe_date_key)
        # Prefer an edge with a real date at the median position; if
        # all edges lack dates we fall through and use whatever's there.
        anchors.append(dated[len(dated) // 2])
    span = _date_span_days(anchors)
    if span <= window_days:
        return anchors
    return None


def materialize_and_filter(
    cycles: Iterable[Sequence[str]],
    edges_by_pair: Dict[Tuple[str, str], List[dict]],
    window_days: int = 30,
) -> List[dict]:
    results: List[dict] = []
    for cycle in cycles:
        cycle = tuple(cycle)
        k = len(cycle)
        pairs = [(cycle[i], cycle[(i + 1) % k]) for i in range(k)]
        options = [edges_by_pair.get(p, []) for p in pairs]
        if any(not o for o in options):
            continue
        best = _pick_best_combination(options, window_days=window_days)
        if best is None:
            continue
        results.append(
            {
                "members": cycle,
                "edges": best,
                "date_span_days": _date_span_days(best),
            }
        )
    return results
