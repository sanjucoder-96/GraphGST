"""Cheap unit tests for demo.scenario and demo.story."""
from __future__ import annotations

from demo.scenario import DEMO_N_GSTINS, DEMO_SEED, HERO_RING, hero_gstin_prefix
from demo.story import STORY, story_json


def test_hero_ring_has_expected_shape():
    assert HERO_RING["size"] == 4
    assert len(HERO_RING["members"]) == 4
    assert len(HERO_RING["invoices"]) == 4
    # Signal expectations must sum to something in (0, 6)
    total = sum(HERO_RING["expected_signals"].values())
    assert 0 < total < 6.01
    assert 0.0 < HERO_RING["expected_score"] < 1.0


def test_hero_members_are_all_maharashtra():
    # State code 27 in the first two chars
    for m in HERO_RING["members"]:
        assert m.startswith("27"), f"hero member {m} is not Maharashtra"


def test_hero_gstin_prefix_indexing():
    assert hero_gstin_prefix(0) == HERO_RING["members"][0]
    assert hero_gstin_prefix(3) == HERO_RING["members"][3]


def test_story_has_expected_steps():
    titles = [s["title"] for s in STORY]
    assert len(titles) == 8
    assert titles[0].startswith("Setup")
    assert "Ingest" in titles[1]
    assert "Model Card" in titles[-1]


def test_story_step_expected_are_well_formed():
    for s in STORY:
        assert "step" in s and "title" in s and "duration_sec" in s
        for k, v in (s.get("expected") or {}).items():
            # Every expected value is a scalar, bool, or {min, max}
            if isinstance(v, dict):
                assert set(v.keys()) <= {"min", "max"}, (
                    f"step {s['step']} key {k} has unexpected keys {v.keys()}"
                )


def test_story_json_is_serializable():
    import json
    j = story_json()
    dumped = json.dumps(j)         # must not raise
    assert "hero_ring" in dumped
    assert "steps" in dumped


def test_demo_seed_is_stable():
    """A regression-guard: if someone changes DEMO_SEED, every hero
    number needs to be re-derived. This test makes that intentional."""
    assert DEMO_SEED == 42
    assert DEMO_N_GSTINS == 500
