"""Materialize composed risk onto the graph — the canonical risk source.

The composable risk engine is the single source of truth for risk. Recomputing
it over the full graph on every request is expensive (the legacy
`/api/vendors/risk` did exactly that: ~9s of NetworkX betweenness + IsolationForest
per hit). Instead we compute it ONCE per refresh and write the result onto each
`:GSTIN` node, so every read endpoint (case list, dashboard, vendor list) becomes
a cheap indexed read while explainable reasons stay available on demand.

Written per GSTIN:
    risk_score        INT 0-100   (mirror; keeps the existing range index + legacy
                                   dashboard buckets working)
    risk_score_norm   FLOAT 0-1   (canonical composer score)
    risk_band         STR         (LOW/MED/HIGH/CRITICAL — one vocabulary)
    risk_reasons_json STR         (top composed reasons, JSON; preserves Reason[])
    risk_scored_at    STR ISO     (when this entity was last scored)

Staleness: a singleton `:RiskMeta` node stores the graph fingerprint
(counts of gstins/invoices/rings/events) at materialization time. Reads compare
it to the current fingerprint so stale risk can never be silently served as
current — every risk/case response carries `materialization.stale`.

Determinism: the composer is a pure function of the graph; given the same graph
(same PYTHONHASHSEED for the ring engine's SCC order) the materialized values are
identical.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .reasons import band_for

COMPOSER_VERSION = "composer/v1:reconcile0.35+ring0.30+rules0.20+temporal0.15"

# ── Cypher ───────────────────────────────────────────────────────────────
_ENSURE_SCHEMA = [
    "CREATE INDEX gstin_risk_band IF NOT EXISTS FOR (g:GSTIN) ON (g.risk_band)",
    # The case list filters + sorts on risk_score_norm (the canonical 0-1 score);
    # without this index that hot query is a full NodeByLabelScan.
    "CREATE INDEX gstin_risk_norm IF NOT EXISTS FOR (g:GSTIN) ON (g.risk_score_norm)",
    "CREATE CONSTRAINT riskmeta_id IF NOT EXISTS FOR (m:RiskMeta) REQUIRE m.id IS UNIQUE",
]

_WRITE_RISK = """
UNWIND $rows AS row
MATCH (g:GSTIN {gstin_id: row.id})
SET g.risk_score        = row.score100,
    g.risk_score_norm   = row.score,
    g.risk_band         = row.band,
    g.risk_reasons_json = row.reasons_json,
    g.risk_scored_at    = row.at
"""

_MARK_MATERIALIZING = (
    "MERGE (m:RiskMeta {id: 'singleton'}) "
    "SET m.materializing = true, m.materialize_started_at = $at"
)

_WRITE_META = """
MERGE (m:RiskMeta {id: 'singleton'})
SET m.materialized_at = $at,
    m.materializing = false,
    m.fingerprint_json = $fingerprint_json,
    m.n_scored   = $n_scored,
    m.composer_version = $version
"""

_READ_META = """
MATCH (m:RiskMeta {id: 'singleton'})
RETURN m.materialized_at AS materialized_at, m.n_scored AS n_scored,
       m.composer_version AS composer_version, m.materializing AS materializing,
       m.fingerprint_json AS fingerprint_json
"""

# Content-sensitive fingerprint. Counts alone can't see an in-place edit that
# preserves node counts (an amount correction, a status flip, a date change), so
# the fingerprint also carries cheap CONTENT aggregates over exactly the inputs
# composed risk depends on:
#   gstins / cancelled_gstins         — RuleScorer + reconcile CANCELLED_SUPPLIER
#   invoices / invoice_gst_sum        — amounts feed exposure + reconcile deltas
#   non_matched_invoices              — invoice.status changes flip this
#   max_invoice_date                  — date edits move the temporal window
#   rings / ring_score_sum            — ring detection/scoring
#   events                            — reconciliation outcomes
# All are single-pass aggregates (one query), deterministic for a given graph.
_FINGERPRINT = """
CALL { MATCH (g:GSTIN)
       RETURN count(g) AS ng,
              sum(CASE WHEN g.status = 'CANCELLED' THEN 1 ELSE 0 END) AS ncancel }
CALL { MATCH (i:Invoice)
       RETURN count(i) AS ni, sum(coalesce(i.total_gst, 0)) AS gst,
              toString(max(i.date)) AS maxd,
              sum(CASE WHEN i.status = 'MATCHED' THEN 0 ELSE 1 END) AS nmm }
