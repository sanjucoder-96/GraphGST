"""Verify destructive endpoints refuse without X-Admin-Token."""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-token-please-ignore")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:1")   # unreachable is OK
    # Import main lazily so env is set before FastAPI starts
    from importlib import reload
    import main
    reload(main)
    return TestClient(main.app)


def test_delete_seed_requires_admin(client):
    r = client.delete("/api/seed")
    assert r.status_code == 401


def test_delete_seed_with_bad_token(client):
    r = client.delete("/api/seed", headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 401


def test_force_seed_requires_admin(client):
    r = client.post("/api/seed?force=true")
    assert r.status_code == 401


def test_rings_detect_persist_requires_admin(client):
    """Regression (audit Phase H): a Neo4j-mutating detect must be authenticated.
    The guard fires before the engine runs, so an unreachable Neo4j is irrelevant."""
    r = client.post("/api/rings/detect", json={"persist": True})
    assert r.status_code == 401


def test_rings_detect_propagate_requires_admin(client):
    """propagate=True also writes (ring_propagated_score) → must be guarded too."""
    r = client.post("/api/rings/detect", json={"propagate": True})
    assert r.status_code == 401


def test_rings_detect_readonly_is_open(client):
    """The default (no persist/propagate) is a pure read — must NOT be rejected
    as unauthorized. It may 500 on the unreachable test Neo4j; it must not 401."""
    r = client.post("/api/rings/detect", json={"hop_max": 8, "window_days": 30})
    assert r.status_code != 401


def test_datagen_load_requires_admin(client):
    """datagen mutations use the SHARED constant-time guard now."""
    r = client.post("/api/datagen/load", json={"dir": "whatever"})
    assert r.status_code == 401


def test_agent_feedback_writes_entry(client, tmp_path, monkeypatch):
    fp = tmp_path / "feedback.jsonl"
    import main as m
    monkeypatch.setattr(m, "FEEDBACK_PATH", str(fp))
    r = client.post("/api/agent/feedback", json={"label": "accurate", "query": "test"})
    assert r.status_code == 200
    assert fp.exists()
    assert '"accurate"' in fp.read_text(encoding="utf-8")
