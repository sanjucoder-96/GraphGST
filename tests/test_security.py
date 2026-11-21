"""Security hardening tests (audit Phase G)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from security import allowed_data_roots, require_admin, resolve_within


def test_resolve_within_allows_temp_subdir():
    base = Path(tempfile.gettempdir())
    p = resolve_within(str(base / "graphgst_bench_all"))
    assert str(p).startswith(str(base.resolve()))


def test_resolve_within_blocks_absolute_outside_root():
    with pytest.raises(HTTPException):
        resolve_within("/etc")


def test_resolve_within_blocks_dotdot_traversal():
    with pytest.raises(HTTPException):
        resolve_within("../../../../etc/passwd")


def test_resolve_within_respects_env_roots(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("GRAPHGST_DATA_ROOTS", d)
        # a subdir of the configured root is allowed
        inner = Path(d) / "sub"
        inner.mkdir()
        assert resolve_within(str(inner)).exists()
        # something outside is blocked
        with pytest.raises(HTTPException):
            resolve_within("/tmp/definitely-not-under-root-xyz")


def test_require_admin_503_when_unset(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with pytest.raises(HTTPException) as ei:
        require_admin(x_admin_token="anything")
    assert ei.value.status_code == 503


def test_require_admin_401_on_wrong_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-secret")
    with pytest.raises(HTTPException) as ei:
        require_admin(x_admin_token="wrong")
    assert ei.value.status_code == 401


def test_require_admin_ok_on_match(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-secret")
    # returns None (no raise) on a correct token
    assert require_admin(x_admin_token="correct-secret") is None
