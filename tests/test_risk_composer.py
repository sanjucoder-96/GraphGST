"""End-to-end composer tests using hand-crafted scorers.

Verifies weight normalization, contribution attribution, deduplication,
graceful handling of a scorer that raises, and stable sort order.
"""
from __future__ import annotations

from typing import List

import pytest

from risk.composer import ComposedRisk, ComposerConfig, RiskComposer
from risk.context import ScorerContext
from risk.reasons import Reason
from risk.scorers.base import Scorer, ScorerResult


class _FixedScorer:
    """Scorer stub that returns a canned subscore + reasons regardless of GSTIN."""
    def __init__(self, name: str, weight: float, subscore: float, reasons: List[Reason]):
        self.name = name
        self.weight = weight
        self._sub = subscore
        self._reasons = reasons

    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        return ScorerResult(subscore=self._sub, reasons=list(self._reasons))


class _RaisingScorer:
    name = "boom"
    weight = 1.0
    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        raise RuntimeError("intentional")


@pytest.fixture
def ctx() -> ScorerContext:
    return ScorerContext(gstins=[{"gstin_id": "G1"}, {"gstin_id": "G2"}])


def test_normalized_weights_sum_to_one():
    cfg = ComposerConfig(scorers=[
        _FixedScorer("a", 0.4, 0.5, []),
        _FixedScorer("b", 0.6, 0.5, []),
        _FixedScorer("c", 0.0, 0.5, []),
    ])
    w = cfg.normalized_weights()
    assert w == {"a": 0.4, "b": 0.6, "c": 0.0}
    assert pytest.approx(sum(w.values())) == 1.0


def test_compose_computes_weighted_score(ctx: ScorerContext):
    comp = RiskComposer(ComposerConfig(scorers=[
        _FixedScorer("a", 1.0, 0.5, [Reason(name="ra", weight=0.5, detail="")]),
        _FixedScorer("b", 3.0, 1.0, [Reason(name="rb", weight=0.9, detail="")]),
    ]))
    r = comp.compose("G1", ctx)
    # Normalized weights: a=0.25, b=0.75. score = 0.5*0.25 + 1.0*0.75 = 0.875
    assert r.score == pytest.approx(0.875, abs=1e-3)
    assert r.contributions == {"a": pytest.approx(0.125, abs=1e-3),
                                 "b": pytest.approx(0.75, abs=1e-3)}
    assert r.band == "CRITICAL"


def test_reasons_are_tagged_and_sorted(ctx: ScorerContext):
    comp = RiskComposer(ComposerConfig(scorers=[
        _FixedScorer("a", 1.0, 0.5, [Reason(name="ra", weight=0.2, detail="A")]),
        _FixedScorer("b", 1.0, 0.5, [Reason(name="rb", weight=0.9, detail="B")]),
    ]))
    r = comp.compose("G1", ctx)
    # rb higher contribution (0.9 * 0.5 = 0.45 vs ra 0.2 * 0.5 = 0.10)
    assert [x["name"] for x in r.reasons] == ["rb", "ra"]
    assert r.reasons[0]["scorer"] == "b"
    assert r.reasons[0]["contribution"] == pytest.approx(0.45, abs=1e-3)


def test_clamps_subscore_out_of_range(ctx: ScorerContext):
    comp = RiskComposer(ComposerConfig(scorers=[
        _FixedScorer("hi", 1.0, 5.0, []),  # subscore >1 must clamp
        _FixedScorer("lo", 1.0, -3.0, []),  # subscore <0 must clamp
    ]))
    r = comp.compose("G1", ctx)
    # hi clamps to 1, lo clamps to 0 → score = 0.5*1 + 0.5*0 = 0.5
    assert r.score == pytest.approx(0.5, abs=1e-3)


def test_scorer_exception_is_swallowed(ctx: ScorerContext):
    comp = RiskComposer(ComposerConfig(scorers=[
        _FixedScorer("good", 1.0, 0.7, [Reason(name="r", weight=0.7, detail="")]),
        _RaisingScorer(),
    ]))
    r = comp.compose("G1", ctx)
    # good contributes 0.7 * 0.5 = 0.35; boom logs and contributes 0
    assert r.score == pytest.approx(0.35, abs=1e-3)
    assert "boom" in r.scorers_run
    assert "boom" not in r.scorers_fired


def test_compose_all_returns_sorted(ctx: ScorerContext):
    # Two entities: G1 gets a big reason for scorer a, G2 gets nothing.
    class _Selective:
        name = "sel"; weight = 1.0
        def score(self, gid: str, ctx: ScorerContext) -> ScorerResult:
            if gid == "G1":
                return ScorerResult(subscore=0.9, reasons=[Reason(name="x", weight=0.9, detail="")])
            return ScorerResult(subscore=0.1, reasons=[])
    comp = RiskComposer(ComposerConfig(scorers=[_Selective()]))
    out = comp.compose_all(ctx)
    assert [r.gstin_id for r in out] == ["G1", "G2"]
    assert out[0].score > out[1].score
