"""End-to-end integration: synthetic data → CSV → load → reconcile → rings →
shipped risk composer (audit Phase I).

This is the one test that wires the WHOLE analytic core together the way the
API does, with no Neo4j: it generates a small deterministic dataset to disk as
CSV, reloads it through the real `_load_graph_source`, runs the real reconcile
and ring engines, and composes risk with the REAL shipped `default_composer`
from `risk.api` (the four-scorer configuration the audit settled on — not a
mock). It asserts the output honors the documented API contract, that planted
rings are discriminated, and that the whole pipeline is deterministic.

Marked `slow` because it runs the full (small) pipeline; still runs by default.
"""
import csv
import os

import pytest

from benchmarks.bench_risk_discrimination import (_generate,
                                                  _load_graph_source,
                                                  _member_meta)
from datagen.config import GenerationConfig
from reconcile.engine import ReconcileConfig, run_reconcile
from reconcile.outcomes import OUTCOMES
from rings.engine import EngineConfig, run_pipeline
from risk.api import default_composer
from risk.context import build_context_from_graph_source

pytestmark = pytest.mark.slow

_EXPECTED_CSVS = ("gstins.csv", "invoices.csv", "gstr1.csv", "gstr3b.csv",
                  "taxpayments.csv", "ewb.csv", "pr.csv")


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("integration_ds"))
    cfg = GenerationConfig(
        n_gstins=120, months=2, n_rings=3,
        ring_size_min=3, ring_size_max=5, seed=42, out_dir=out,
    )
    _generate(cfg)
    return cfg, out


def _pipeline(gs):
    """The real API hydration path, minus Neo4j: reconcile + rings + compose."""
    events = run_reconcile(
        graph_source=gs, config=ReconcileConfig(include_matched=False))
    rings = run_pipeline(
        graph_source={"edges": gs["edges"], "member_meta": _member_meta(gs["gstins"])},
        config=EngineConfig(hop_max=7, window_days=90, persist=False, propagate=False))
    ctx = build_context_from_graph_source(
        gs,
        match_events=[e for e in events if e.get("outcome") != "MATCHED"],
        detected_rings=[r.to_dict() for r in rings],
        member_meta=_member_meta(gs["gstins"]),
    )
    composer = default_composer()
    return events, rings, composer.compose_all(ctx)


def test_csvs_and_truth_written(generated):
    _, out = generated
    for name in _EXPECTED_CSVS:
        p = os.path.join(out, name)
        assert os.path.exists(p), f"missing {name}"
        with open(p, encoding="utf-8") as f:
            assert len(list(csv.DictReader(f))) > 0, f"{name} is empty"
    assert os.path.exists(os.path.join(out, "truth.json"))


def test_graph_source_loads_with_edges(generated):
    _, out = generated
    gs = _load_graph_source(out)
    assert gs["edges"], "graph_source has no edges"
    assert gs["gstins"], "graph_source has no gstins"


def test_reconcile_emits_valid_outcomes(generated):
    _, out = generated
    gs = _load_graph_source(out)
    events, _, _ = _pipeline(gs)
    assert events, "reconcile produced no events"
    for e in events:
        assert e["outcome"] in OUTCOMES, f"unknown outcome {e['outcome']}"


def test_rings_detected_and_members_are_real_gstins(generated):
    _, out = generated
    gs = _load_graph_source(out)
    _, rings, _ = _pipeline(gs)
    assert rings, "no rings detected in a dataset with 3 planted rings"
    gstin_ids = {g["gstin_id"] for g in gs["gstins"]}
    for r in rings:
        assert set(r.members) <= gstin_ids
        assert 0.0 <= r.score <= 1.0


def test_risk_output_honors_api_contract(generated):
    _, out = generated
    gs = _load_graph_source(out)
    _, _, ranked = _pipeline(gs)
    assert ranked
    keys = {"gstin_id", "score", "band", "contributions",
            "reasons", "scorers_fired", "scorers_run"}
    for r in ranked:
        d = r.to_dict()
        assert keys <= set(d), f"missing keys: {keys - set(d)}"
        assert 0.0 <= d["score"] <= 1.0
        assert d["band"] in {"LOW", "MED", "HIGH", "CRITICAL"}
    # Sorted descending by score (the API relies on this).
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_planted_ring_members_score_above_average(generated):
    """Discrimination sanity: planted ring members carry the RingScorer
    contribution most entities lack, so their mean risk must exceed the
    population mean. A weak, robust assertion — not a tuned metric."""
    import json
    _, out = generated
    gs = _load_graph_source(out)
    _, _, ranked = _pipeline(gs)
    with open(os.path.join(out, "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)
    members = set()
    for pr in truth.get("planted_rings", []):
        members.update(pr.get("members") or [])
    assert members, "no planted ring members in truth"
    by_id = {r.gstin_id: r.score for r in ranked}
    member_scores = [by_id[m] for m in members if m in by_id]
    assert member_scores, "no planted members scored"
    pop_mean = sum(by_id.values()) / len(by_id)
    member_mean = sum(member_scores) / len(member_scores)
    assert member_mean > pop_mean, (
        f"ring members ({member_mean:.3f}) not above population ({pop_mean:.3f})")


def test_pipeline_is_deterministic(generated):
    """Same context, two composes → identical ranking. Guards against any
    hidden nondeterminism in the composer/scorers within a single process."""
    _, out = generated
    gs = _load_graph_source(out)
    _, _, ranked1 = _pipeline(gs)
    _, _, ranked2 = _pipeline(gs)
    assert [(r.gstin_id, r.score) for r in ranked1] == \
           [(r.gstin_id, r.score) for r in ranked2]


def test_same_input_same_graph_same_risk(tmp_path_factory):
    """Reproducibility spine: same seed → byte-identical CSVs (same graph) →
    identical composed-risk ranking (same risk). Proves the whole
    generate→normalize→reconcile→rings→risk chain is deterministic."""
    a = str(tmp_path_factory.mktemp("det_a"))
    b = str(tmp_path_factory.mktemp("det_b"))
    cfg_a = GenerationConfig(n_gstins=120, months=2, n_rings=3,
                             ring_size_min=3, ring_size_max=5, seed=42, out_dir=a)
    cfg_b = GenerationConfig(n_gstins=120, months=2, n_rings=3,
                             ring_size_min=3, ring_size_max=5, seed=42, out_dir=b)
    _generate(cfg_a)
    _generate(cfg_b)
    # same input → same graph (byte-identical source CSVs)
    for name in ("gstins.csv", "invoices.csv", "gstr1.csv", "taxpayments.csv"):
        with open(os.path.join(a, name), encoding="utf-8") as fa, \
             open(os.path.join(b, name), encoding="utf-8") as fb:
            assert fa.read() == fb.read(), f"{name} differs between identical-seed runs"
    # same graph → same risk (identical composed ranking)
    _, _, ranked_a = _pipeline(_load_graph_source(a))
    _, _, ranked_b = _pipeline(_load_graph_source(b))
    assert [(r.gstin_id, round(r.score, 9)) for r in ranked_a] == \
           [(r.gstin_id, round(r.score, 9)) for r in ranked_b]
