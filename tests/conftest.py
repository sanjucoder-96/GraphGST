"""Pytest bootstrap + live-DB isolation guard.

1. Put the project root on sys.path so `import db`, `import main`, etc. work.
2. Keep UNIT tests off the real database. `db.py` loads `.env` on import, which
   may point NEO4J_* at a live Aura instance. Without a guard, any unit test
   that happened to call the DB would silently hit — and possibly mutate —
   production. The autouse fixture below points NEO4J_URI at an unreachable
   localhost for every test that is NOT marked `neo4j`, restoring the original
   "DB is unreachable in unit tests" contract. Tests marked `neo4j` are left
   untouched and use the real `.env` configuration.
"""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _isolate_live_db(request, monkeypatch):
    """Neutralise the live DB for every non-`neo4j` test."""
    if request.node.get_closest_marker("neo4j"):
        yield  # integration tests use the real .env configuration untouched
        return
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:1")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")
    # Force the singleton to rebuild against the unreachable URI if a prior
    # test opened a real driver.
    try:
        import db
        db.close_driver()
    except Exception:
        pass
    yield
    try:
        import db
        db.close_driver()
    except Exception:
        pass
