"""Test the Reason contract + helpers."""
import pytest

from risk.reasons import Reason, ReasonBand, band_for, dedupe_reasons


def test_band_thresholds():
    assert band_for(0.0) == ReasonBand.LOW
    assert band_for(0.29) == ReasonBand.LOW
    assert band_for(0.30) == ReasonBand.MED
    assert band_for(0.54) == ReasonBand.MED
    assert band_for(0.55) == ReasonBand.HIGH
    assert band_for(0.79) == ReasonBand.HIGH
    assert band_for(0.80) == ReasonBand.CRITICAL
    assert band_for(1.0) == ReasonBand.CRITICAL


def test_reason_to_dict_and_back():
    r = Reason(name="x", weight=0.42, detail="hello",
                evidence={"node_type": "GSTIN", "node_id": "27..."})
    d = r.to_dict()
    assert d == {"name": "x", "weight": 0.42, "detail": "hello",
                    "evidence": {"node_type": "GSTIN", "node_id": "27..."}}
    r2 = Reason.from_dict(d)
    assert r2 == r


def test_with_scorer_computes_contribution():
    r = Reason(name="x", weight=0.5, detail="")
    tagged = r.with_scorer("rules", 0.20)
    assert tagged.scorer == "rules"
    assert tagged.contribution == pytest.approx(0.5 * 0.20, rel=1e-6)
    # to_dict includes scorer + contribution once set
    d = tagged.to_dict()
    assert d["scorer"] == "rules"
    assert d["contribution"] == pytest.approx(0.1, rel=1e-6)


def test_dedupe_reasons_keeps_max_weight():
    a = Reason(name="dup", weight=0.3, detail="A",
                evidence={"node_id": "N1"}, scorer="rules")
    b = Reason(name="dup", weight=0.9, detail="B",
                evidence={"node_id": "N1"}, scorer="rules")
    c = Reason(name="dup", weight=0.7, detail="C",
                evidence={"node_id": "N2"}, scorer="rules")
    out = dedupe_reasons([a, b, c])
    assert len(out) == 2
    # b (higher weight, same key) survives over a
    kept_details = sorted(r.detail for r in out)
    assert kept_details == ["B", "C"]


def test_dedupe_handles_list_node_ids():
    a = Reason(name="dup", weight=0.5, detail="A",
                evidence={"node_id": ["X", "Y"]}, scorer="s")
    b = Reason(name="dup", weight=0.8, detail="B",
                evidence={"node_id": ["X", "Y"]}, scorer="s")
    out = dedupe_reasons([a, b])
    assert len(out) == 1
    assert out[0].detail == "B"
