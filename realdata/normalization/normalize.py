"""Normalization helpers shared by adapters and the quality report.

Includes a real-GSTIN format validator. None of the *currently wired* public
datasets carries real GSTINs (Iron Dealers = anonymised integers, AMLworld =
bank accounts), but a future authorized dataset will — the validator lets the
quality report flag malformed GSTINs, and the anonymizer (see anonymize.py)
protects real ones before they ever reach the graph, logs, or UI.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

# A GSTIN is 15 chars: 2-digit state + 10-char PAN + 1 entity char + 'Z' + 1 checksum.
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")


def is_valid_gstin(s: Optional[str]) -> bool:
    """Structural validity of a real GSTIN (shape only, not the checksum digit)."""
    if not s:
        return False
    return bool(_GSTIN_RE.match(str(s).strip().upper()))


def looks_like_real_gstin(s: Optional[str]) -> bool:
    """True if the raw token is plausibly a real 15-char GSTIN (used to decide
    whether anonymization is needed for a source)."""
    return is_valid_gstin(s)


def clean_id(s: Optional[str]) -> str:
    return "" if s is None else str(s).strip()


def parse_amount(v) -> Optional[float]:
    """Coerce to a non-negative float, else None (never fabricate)."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if (f == f and f >= 0) else None   # f==f rejects NaN


def valid_iso_date(s: Optional[str]) -> bool:
    if not s:
        return False
    try:
        date.fromisoformat(str(s)[:10])
        return True
    except (ValueError, TypeError):
        return False
