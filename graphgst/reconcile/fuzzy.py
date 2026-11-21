"""Fuzzy matchers for invoice IDs, amounts, dates, and HSN.

These are the "cheap fixes" that stop the reconciliation engine from
reporting `MISSING_IN_PR` when the buyer merely wrote `INV/2024/001`
instead of `INV-2024-001`, or `100.00` instead of `100`. Real ERPs
disagree constantly on formatting.

Every threshold is documented in-line; every function is pure (no I/O)
and deterministic (no time-of-day tolerance) so tests can pin values.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from typing import Optional, Union

_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")


def normalize_id(s: str) -> str:
    """Strip punctuation, uppercase — good enough for invoice IDs."""
    if s is None:
        return ""
    return _NON_ALNUM_RE.sub("", str(s)).upper()


# ── Jaro / Jaro-Winkler ─────────────────────────────────────────────────
def _jaro(a: str, b: str) -> float:
    """Pure-Python Jaro similarity ∈ [0, 1]."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    window = max(la, lb) // 2 - 1
    if window < 0:
        window = 0

    matched_a = [False] * la
    matched_b = [False] * lb
    matches = 0
    for i, ca in enumerate(a):
        j0 = max(0, i - window)
        j1 = min(lb, i + window + 1)
        for j in range(j0, j1):
            if matched_b[j]:
                continue
            if b[j] != ca:
                continue
            matched_a[i] = True
            matched_b[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    # transpositions
    t = 0
    k = 0
    for i in range(la):
        if not matched_a[i]:
            continue
        while not matched_b[k]:
            k += 1
        if a[i] != b[k]:
            t += 1
        k += 1
    t = t // 2
    return (matches / la + matches / lb + (matches - t) / matches) / 3


def jaro_winkler(a: str, b: str, p: float = 0.1, max_prefix: int = 4) -> float:
    """Jaro-Winkler ∈ [0, 1]. p=0.1 (Winkler's default), prefix cap 4.

    Winkler boosts matches that agree on the first few characters; that's
    exactly the invoice-id case ("INV-2024-001" vs "INV/2024/001").
    """
    if a is None or b is None:
        return 0.0
    a, b = str(a), str(b)
    j = _jaro(a, b)
    if j == 0:
        return 0.0
    prefix = 0
    for i in range(min(max_prefix, len(a), len(b))):
        if a[i] == b[i]:
            prefix += 1
        else:
            break
    return j + prefix * p * (1 - j)


_ALPHA_RE = re.compile(r"[A-Z]+")
_DIGIT_RE = re.compile(r"[0-9]+")


def invoice_id_match(a: str, b: str, threshold: float = 0.90) -> bool:
    """True iff the two invoice-ids look like the same one modulo punctuation.

    Two-stage check: after normalization (strip non-alphanumerics, upper),
    the DIGIT runs must be identical AND Jaro-Winkler must clear the
    threshold. That way "INV-2024-001" == "INV/2024/001" (punctuation only)
    but "INV-2024-001" ≠ "INV-2024-002" (numeric-different — near-JW score
    would otherwise mask this).
    """
    if not a or not b:
        return False
    na = normalize_id(a); nb = normalize_id(b)
    if na == nb:
        return True
    # Digit sequences must line up exactly — sequential numbering matters.
    if _DIGIT_RE.findall(na) != _DIGIT_RE.findall(nb):
        return False
    return jaro_winkler(na, nb) >= threshold


# ── Numeric tolerance ────────────────────────────────────────────────
def amount_close(
    a: Optional[float], b: Optional[float],
    abs_tol: float = 1.0, rel_tol: float = 0.001,
) -> bool:
    """|a - b| ≤ max(abs_tol, rel_tol * max(|a|, |b|))?

    Defaults: rupee-level rounding tolerance (±₹1) OR ±0.1 % of the
    larger side, whichever is greater. That covers percentage-rounding
    on large invoices and paise-level rounding on small ones.
    """
    if a is None or b is None:
        return False
    a = float(a); b = float(b)
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def relative_delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Signed relative delta (a - b) / max(|a|, |b|), or None if ill-defined."""
    if a is None or b is None:
        return None
    a = float(a); b = float(b)
    denom = max(abs(a), abs(b))
    if denom == 0:
        return 0.0
    return (a - b) / denom


# ── Date tolerance ───────────────────────────────────────────────────
def _as_date(x: Union[str, date, datetime, None]) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    try:
        return date.fromisoformat(str(x))
    except (ValueError, TypeError):
        return None


def date_close(
    a: Union[str, date, datetime, None], b: Union[str, date, datetime, None],
    days_tol: int = 3,
) -> bool:
    """True iff both dates parse and differ by ≤ days_tol days."""
    da = _as_date(a); db = _as_date(b)
    if da is None or db is None:
        return False
    return abs((da - db).days) <= days_tol


def date_delta_days(
    a: Union[str, date, datetime, None], b: Union[str, date, datetime, None]
) -> Optional[int]:
    """Signed day difference (a - b), or None if either can't parse."""
    da = _as_date(a); db = _as_date(b)
    if da is None or db is None:
        return None
    return (da - db).days


# ── GSTIN format check ──────────────────────────────────────────────
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")


def is_valid_gstin(gstin: str) -> bool:
    """Shape-check only (15 chars, state-code + PAN + entity + Z + check).
    Does NOT verify the mod-36 checksum against the portal."""
    return bool(gstin and _GSTIN_RE.match(str(gstin)))