CALL { MATCH (r:Ring) RETURN count(r) AS nr, sum(coalesce(r.score, 0)) AS rscore }
CALL { MATCH (m:MatchEvent) RETURN count(m) AS ne }
RETURN ng, ncancel, ni, gst, maxd, nmm, nr, rscore, ne
"""

_READ_ONE = """
MATCH (g:GSTIN {gstin_id: $id})
RETURN g.risk_score_norm AS score, g.risk_score AS score100, g.risk_band AS band,
       g.risk_reasons_json AS reasons_json, g.risk_scored_at AS scored_at
"""


def _ensure_schema() -> None:
    from db import run_write
    for cql in _ENSURE_SCHEMA:
        try:
            run_write(cql)
        except Exception:
            pass  # index/constraint may already exist or DB busy; non-fatal


def current_fingerprint() -> Dict[str, Any]:
    """Content-sensitive graph fingerprint (counts + cheap content aggregates).
    Deterministic for a given graph; changes when any risk-relevant content
    changes, including in-place edits that preserve node counts."""
    from db import run_query
    rows = run_query(_FINGERPRINT)
    r = rows[0] if rows else {}
    return {
        "gstins": int(r.get("ng") or 0),
        "cancelled_gstins": int(r.get("ncancel") or 0),
        "invoices": int(r.get("ni") or 0),
        "invoice_gst_sum": round(float(r.get("gst") or 0.0), 2),
        "non_matched_invoices": int(r.get("nmm") or 0),
        "max_invoice_date": r.get("maxd") or "",
        "rings": int(r.get("nr") or 0),
        "ring_score_sum": round(float(r.get("rscore") or 0.0), 4),
        "events": int(r.get("ne") or 0),
    }


def read_materialization_status() -> Dict[str, Any]:
    """Return the stored materialization stamp + a live staleness verdict.

    `stale` is True when risk has never been materialized, or when the current
    graph fingerprint differs from the one captured at materialization time.
    """
    from db import run_query
    try:
        cur = current_fingerprint()
        rows = run_query(_READ_META)
    except Exception:
        # Degrade like the rest of the risk surface: report stale rather than
        # 500 if the DB blips between reads.
        return {"materialized_at": None, "stale": True, "n_scored": 0,
                "composer_version": None, "fingerprint": {}, "current_fingerprint": {}}
    if not rows:
        return {
            "materialized_at": None, "stale": True, "n_scored": 0,
            "composer_version": None, "fingerprint": {},
            "current_fingerprint": cur,
        }
    m = rows[0]
    try:
        stored = json.loads(m.get("fingerprint_json") or "{}")
    except (ValueError, TypeError):
        stored = {}
    # Stale if the content-sensitive fingerprint moved OR a materialization is
    # mid-flight / failed part-way (the materializing flag is cleared only on
    # full success), so a partially-written risk set can never read as current.
    stale = (stored != cur) or bool(m.get("materializing"))
    return {
        "materialized_at": m.get("materialized_at"),
        "stale": stale,
        "n_scored": int(m.get("n_scored") or 0),
        "composer_version": m.get("composer_version"),
        "fingerprint": stored,
        "current_fingerprint": cur,
    }


def read_materialized_risk(gstin_id: str) -> Optional[Dict[str, Any]]:
    """Read one GSTIN's materialized risk, or None if never materialized."""
    from db import run_query
    rows = run_query(_READ_ONE, {"id": gstin_id})
    if not rows or rows[0].get("score") is None:
        return None
    r = rows[0]
    reasons: List[dict] = []
    try:
        reasons = json.loads(r.get("reasons_json") or "[]")
    except (ValueError, TypeError):
        reasons = []
    score = float(r.get("score") or 0.0)
    return {
        "score": score,
        "score_100": int(r.get("score100") or round(score * 100)),
        "band": r.get("band") or band_for(score).value,
        "reasons": reasons,
        "scored_at": r.get("scored_at"),
    }


def _rows_from_ranked(ranked: List[Any], at: str) -> List[dict]:
    rows = []
    for r in ranked:
        d = r.to_dict() if hasattr(r, "to_dict") else r
        score = float(d.get("score") or 0.0)
        rows.append({
            "id": d.get("gstin_id"),
            "score": round(score, 6),
            "score100": int(round(score * 100)),
            "band": d.get("band") or band_for(score).value,
            "reasons_json": json.dumps(d.get("reasons") or []),
            "at": at,
        })
    return rows


