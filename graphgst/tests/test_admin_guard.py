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


def test_agent_feedback_writes_entry(client, tmp_path, monkeypatch):
    fp = tmp_path / "feedback.jsonl"
    import main as m
    monkeypatch.setattr(m, "FEEDBACK_PATH", str(fp))
    r = client.post("/api/agent/feedback", json={"label": "accurate", "query": "test"})
    assert r.status_code == 200
    assert fp.exists()
    assert '"accurate"' in fp.read_text(encoding="utf-8")
