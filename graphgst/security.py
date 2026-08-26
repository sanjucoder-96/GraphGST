"""Backend security helpers.

Centralises the two things the API layer must get right:

  * `require_admin` — constant-time admin-token check (shared by every
    destructive / mutating / training endpoint).
  * `resolve_within` — safe filesystem-path resolution that prevents path
    traversal: a user-supplied directory is accepted ONLY if, after
    resolving symlinks and `..`, it lives under one of a fixed set of
    allowed roots.

See docs/SECURITY.md for the threat model.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Iterable, List

from fastapi import Header, HTTPException, status

# ── Admin token ────────────────────────────────────────────────────────────

def require_admin(x_admin_token: str = Header(default="")) -> None:
    """FastAPI dependency. 401 if the header is missing/wrong; 503 if the
    server has no ADMIN_TOKEN configured (fail closed, never open)."""
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "ADMIN_TOKEN not configured; endpoint disabled")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "X-Admin-Token required and must match server ADMIN_TOKEN")


# ── Safe path resolution ───────────────────────────────────────────────────

def allowed_data_roots() -> List[Path]:
    """Directories a user-supplied path may live under. Configurable via
    GRAPHGST_DATA_ROOTS (os.pathsep-separated); defaults to the project's
    datagen output, the demo artifacts, and the system temp dir (where the
    benchmark harness writes)."""
    here = Path(__file__).resolve().parent
    env = os.environ.get("GRAPHGST_DATA_ROOTS")
    if env:
        roots = [Path(p) for p in env.split(os.pathsep) if p.strip()]
    else:
        import tempfile
        roots = [
            here / "datagen_output",
            here / "demo" / "artifacts",
            here / "benchmarks",
            Path(tempfile.gettempdir()),
        ]
    out: List[Path] = []
    for r in roots:
        try:
            out.append(r.resolve())
        except Exception:
            continue
    return out


def resolve_within(candidate: str, roots: Iterable[Path] | None = None) -> Path:
    """Resolve `candidate` and return it ONLY if it is inside an allowed root.

    Raises HTTPException(400) on traversal / outside-root. This blocks
    `../../etc`, absolute paths outside the roots, and symlink escapes.
    """
    roots = list(roots) if roots is not None else allowed_data_roots()
    try:
        resolved = Path(candidate).resolve()
    except Exception:
        raise HTTPException(400, "invalid path")
    for root in roots:
        try:
            resolved.relative_to(root)   # raises ValueError if not under root
            return resolved
        except ValueError:
            continue
    raise HTTPException(
        400,
        "path is outside the allowed data roots "
        "(set GRAPHGST_DATA_ROOTS to widen)",
    )
