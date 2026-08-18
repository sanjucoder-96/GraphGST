"""Verify outcome codes and severity mapping."""
from reconcile.outcomes import (AMOUNT_MISMATCH, CANCELLED_SUPPLIER,
                                  CRITICAL, HIGH, INFO, MATCHED, MEDIUM,
                                  MISSING_TAX_PAYMENT, OUTCOMES, Reason,
                                  SEVERITY, severity_for)


def test_outcomes_and_severity_are_consistent():
    # Every canonical outcome has a severity mapping.
    for o in OUTCOMES:
        assert o in SEVERITY, f"missing severity for {o!r}"


def test_severity_for_defaults_medium_for_unknown():
    assert severity_for("SOME_UNKNOWN_OUTCOME") == MEDIUM


def test_specific_severities():
    assert severity_for(MATCHED) == INFO
    assert severity_for(AMOUNT_MISMATCH) == HIGH
    assert severity_for(CANCELLED_SUPPLIER) == CRITICAL
    assert severity_for(MISSING_TAX_PAYMENT) == CRITICAL


def test_reason_to_dict_roundtrip():
    r = Reason(name="taxable-value-delta", weight=0.42, detail="hello",
                evidence={"node_type": "PurchaseRegister", "node_id": "PR-1"})
    d = r.to_dict()
    assert d == {
        "name": "taxable-value-delta",
        "weight": 0.42,
        "detail": "hello",
        "evidence": {"node_type": "PurchaseRegister", "node_id": "PR-1"},
    }
