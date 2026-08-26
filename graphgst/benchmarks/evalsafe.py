"""Evaluation-integrity guards.

The synthetic generator writes planted-label columns into its CSVs so the
data is debuggable (`scenario`, invoice `status = CIRCULAR_FRAUD`, EWB
`phantom`). Those columns MUST NOT reach any scorer/feature — otherwise a
future feature could silently read the answer.

`strip_labels` removes the denylisted columns per record kind BEFORE the
rows are handed to a `ScorerContext`. `assert_label_free` is used by the
guard test to fail loudly if a label token survives.

IMPORTANT: `gstins.status` (Active / CANCELLED) is a LEGITIMATE feature the
RuleScorer uses — it is NOT stripped. Only `gstins.scenario` is. On invoices
and EWBs, `status`/`scenario`/`phantom` are planted tells and ARE stripped.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

# Per-kind label denylist. Anything a scorer could use as a shortcut to the
# planted-ring label.
_DENYLIST: Dict[str, set[str]] = {
    "gstins":   {"scenario"},                     # keep status (CANCELLED is real)
    "invoices": {"scenario", "status"},           # status=CIRCULAR_FRAUD is a label
    "ewb":      {"scenario", "phantom"},          # phantom=True only on ring EWBs
    "pr":       {"scenario"},
    "gstr1":    {"scenario"},
    "gstr3b":   {"scenario"},
    "taxpayments": {"scenario"},
}

# Values that must never appear in a scorer-visible record (label tokens).
_LABEL_VALUE_TOKENS = {"CIRCULAR_TRADING", "CIRCULAR_FRAUD"}


def strip_labels(rows: Iterable[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    """Return copies of `rows` with the label columns for `kind` removed."""
    deny = _DENYLIST.get(kind, set())
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({k: v for k, v in r.items() if k not in deny})
    return out


def assert_label_free(rows: Iterable[Dict[str, Any]], kind: str, where: str = "") -> None:
    """Raise AssertionError if any record still carries a label column or a
    label value token. Used by the guard test."""
    deny = _DENYLIST.get(kind, set())
    for i, r in enumerate(rows):
        leaked_cols = deny & set(r.keys())
        assert not leaked_cols, (
            f"[{where}] {kind} row {i} still carries label column(s) "
            f"{sorted(leaked_cols)}"
        )
        for k, v in r.items():
            if isinstance(v, str) and v in _LABEL_VALUE_TOKENS:
                raise AssertionError(
                    f"[{where}] {kind} row {i} field {k!r} holds label token {v!r}"
                )


def strip_graph_source(gs: Dict[str, Any]) -> Dict[str, Any]:
    """Strip label columns from a benchmark graph_source dict in place-safe
    fashion, returning a new dict. Applies to the record lists a
    ScorerContext consumes: gstins, invoices, pr."""
    out = dict(gs)
    if "gstins" in out:
        out["gstins"] = strip_labels(out["gstins"], "gstins")
    if "invoices" in out:
        out["invoices"] = strip_labels(out["invoices"], "invoices")
    if "pr" in out:
        out["pr"] = strip_labels(out["pr"], "pr")
    return out
