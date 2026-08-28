"""Idempotent persistence of detected rings to Neo4j.

All writes go through db.run_write. Rings are keyed by their canonical
`ring_id` so re-detection updates in place rather than duplicating.

Break-edge is stored as FLAT PROPERTIES on the Ring node — not as a
relationship — because the removed edge is a HYPOTHETICAL.

Recurrence fix (Phase 3 revision)
---------------------------------
Because ring_id is a deterministic function of members, MERGE is
idempotent — at most ONE Ring node ever exists per pattern. Under the
original scheme, `count_prior_multiset` therefore only ever returned 0
(first detection) or 1 (any subsequent detection), so R saturated at
~0.28 and its docstring claim was un-implementable.

We now carry a `sighting_count` property on the Ring node:
    ON CREATE SET sighting_count = 1
    ON MATCH  SET sighting_count = coalesce(sighting_count, 1) + 1

`count_prior_multiset` reads that property BEFORE upsert, so a ring
detected for the k-th time sees n_prior = k-1, and R saturates as
intended (r(3)~0.63, r(10)~0.96).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

RING_CONSTRAINT_CQL = (
    "CREATE CONSTRAINT ring_id_unique IF NOT EXISTS "
    "FOR (r:Ring) REQUIRE r.ring_id IS UNIQUE"
)

UPSERT_RING_CQL = """
MERGE (r:Ring {ring_id: $ring_id})
  ON CREATE SET r.detected_at = datetime(), r.sighting_count = 1
  ON MATCH  SET r.sighting_count = coalesce(r.sighting_count, 1) + 1
SET r.score          = $score,
    r.C              = $C,
    r.V              = $V,
    r.T              = $T,
    r.R              = $R,
    r.N              = $N,
    r.H              = $H,
    r.hops           = $hops,
    r.total_gst      = $total_gst,
    r.date_span_days = $date_span_days,
    r.last_scored_at = datetime()
WITH r
UNWIND $members AS gstin_id
  MATCH (g:GSTIN {gstin_id: gstin_id})
  MERGE (r)-[:INCLUDES]->(g)
WITH r
UNWIND $invoices AS invoice_id
  MATCH (i:Invoice {invoice_id: invoice_id})
  MERGE (r)-[:CONTAINS]->(i)
RETURN r.ring_id AS ring_id,
       r.score   AS score,
       r.sighting_count AS sighting_count,
       size($members)  AS n_members,
       size($invoices) AS n_invoices
"""

BREAK_EDGE_CQL = """
MATCH (r:Ring {ring_id: $ring_id})
SET r.break_edge_from        = $from_gstin,
    r.break_edge_to          = $to_gstin,
    r.break_edge_invoice     = $invoice_id,
    r.break_edge_score_after = $score_after_removal,
    r.break_edge_score_drop  = $score_drop,
    r.break_edge_rationale   = $rationale,
    r.break_edge_computed_at = datetime()
RETURN r.ring_id AS ring_id,
       r.score   AS current_score,
       r.break_edge_score_after AS score_after,
       r.break_edge_score_drop  AS score_drop
"""

LIST_RINGS_CQL = """
MATCH (r:Ring)
OPTIONAL MATCH (r)-[:INCLUDES]->(g:GSTIN)
OPTIONAL MATCH (r)-[:CONTAINS]->(i:Invoice)
WITH r,
     count(DISTINCT g) AS n_members,
     count(DISTINCT i) AS n_invoices,
     collect(DISTINCT g.gstin_id) AS members
RETURN r.ring_id        AS ring_id,
       r.score          AS score,
       r.C              AS closure_strength,
       r.V              AS value_similarity,
       r.T              AS temporal_compactness,
       r.R              AS recurrence,
       r.N              AS network_signal,
       r.H              AS historical_prior,
       r.hops           AS hops,
       r.total_gst      AS total_gst,
       r.date_span_days AS date_span_days,
       r.sighting_count AS sighting_count,
       r.break_edge_from      AS break_edge_from,
       r.break_edge_to        AS break_edge_to,
       r.break_edge_invoice   AS break_edge_invoice,
       r.break_edge_score_drop AS break_edge_score_drop,
       n_members,
       n_invoices,
       members,
       toString(r.detected_at)    AS detected_at,
       toString(r.last_scored_at) AS last_scored_at
ORDER BY r.score DESC, r.detected_at DESC
"""

# Neo4j temporal values (neo4j.time.DateTime/Date) are NOT JSON-serializable by
# FastAPI/Pydantic. `r{.*}` would splat the raw `detected_at` / `last_scored_at`
# / `break_edge_computed_at` DateTimes into the response and 500 the endpoint.
# Override those keys with toString() so the projection is pure JSON scalars.
GET_RING_CQL = """
MATCH (r:Ring {ring_id: $ring_id})
OPTIONAL MATCH (r)-[:INCLUDES]->(g:GSTIN)
OPTIONAL MATCH (r)-[:CONTAINS]->(i:Invoice)
WITH r,
     collect(DISTINCT g.gstin_id) AS members,
     collect(DISTINCT i.invoice_id) AS invoices