def materialize_risk(ranked: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Compose risk for every GSTIN (unless `ranked` is supplied) and write it
    onto the graph + update the RiskMeta stamp. Returns the new status dict."""
    from db import run_write

    if ranked is None:
        from .api import default_composer
        from .hydrate import hydrate_context
        ctx, _rings, _events = hydrate_context()
        ranked = default_composer().compose_all(ctx)

    at = datetime.now(timezone.utc).isoformat()
    _ensure_schema()
    rows = _rows_from_ranked(ranked, at)
    # Mark materializing BEFORE the chunked writes so a mid-way failure (the
    # writes are per-chunk transactions, not one atomic write) leaves the flag
    # set → read_materialization_status reports stale until a full refresh heals.
    run_write(_MARK_MATERIALIZING, {"at": at})
    for i in range(0, len(rows), 1000):
        run_write(_WRITE_RISK, {"rows": rows[i:i + 1000]})

    fp = current_fingerprint()
    run_write(_WRITE_META, {   # clears materializing + stamps the fingerprint
        "at": at,
        "fingerprint_json": json.dumps(fp, sort_keys=True),
        "n_scored": len(rows), "version": COMPOSER_VERSION,
    })
    return read_materialization_status()


def refresh_intelligence(persist: bool = True) -> Dict[str, Any]:
    """Full canonical refresh: detect+persist rings, reconcile+persist events,
    then compose+materialize risk against those same in-memory results (so the
    graph is hydrated once, not per-stage). This is the ONE place that makes the
    graph's intelligence current; call it after any ingestion.
    """
    from db import run_write

    from .api import default_composer
    from .hydrate import hydrate_context

    t0 = time.perf_counter()
    # Detect + persist FIRST (MERGE by ring_id / event_id, idempotent). We do NOT
    # wipe :Ring beforehand: the ring engine's H (historical_prior) and R
    # (recurrence) signals read the PRIOR persisted rings during this run, so
    # wiping first would pin both to 0 and destroy sighting_count history.
    ctx, rings, events = hydrate_context(persist_rings=persist, persist_events=persist)
    if persist:
        # GC orphans: analytic nodes NOT produced by this detection no longer
        # correspond to a current cycle/anomaly, so remove them by id (done AFTER
        # detection, so recurrence history was already read). Empty id list →
        # `NOT x IN []` is true for all → wipes the label, which is correct when
        # nothing was detected.
        ring_ids = [getattr(r, "ring_id", None) for r in rings]
        ring_ids = [r for r in ring_ids if r]
        event_ids = [e.get("event_id") for e in events if e.get("event_id")]
        run_write("MATCH (r:Ring) WHERE NOT r.ring_id IN $ids DETACH DELETE r",
                  {"ids": ring_ids})
        run_write("MATCH (m:MatchEvent) WHERE NOT m.event_id IN $ids DETACH DELETE m",
                  {"ids": event_ids})
    ranked = default_composer().compose_all(ctx)
    status = materialize_risk(ranked)
    # Report persisted counts from the authoritative post-write fingerprint (the
    # DB), not the in-memory lists — so a swallowed persist failure can't report
    # a phantom success.
    fp = status.get("fingerprint", {})

    # Train + persist the lookalike embedding ONCE against this exact graph state,
    # stamping the same fingerprint, so Related Vendors is LIVE after a refresh
    # (not a per-request train, not a UI mock fallback). Best-effort: a graph
    # without embeddings still refreshes.
    embed_trained = 0
    if persist:
        try:
            embed_trained = _train_embeddings(fp)
        except Exception as e:  # noqa: BLE001
            logger.warning("embedding training skipped during refresh: %s", e)

    return {
        "ok": True,
        "rings_persisted": fp.get("rings", 0) if persist else 0,
        "events_persisted": fp.get("events", 0) if persist else 0,
        "gstins_scored": status.get("n_scored", 0),
        "embeddings_indexed": embed_trained,
        "materialized_at": status.get("materialized_at"),
        "stale": status.get("stale"),
        "fingerprint": fp,
        "elapsed_sec": round(time.perf_counter() - t0, 3),
    }


def _train_embeddings(fingerprint: Dict[str, Any]) -> int:
    """Train the node2vec/PMI-SVD lookalike index against the current graph and
    persist it with the given graph fingerprint. Deterministic (seed 42,
    hash-seed-invariant); uses the benchmark-headline config so the demo matches
    the documented structural_hit@10 / cohesion_recall@10 numbers. Returns the
    number of indexed entities."""
    from embed.api import _hydrate_edges_from_neo4j
    from embed.persist import save_index
    from embed.train import EmbedConfig, train
    edges = _hydrate_edges_from_neo4j()
    if not edges:
        return 0
    model = train(graph_source={"edges": edges},
                  config=EmbedConfig(dim=64, walks_per_node=15, walk_len=25, seed=42))
    save_index(model, graph_fingerprint=fingerprint)
    return len(model.ids)
