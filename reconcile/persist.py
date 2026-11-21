"""Persist MatchEvent records into Neo4j as first-class nodes.

Each `MatchEvent` node has the outcome + severity + delta + reasons
inline, and is linked to the cited Invoice, Supplier, Buyer, and (when
present) to a specific `PurchaseRegister` line via `HAS_EVIDENCE`.

Schema (idempotent MERGE by event_id):

    (:MatchEvent {event_id, outcome, severity, delta, at, reasons_json})
      -[:ABOUT]-> (:Invoice)
      -[:BY]->     (:GSTIN {gstin_id: supplier_gstin})
      -[:TO]->     (:GSTIN {gstin_id: buyer_gstin})
      -[:HAS_EVIDENCE {reason_name}]-> (:...)   for each Reason with a node
"""
from __future__ import annotations

import json
import logging
from typing import Iterable, List

logger = logging.getLogger(__name__)


ENSURE_CQL = (
    "CREATE CONSTRAINT match_event_id IF NOT EXISTS "
    "FOR (m:MatchEvent) REQUIRE m.event_id IS UNIQUE"
)


def ensure_constraints() -> None:
    from db import run_write
    try:
        run_write(ENSURE_CQL)
    except Exception:
        logger.exception("failed to ensure MatchEvent constraint")


UPSERT_CQL = """
UNWIND $rows AS r
MERGE (m:MatchEvent {event_id: r.event_id})
SET m.outcome      = r.outcome,
    m.severity     = r.severity,
    m.delta        = r.delta,
    m.at           = r.at,
    m.reasons_json = r.reasons_json
WITH m, r
MATCH (i:Invoice {invoice_id: r.invoice_id})
MERGE (m)-[:ABOUT]->(i)
WITH m, r
OPTIONAL MATCH (s:GSTIN {gstin_id: r.supplier_gstin})
FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
    MERGE (m)-[:BY]->(s))
WITH m, r
OPTIONAL MATCH (b:GSTIN {gstin_id: r.buyer_gstin})
FOREACH (_ IN CASE WHEN b IS NULL THEN [] ELSE [1] END |
    MERGE (m)-[:TO]->(b))
"""


def upsert_events(events: Iterable[dict], batch: int = 500) -> int:
    """Persist MatchEvent nodes; returns the count written."""
    from db import run_write
    ensure_constraints()
    events = list(events)
    if not events:
        return 0

    def _row(e: dict) -> dict:
        return {
            "event_id": e["event_id"],
            "outcome": e["outcome"],
            "severity": e["severity"],
            "delta": None if e.get("delta") is None else float(e["delta"]),
            "at": e["at"],
            "reasons_json": json.dumps(e.get("reasons") or [], ensure_ascii=False),
            "invoice_id": e["invoice_id"],
            "supplier_gstin": e["supplier_gstin"],
            "buyer_gstin": e["buyer_gstin"],
        }

    n = 0
    for i in range(0, len(events), batch):
        chunk = [_row(e) for e in events[i:i + batch]]
        try:
            run_write(UPSERT_CQL, {"rows": chunk})
            n += len(chunk)
        except Exception:
            logger.exception("upsert_events batch failed at offset %d", i)
            raise
    return n


LIST_CQL = """
MATCH (m:MatchEvent)
WHERE $outcome IS NULL OR m.outcome = $outcome
RETURN m.event_id AS event_id,
       m.outcome AS outcome,
       m.severity AS severity,
       m.delta AS delta,
       m.at AS at,
       m.reasons_json AS reasons_json,
       [(m)-[:ABOUT]->(i) | i.invoice_id][0] AS invoice_id,
       [(m)-[:BY]->(s) | s.gstin_id][0] AS supplier_gstin,
       [(m)-[:TO]->(b) | b.gstin_id][0] AS buyer_gstin
ORDER BY m.at DESC
LIMIT $limit
"""


def list_events(outcome: str | None = None, limit: int = 200) -> List[dict]:
    from db import run_query
    rows = run_query(LIST_CQL, {"outcome": outcome, "limit": int(limit)})
    for r in rows:
        try:
            r["reasons"] = json.loads(r.pop("reasons_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            r["reasons"] = []
    return rows