RETURN r{.*,
         detected_at: toString(r.detected_at),
         last_scored_at: toString(r.last_scored_at),
         break_edge_computed_at: toString(r.break_edge_computed_at),
         members: members,
         invoices: invoices} AS ring
"""

SEEN_MEMBERS_CQL = (
    "MATCH (r:Ring)-[:INCLUDES]->(g:GSTIN) RETURN collect(DISTINCT g.gstin_id) AS seen"
)

# Read n_prior directly from the Ring node's sighting_count. Because
# ring_id is a deterministic function of members, this replaces the
# old APOC-based multiset comparison.
SIGHTING_COUNT_CQL = (
    "MATCH (r:Ring {ring_id: $ring_id}) RETURN coalesce(r.sighting_count, 0) AS n_prior"
)


def ensure_constraints() -> None:
    from db import run_write
    run_write(RING_CONSTRAINT_CQL)


def upsert_ring(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Idempotent MERGE of a Ring + its members and invoices.

    Also increments the ring's sighting_count on every call. On success
    returns the parsed row; on any Neo4j failure, logs the exception
    with the ring_id and re-raises so the caller (API/engine) can
    reflect the failure back to the user rather than silently reporting
    a persisted ring that doesn't actually exist.
    """
    from db import run_write
    try:
        return [dict(r) for r in run_write(UPSERT_RING_CQL, payload)]
    except Exception:
        logger.exception("upsert_ring failed for ring_id=%s", payload.get("ring_id"))
        raise


def upsert_break_edge(
    ring_id: str,
    from_gstin: str,
    to_gstin: str,
    invoice_id: Optional[str],
    score_after_removal: float,
    score_drop: float,
    rationale: str,
) -> List[Dict[str, Any]]:
    from db import run_write
    try:
        return [
            dict(r)
            for r in run_write(
                BREAK_EDGE_CQL,
                {
                    "ring_id": ring_id,
                    "from_gstin": from_gstin,
                    "to_gstin": to_gstin,
                    "invoice_id": invoice_id,
                    "score_after_removal": float(score_after_removal),
                    "score_drop": float(score_drop),
                    "rationale": rationale,
                },
            )
        ]
    except Exception:
        logger.exception("upsert_break_edge failed for ring_id=%s", ring_id)
        raise


def list_rings() -> List[Dict[str, Any]]:
    from db import run_query
    return [dict(r) for r in run_query(LIST_RINGS_CQL)]


def get_ring(ring_id: str) -> Optional[Dict[str, Any]]:
    from db import run_query
    rows = run_query(GET_RING_CQL, {"ring_id": ring_id})
    if not rows or not rows[0].get("ring"):
        return None
    return _shape_persisted_ring(dict(rows[0]["ring"]))


def _shape_persisted_ring(r: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a persisted :Ring node (flat C/V/T/… + break_edge_* props) into
    the SAME shape as an in-memory DetectedRing.to_dict(): a nested `signals`
    object and a `break_edge` object. The flat props are left in place for
    backward compatibility. This makes GET /api/rings/{id} shape-consistent with
    POST /api/rings/detect and with what the frontend Ring type expects."""
    r["signals"] = {k: r.get(k) for k in ("C", "V", "T", "R", "N", "H")}
    if r.get("break_edge_invoice") or r.get("break_edge_from"):
        r["break_edge"] = {
            "src": r.get("break_edge_from"), "dst": r.get("break_edge_to"),
            "invoice_id": r.get("break_edge_invoice"),
            "score_drop": r.get("break_edge_score_drop"),
            "score_after": r.get("break_edge_score_after"),
        }
    else:
        r["break_edge"] = None
    return r


def fetch_seen_members() -> List[str]:
    """All GSTINs currently linked to any :Ring — feeds the H signal.

    Read-only helper. On any Neo4j failure we return [] (which makes H
    conservatively 0) and log the exception so operators can see the
    fallback; we deliberately do NOT re-raise, because the pipeline
    should still produce results when the H signal has no data.
    """
    from db import run_query
    try:
        rows = run_query(SEEN_MEMBERS_CQL)
    except Exception:
        logger.exception("fetch_seen_members failed; H signal will default to 0")
        return []
    if not rows:
        return []
    return list(rows[0].get("seen") or [])


def count_prior_multiset(members: Sequence[str], ring_id_override: Optional[str] = None) -> int:
    """How many times has this exact ring been seen previously?

    Reads `r.sighting_count` from the Ring node keyed by the ring_id
    derived from `members`. Called BEFORE upsert, so on the k-th
    detection returns k-1.

    Read-only failure semantics mirror fetch_seen_members: return 0 on
    Neo4j unavailable, log the exception. R attenuates to 0 in that
    case which is safe.
    """
    from db import run_query
    if ring_id_override is not None:
        rid = ring_id_override
    else:
        # Import locally to avoid circular import at module load.
        from .canonical import ring_id as _ring_id
        try:
            rid = _ring_id(members)
        except Exception:
            return 0
    try:
        rows = run_query(SIGHTING_COUNT_CQL, {"ring_id": rid})
        return int(rows[0]["n_prior"]) if rows else 0
    except Exception:
        logger.exception("count_prior_multiset failed for ring_id=%s", rid)
        return 0
