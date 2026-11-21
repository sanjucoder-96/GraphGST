"""Outcome taxonomy, severity mapping, and the Reason contract.

The outcome codes here are the AUTHORITATIVE canonical strings; they
match the ones used by `datagen.anomalies` so scoring against
`truth.json` is a direct string comparison. If you rename one here,
update the corresponding datagen constant too.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


# ── Canonical outcome codes ────────────────────────────────────────────
MATCHED = "MATCHED"
NEAR_MATCH = "NEAR_MATCH"
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
TAX_MISMATCH = "TAX_MISMATCH"
DATE_MISMATCH = "DATE_MISMATCH"
HSN_MISMATCH = "HSN_MISMATCH"
POS_MISMATCH = "POS_MISMATCH"
MISSING_GSTR1 = "MISSING_GSTR1"
MISSING_GSTR3B = "MISSING_GSTR3B"
MISSING_TAX_PAYMENT = "MISSING_TAX_PAYMENT"
MISSING_IN_PR = "MISSING_IN_PR"
MISSING_EWB = "MISSING_EWB"
DUPLICATE = "DUPLICATE"
NEAR_DUPLICATE = "NEAR_DUPLICATE"
CANCELLED_SUPPLIER = "CANCELLED_SUPPLIER"
INVALID_GSTIN_FORMAT = "INVALID_GSTIN_FORMAT"

OUTCOMES: tuple[str, ...] = (
    MATCHED, NEAR_MATCH, AMOUNT_MISMATCH, TAX_MISMATCH, DATE_MISMATCH,
    HSN_MISMATCH, POS_MISMATCH, MISSING_GSTR1, MISSING_GSTR3B,
    MISSING_TAX_PAYMENT, MISSING_IN_PR, MISSING_EWB, DUPLICATE,
    NEAR_DUPLICATE, CANCELLED_SUPPLIER, INVALID_GSTIN_FORMAT,
)


# ── Severity ranking ───────────────────────────────────────────────────
INFO = "INFO"
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CRITICAL = "CRITICAL"

SEVERITY: dict[str, str] = {
    MATCHED: INFO,
    NEAR_MATCH: LOW,
    AMOUNT_MISMATCH: HIGH,
    TAX_MISMATCH: HIGH,
    DATE_MISMATCH: MEDIUM,
    HSN_MISMATCH: HIGH,
    POS_MISMATCH: MEDIUM,
    MISSING_GSTR1: HIGH,       # buyer's ITC claim blocked u/s 16(2)(aa)
    MISSING_GSTR3B: HIGH,      # supplier tax not declared
    MISSING_TAX_PAYMENT: CRITICAL,  # tax collected, not remitted — Sec 74 risk
    MISSING_IN_PR: HIGH,       # buyer never booked — potential fabrication
    MISSING_EWB: MEDIUM,       # logistics compliance gap
    DUPLICATE: CRITICAL,       # double-claim of ITC
    NEAR_DUPLICATE: MEDIUM,
    CANCELLED_SUPPLIER: CRITICAL,   # invoice from cancelled GSTIN — ITC ineligible
    INVALID_GSTIN_FORMAT: HIGH,
}


def severity_for(outcome: str) -> str:
    """Return severity for an outcome; unknown outcomes → MEDIUM (safe default)."""
    return SEVERITY.get(outcome, MEDIUM)


# ── Reason contract ────────────────────────────────────────────────────
@dataclass
class Reason:
    """A single, cite-able piece of evidence for a MatchEvent.

    Fields
    ------
    name      : short kebab-case identifier ("amount-delta", "supplier-cancelled")
    weight    : contribution to the confidence of the outcome ∈ [0, 1]
    detail    : human-readable one-liner rendered in the UI Reason chip
    evidence  : dict pointing at the exact cited node(s) so the UI can
                highlight the subgraph. Keys we use:
                  {"node_type": "Invoice", "node_id": "INV-...",
                   "path": "GSTIN→ISSUED_INVOICE→Invoice"}
                It's a dict, not a full graph edge list, because the
                MatchEvent already links to invoice/gstins as first-class
                fields — Reasons just point at supporting context.
    """
    name: str
    weight: float
    detail: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
