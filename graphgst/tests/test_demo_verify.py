"""End-to-end test: reset the demo state, verify every story assertion.

This test is what gates a demo before the presenter goes on stage.
If it fails, do NOT run the live demo — fix the drift first.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def demo_state_ready():
    """Regenerate the demo dataset from scratch, byte-deterministic."""
    # PYTHONHASHSEED must be set for determinism; run the CLI which self-execs
    # with it set anyway.
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    result = subprocess.run(
        [sys.executable, "-m", "demo.reset", "--no-neo4j"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"demo.reset failed: {result.stderr}")
    yield


def test_reset_produces_all_artifacts(demo_state_ready):
    from demo.reset import DEMO_ARTIFACT_DIR
    expected = {"gstins.csv", "invoices.csv", "pr.csv", "ewb.csv", "irn.csv",
                 "gstr1.csv", "gstr3b.csv", "gstr2b.csv", "taxpayments.csv",
                 "truth.json", "status.json"}
    actual = set(os.listdir(DEMO_ARTIFACT_DIR))
    missing = expected - actual
    assert not missing, f"demo artifacts missing: {sorted(missing)}"


def test_verify_story_all_steps_pass(demo_state_ready):
    from demo.verify import verify_story
    result = verify_story()
    if not result["ok"]:
        failed = [s for s in result["steps"] if not s["ok"]]
        report = "\n".join(
            f"  step {s['step']} — {s['title']}: " +
            ", ".join(f"{c['key']} exp={c['expected']} act={c['actual']}"
                       for c in s["checks"] if not c["ok"])
            for s in failed
        )
        pytest.fail(f"demo story verification failed:\n{report}")


def test_hero_ring_detected_by_engine(demo_state_ready):
    from demo.verify import verify_story
    facts = verify_story()["facts"]
    assert facts["ring"]["detected"] is True
    assert facts["ring"]["members_count"] == 4
    assert 0.55 <= facts["ring"]["score"] <= 0.70


def test_hero_ring_invoices_have_zero_reconcile_events(demo_state_ready):
    """The narrative pivot: reconciliation misses this ring entirely.
    If any reconcile event ever fires on the hero's invoices, the story
    changes and the presenter needs to know before going on stage."""
    from demo.verify import verify_story
    facts = verify_story()["facts"]
    assert facts["hero"]["reconcile_events"] == 0


def test_embed_finds_at_least_two_hero_co_members(demo_state_ready):
    """The graph-ML side of the story: without a 'ring' label, the
    embedding still groups hero members close in cosine space."""
    from demo.verify import verify_story
    facts = verify_story()["facts"]
    assert facts["embed"]["hero_hits_in_top_10"] >= 2
