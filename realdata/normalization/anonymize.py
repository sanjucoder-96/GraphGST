"""Deterministic anonymization — real identifier → stable internal pseudonym.

Purpose (Phase 4): if a dataset ever contains identifiable GSTINs (or any
sensitive id), we must NOT expose them in the UI, logs, git, screenshots, or
report artifacts — while keeping the graph *topology* intact so ring detection
still works.

How it works:
  * A keyed HMAC-SHA256 over the raw id, truncated to a short hex, produces a
    stable pseudonym `ANON-<12hex>`. Same id + same salt → same pseudonym
    (topology preserved, imports idempotent); a different id → a different
    pseudonym with overwhelming probability.
  * The mapping is **one-way**: without the salt you cannot recover the original
    id from the pseudonym. We do NOT persist a reverse map by default.
  * The salt comes from `REALDATA_ANON_SALT` (env). If unset, a fixed default is
    used so results are reproducible for the non-sensitive public datasets; for
    REAL sensitive data you MUST set a secret salt (documented in
    realdata/README.md) so pseudonyms are not derivable.

Because it is keyed and deterministic, re-importing the same dataset produces
the same pseudonyms — which is what makes the Neo4j import idempotent.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from ..schemas.canonical import CanonicalDataset

_DEFAULT_SALT = "graphgst-realdata-v1-nonsecret-default"


def _salt() -> bytes:
    return os.environ.get("REALDATA_ANON_SALT", _DEFAULT_SALT).encode("utf-8")


def pseudonym(raw_id: str, salt: Optional[bytes] = None) -> str:
    """Stable, one-way pseudonym for a raw identifier."""
    key = salt if salt is not None else _salt()
    digest = hmac.new(key, str(raw_id).encode("utf-8"), hashlib.sha256).hexdigest()
    return f"ANON-{digest[:12]}"


def anonymize_dataset(ds: CanonicalDataset, salt: Optional[bytes] = None) -> CanonicalDataset:
    """Replace every entity id (and the corresponding transaction endpoints)
    with a stable pseudonym, preserving graph topology. Names/source ids that
    could leak identity are also scrubbed. Mutates and returns ``ds``."""
    key = salt if salt is not None else _salt()
    remap = {e.entity_id: pseudonym(e.source_id or e.entity_id, key) for e in ds.entities}

    for e in ds.entities:
        new = remap[e.entity_id]
        e.entity_id = new
        e.source_id = new          # scrub the original id
        e.name = new               # scrub any name that could identify a taxpayer
    for t in ds.txns:
        t.supplier_id = remap.get(t.supplier_id, pseudonym(t.supplier_id, key))
        t.buyer_id = remap.get(t.buyer_id, pseudonym(t.buyer_id, key))

    ds.anonymized = True
    ds.notes = (ds.notes + " | Identifiers anonymized (keyed HMAC pseudonyms; "
                "original ids not retained).").strip(" |")
    return ds
