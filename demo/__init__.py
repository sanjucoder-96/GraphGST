"""demo — the reproducible 3-5 minute investigation story (Phase 8).

Every number the presenter says on stage traces back to either:
  * the same deterministic synthetic dataset (seed 42, n_gstins 500,
    n_rings 8) reset by `python -m demo.reset`; OR
  * an explicitly labelled DEMO fixture in the frontend (`web/src/lib/
    mocks.ts`) — the frontend badges the environment DEMO whenever those
    reach the UI.

Public exports:

    from demo import reset, verify_story, STORY, HERO_RING, DEMO_CFG
"""
from .reset import reset, DEMO_CFG, DEMO_ARTIFACT_DIR
from .scenario import HERO_RING
from .story import STORY, story_json
from .verify import verify_story

__all__ = [
    "reset",
    "DEMO_CFG",
    "DEMO_ARTIFACT_DIR",
    "HERO_RING",
    "STORY",
    "story_json",
    "verify_story",
]
