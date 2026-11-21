"""Case assembly service — Neo4j → domain → canonical schemas.

One case = a bounded set of targeted, gstin_id-indexed Cypher reads (no
full-graph recomputation): entity meta, materialized risk (or a single live
compose fallback), the entity's rings, its reconciliation events, its ITC
exposure, related vendors (embeddings), a timeline, and a small ring/1-hop
subgraph. This replaces the previous client-side assembly from 4 endpoints +
MOCK_RINGS.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from schemas import (Band, Case, CaseList, CaseListItem, CaseStatusResult,
                     EntityRef, ExposureBreakdown, InvestigationStatus,
                     MatchEventOut, MaterializationInfo, Reason, RelatedVendor,
                     RingEdge, RingSummary, RiskScore, TimelineEvent)

# ITC-blocking reconciliation outcomes → the value at risk for exposure.
BLOCKING_OUTCOMES = [
    "MISSING_GSTR1", "MISSING_GSTR3B", "MISSING_TAX_PAYMENT",
    "CANCELLED_SUPPLIER", "DUPLICATE",
]

_SIGNAL_KEYS = ("C", "V", "T", "R", "N", "H")


def _safe_band(value: Any, score: float = 0.0) -> Band:
    """Coerce a DB/legacy band string to the canonical enum. A single node with
    a stale value (e.g. legacy 'MEDIUM') must not 500 the whole response."""
    if isinstance(value, str) and value in Band.__members__:
        return Band(value)
    if value == "MEDIUM":
        return Band.MED
    from risk.reasons import band_for
    return Band(band_for(float(score or 0.0)).value)


# ── low-level reads (all keyed by gstin_id / indexed) ────────────────────
def _entity(gstin_id: str) -> Optional[Dict[str, Any]]:
    from db import run_query
    rows = run_query(
        "MATCH (g:GSTIN {gstin_id:$id}) "
        "RETURN g.gstin_id AS gstin_id, "
        "       coalesce(g.name,g.legal_name,g.trade_name) AS name, "
        "       g.state_code AS state_code, g.status AS status, "
        "       g.scenario AS scenario, g.investigation_status AS investigation_status",
        {"id": gstin_id},
    )
    return rows[0] if rows else None


def _rings_for(gstin_id: str, include_edges: bool = False) -> List[RingSummary]:
    from db import run_query
    rows = run_query(
        "MATCH (r:Ring)-[:INCLUDES]->(:GSTIN {gstin_id:$id}) "
        "OPTIONAL MATCH (r)-[:INCLUDES]->(gm:GSTIN) "
        "OPTIONAL MATCH (r)-[:CONTAINS]->(i:Invoice) "
        "WITH r, collect(DISTINCT gm.gstin_id) AS members, "
        "        collect(DISTINCT i.invoice_id) AS invoices "
        "RETURN r{.*, members: members, invoices: invoices} AS ring "
        "ORDER BY r.score DESC",
        {"id": gstin_id},
    )
    out = [_ring_summary(r["ring"]) for r in rows]
    if include_edges:
        for ring in out:
            ring.edges = _ring_edges(ring.ring_id)
    return out


def _ring_edges(ring_id: str) -> List[RingEdge]:
    """The ring's per-hop invoice edges (src→dst, date, amount, gst, vehicle)."""
    from db import run_query
    rows = run_query(
        "MATCH (r:Ring {ring_id:$rid})-[:CONTAINS]->(i:Invoice) "
        "MATCH (s:GSTIN)-[:ISSUED_INVOICE]->(i)-[:BILLED_TO]->(b:GSTIN) "
        "OPTIONAL MATCH (i)-[:TRANSPORTED_VIA]->(:EWayBill)-[:USED_VEHICLE]->(v:Vehicle) "
        "WITH i, s, b, head(collect(v.vehicle_number)) AS vehicle "
        "RETURN s.gstin_id AS src, b.gstin_id AS dst, i.invoice_id AS invoice_id, "
        "       toString(i.date) AS date, coalesce(i.amount,i.taxable_value,0) AS amount, "
        "       coalesce(i.total_gst,0) AS gst_amount, vehicle AS vehicle_id, i.hsn AS hsn "
        "ORDER BY i.date",
        {"rid": ring_id},
    )
    return [RingEdge(
        src=r["src"], dst=r["dst"], invoice_id=r["invoice_id"], date=r.get("date"),
        amount=float(r.get("amount") or 0.0), gst_amount=float(r.get("gst_amount") or 0.0),
        vehicle_id=r.get("vehicle_id"), hsn=r.get("hsn"),
    ) for r in rows]


def _ring_summary(r: Dict[str, Any]) -> RingSummary:
    from risk.reasons import band_for
    span = int(r.get("date_span_days") or 0)
    total_gst = float(r.get("total_gst") or 0.0)
    members = r.get("members") or []
    invoices = r.get("invoices") or []
    score = float(r.get("score") or 0.0)
    break_edge = None
    if r.get("break_edge_invoice") or r.get("break_edge_from"):
        break_edge = {
            "src": r.get("break_edge_from"), "dst": r.get("break_edge_to"),
            "invoice_id": r.get("break_edge_invoice"),
            "score_drop": r.get("break_edge_score_drop"),
            "score_after": r.get("break_edge_score_after"),
        }
    velocity = round(total_gst / max(1, span), 2)
    return RingSummary(
        ring_id=r.get("ring_id"),
        score=score,
        band=Band(band_for(score).value),
        members=list(members),
        member_count=len(members),
        invoices=list(invoices),
        invoice_count=len(invoices),
        hops=int(r.get("hops") or len(members)),
        date_span_days=span,
        total_gst=total_gst,
        signals={k: float(r.get(k) or 0.0) for k in _SIGNAL_KEYS},
        contribution={},
        share={},
        break_edge=break_edge,
        temporal={"velocity_inr_per_day": velocity, "date_span_days": span},
        velocity_inr_per_day=velocity,
    )


def _events_for(gstin_id: str, limit: int = 100) -> List[MatchEventOut]:
    from db import run_query
    rows = run_query(
        "MATCH (m:MatchEvent)-[rel:BY|TO]->(:GSTIN {gstin_id:$id}) "
        "OPTIONAL MATCH (m)-[:BY]->(s:GSTIN) "
        "OPTIONAL MATCH (m)-[:TO]->(b:GSTIN) "
        "OPTIONAL MATCH (m)-[:ABOUT]->(i:Invoice) "
        "RETURN DISTINCT m.event_id AS event_id, m.outcome AS outcome, "
        "       m.severity AS severity, m.delta AS delta, m.at AS at, "
        "       m.reasons_json AS reasons_json, i.invoice_id AS invoice_id, "
        "       s.gstin_id AS supplier_gstin, b.gstin_id AS buyer_gstin "
        "ORDER BY m.at DESC LIMIT $limit",
        {"id": gstin_id, "limit": int(limit)},
    )
    out: List[MatchEventOut] = []
    for r in rows:
        role = "supplier" if r.get("supplier_gstin") == gstin_id else (
            "buyer" if r.get("buyer_gstin") == gstin_id else None)
        reasons = _parse_reasons(r.get("reasons_json"))
        out.append(MatchEventOut(
            event_id=r.get("event_id"), outcome=r.get("outcome"),
            severity=r.get("severity") or "MEDIUM", delta=r.get("delta"),
            at=r.get("at"), invoice_id=r.get("invoice_id"),
            supplier_gstin=r.get("supplier_gstin"), buyer_gstin=r.get("buyer_gstin"),
            role=role, reasons=reasons,
        ))
    return out


def _exposure_for(gstin_id: str) -> ExposureBreakdown:
    """ITC value the entity's non-compliant ISSUED invoices put at risk
    (supplier-side). `total_inr`/`invoice_count` aggregate over DISTINCT invoices
    (an invoice with several blocking outcomes counts its GST ONCE); `by_outcome`
    is a per-outcome view whose buckets may overlap and need not sum to the total.
    """
    from db import run_query
    # Total + count over DISTINCT invoices carrying ANY blocking outcome.
    tot = run_query(
        "MATCH (g:GSTIN {gstin_id:$id})-[:ISSUED_INVOICE]->(i:Invoice) "
        "WHERE EXISTS { (i)<-[:ABOUT]-(m:MatchEvent) WHERE m.outcome IN $blocking } "
        "RETURN sum(coalesce(i.total_gst,0)) AS total, count(i) AS n",
        {"id": gstin_id, "blocking": BLOCKING_OUTCOMES},
    )
    t = tot[0] if tot else {}
    # Per-outcome breakdown (distinct invoices per outcome; may overlap).
    by_rows = run_query(
        "MATCH (g:GSTIN {gstin_id:$id})-[:ISSUED_INVOICE]->(i:Invoice)"
        "<-[:ABOUT]-(m:MatchEvent) WHERE m.outcome IN $blocking "
        "WITH m.outcome AS outcome, collect(DISTINCT i) AS invs "
        "RETURN outcome, reduce(s=0.0, x IN invs | s + coalesce(x.total_gst,0)) AS gst",
        {"id": gstin_id, "blocking": BLOCKING_OUTCOMES},
    )
    by_outcome = {r.get("outcome"): round(float(r.get("gst") or 0.0), 2) for r in by_rows}
    return ExposureBreakdown(
        total_inr=round(float(t.get("total") or 0.0), 2),
        by_outcome=by_outcome,
        invoice_count=int(t.get("n") or 0),
    )


def _timeline_for(gstin_id: str, limit: int = 200) -> List[TimelineEvent]:
    from db import run_query
    rows = run_query(
        "MATCH (g:GSTIN {gstin_id:$id}) "
        "OPTIONAL MATCH (g)-[:ISSUED_INVOICE]->(io:Invoice) "
        "OPTIONAL MATCH (ib:Invoice)-[:BILLED_TO]->(g) "
        "WITH collect(DISTINCT io) + collect(DISTINCT ib) AS invs "
        "UNWIND invs AS i WITH DISTINCT i WHERE i IS NOT NULL "
        "RETURN toString(i.date) AS date, i.invoice_id AS ref, "
        "       coalesce(i.amount,i.taxable_value,0) AS amount, "
        "       coalesce(i.total_gst,0) AS gst, i.status AS status "
        "ORDER BY i.date DESC LIMIT $limit",   # keep the most RECENT N
        {"id": gstin_id, "limit": int(limit)},
    )
    out: List[TimelineEvent] = []
    for r in rows:
        if not r.get("date"):
            continue
        out.append(TimelineEvent(
            date=r["date"], kind="invoice", ref=r.get("ref"),
            label=str(r.get("status") or "invoice"),
            amount=float(r.get("amount") or 0.0), gst=float(r.get("gst") or 0.0),
        ))
    out.reverse()   # present ascending for display
    return out


def _subgraph_for(gstin_id: str, cap: int = 60) -> Dict[str, Any]:
    """A small 1-hop invoice neighbourhood around the entity, in Cytoscape shape,
    so the graph canvas needs no separate full-graph fetch."""
    from db import run_query
    rows = run_query(
        "MATCH (g:GSTIN {gstin_id:$id})-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(b:GSTIN) "
        "RETURN g.gstin_id AS src, b.gstin_id AS dst, i.invoice_id AS invoice_id, "
        "       toString(i.date) AS date, coalesce(i.amount,i.taxable_value,0) AS amount "
        "UNION "
        "MATCH (a:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(g:GSTIN {gstin_id:$id}) "
        "RETURN a.gstin_id AS src, g.gstin_id AS dst, i.invoice_id AS invoice_id, "
        "       toString(i.date) AS date, coalesce(i.amount,i.taxable_value,0) AS amount",
        {"id": gstin_id},
    )
    rows = rows[:cap]
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    for r in rows:
        for gid in (r["src"], r["dst"]):
            if gid not in nodes:
                nodes[gid] = {"data": {"id": gid, "label": gid[:12], "type": "gstin",
                                       "gstin_short": gid[:8]}}
        edges.append({"data": {
            "id": r["invoice_id"], "source": r["src"], "target": r["dst"],
            "invoice_id": r["invoice_id"], "date": r.get("date"),
            "amount": r.get("amount"), "kind": "invoice"}})
    return {"nodes": list(nodes.values()), "edges": edges}


def _related_vendors(gstin_id: str, k: int = 6,
                     same_ring_members: Optional[set] = None) -> List[RelatedVendor]:
    """Embedding lookalikes, enriched with name + materialized risk band.
    `same_ring_members` (the entity's ring co-members) is passed in by get_case
    to avoid re-running the rings query."""
    try:
        from embed.persist import load_index
    except Exception:
        return []
    idx = None
    try:
        idx = load_index()
    except Exception:
        idx = None
    if idx is None:
        return []
    try:
        hits = idx.similar_to(gstin_id, k=k)
    except Exception:
        return []
    if not hits:
        return []
    from db import run_query
    ids = [h[0] for h in hits]
    meta_rows = run_query(
        "MATCH (g:GSTIN) WHERE g.gstin_id IN $ids "
        "RETURN g.gstin_id AS id, coalesce(g.name,g.legal_name) AS name, "
        "       g.risk_score_norm AS score, g.risk_band AS band",
        {"ids": ids},
    )
    meta = {r["id"]: r for r in meta_rows}
    # rings this entity is in (to badge shared-ring neighbours) — reuse the
    # caller's already-computed membership when provided.
    if same_ring_members is None:
        same_ring_members = set()
        for ring in _rings_for(gstin_id):
            same_ring_members.update(ring.members)
    out: List[RelatedVendor] = []
    for gid, sim in hits:
        m = meta.get(gid, {})
        band = m.get("band")
        out.append(RelatedVendor(
            gstin_id=gid, name=m.get("name"), similarity=round(float(sim), 4),
            risk_score=(float(m["score"]) if m.get("score") is not None else None),
            band=(Band(band) if band in Band.__members__ else None),
            shares_ring=gid in same_ring_members,
        ))
    return out


def _parse_reasons(reasons_json: Any) -> List[Reason]:
    if isinstance(reasons_json, list):
        raw = reasons_json
    else:
        try:
            raw = json.loads(reasons_json or "[]")
        except (ValueError, TypeError):
            raw = []
    out: List[Reason] = []
    for d in raw:
        if not isinstance(d, dict):
            continue
        out.append(Reason(
            name=str(d.get("name", "")), weight=float(d.get("weight") or 0.0),
            detail=str(d.get("detail", "")), evidence=dict(d.get("evidence") or {}),
            scorer=d.get("scorer"),
            contribution=(float(d["contribution"]) if d.get("contribution") is not None else None),
        ))
    return out


# ── risk (materialized-first, single live compose fallback) ──────────────
def _risk_for(gstin_id: str) -> RiskScore:
    from risk.materialize import read_materialized_risk
    mat = read_materialized_risk(gstin_id)
    if mat is not None:
        return RiskScore(
            score=mat["score"], score_100=mat["score_100"],
            band=_safe_band(mat["band"], mat["score"]),
            reasons=_parse_reasons(mat["reasons"]), materialized=True,
            scored_at=mat.get("scored_at"),
        )
    # Fallback: compose this one entity live (materialization not yet run).
    from risk.api import default_composer
    from risk.hydrate import hydrate_context
    ctx, _r, _e = hydrate_context()
    if gstin_id not in ctx.all_gstin_ids():
        return RiskScore(score=0.0, score_100=0, band=Band.LOW, materialized=False)
    d = default_composer().compose(gstin_id, ctx).to_dict()
    score = float(d.get("score") or 0.0)
    return RiskScore(
        score=score, score_100=int(round(score * 100)), band=_safe_band(d.get("band"), score),
        contributions=d.get("contributions") or {}, reasons=_parse_reasons(d.get("reasons")),
        scorers_fired=d.get("scorers_fired") or [], scorers_run=d.get("scorers_run") or [],
        materialized=False,
    )


def _materialization() -> MaterializationInfo:
    from risk.materialize import read_materialization_status
    s = read_materialization_status()
    return MaterializationInfo(
        materialized_at=s.get("materialized_at"), stale=bool(s.get("stale", True)),
        fingerprint=s.get("fingerprint") or {}, current_fingerprint=s.get("current_fingerprint") or {},
        n_scored=int(s.get("n_scored") or 0), composer_version=s.get("composer_version"),
    )


# ── public API ───────────────────────────────────────────────────────────
def get_case(gstin_id: str, include_subgraph: bool = True) -> Optional[Case]:
    ent = _entity(gstin_id)
    if ent is None:
        return None
    risk = _risk_for(gstin_id)
    rings = _rings_for(gstin_id, include_edges=True)
    events = _events_for(gstin_id)
    exposure = _exposure_for(gstin_id)
    ring_members = {m for r in rings for m in r.members}
    related = _related_vendors(gstin_id, same_ring_members=ring_members)
    timeline = _timeline_for(gstin_id)
    subgraph = _subgraph_for(gstin_id) if include_subgraph else None
    latest = events[0].at if events else (timeline[-1].date if timeline else None)
    inv_status = ent.get("investigation_status") or InvestigationStatus.OPEN.value
    return Case(
        case_id=gstin_id,
        entity=EntityRef(
            gstin_id=gstin_id, name=ent.get("name"), state_code=ent.get("state_code"),
            status=ent.get("status"), scenario=ent.get("scenario")),
        risk=risk, exposure=exposure, rings=rings, reconciliation=events,
        related_vendors=related, timeline=timeline, subgraph=subgraph,
        investigation_status=InvestigationStatus(inv_status)
            if inv_status in [s.value for s in InvestigationStatus] else InvestigationStatus.OPEN,
        latest_activity=latest,
        generated_at=datetime.now(timezone.utc).isoformat(),
        materialization=_materialization(),
    )


def set_investigation_status(gstin_id: str, status: str) -> Optional[CaseStatusResult]:
    """Persist the investigation workflow status onto the GSTIN node. Returns
    None if the entity does not exist. This is real Neo4j state — not React
    state — so the status survives reloads and is read back by the Case API."""
    from db import run_write
    at = datetime.now(timezone.utc).isoformat()
    recs = run_write(
        "MATCH (g:GSTIN {gstin_id:$id}) "
        "SET g.investigation_status = $s, g.investigation_updated_at = $at "
        "RETURN g.gstin_id AS id, g.investigation_status AS status, "
        "       g.investigation_updated_at AS at",
        {"id": gstin_id, "s": status, "at": at},
    )
    rows = [dict(r) for r in recs]
    if not rows:
        return None
    r = rows[0]
    return CaseStatusResult(
        case_id=r["id"], investigation_status=InvestigationStatus(r["status"]),
        updated_at=r.get("at"),
    )


def list_cases(band: Optional[str] = None, min_score: float = 0.0,
               limit: int = 100, q: Optional[str] = None) -> CaseList:
    """Ranked case list from MATERIALIZED risk (cheap indexed read). Enriches
    each with ring ids + ITC exposure via two batch queries."""
    from db import run_query
    # A seekable band predicate (g.risk_band = $band) lets the gstin_risk_band
    # index be used; the ($band IS NULL OR ...) disjunction would defeat it, so
    # we only add the band clause when a band is actually requested.
    _RET = (
        "RETURN g.gstin_id AS id, coalesce(g.name,g.legal_name,g.trade_name) AS name, "
        "       g.state_code AS state, g.status AS status, g.scenario AS scenario, "
        "       g.risk_score_norm AS score, g.risk_band AS band, "
        "       g.risk_reasons_json AS reasons_json, "
        "       g.investigation_status AS inv_status "
        "ORDER BY g.risk_score_norm DESC LIMIT $limit")
    params = {"min": float(min_score), "limit": int(limit)}
    if band:
        params["band"] = band
        cql = ("MATCH (g:GSTIN) WHERE g.risk_band = $band "
               "AND g.risk_score_norm IS NOT NULL AND g.risk_score_norm >= $min " + _RET)
    else:
        cql = ("MATCH (g:GSTIN) WHERE g.risk_score_norm IS NOT NULL "
               "AND g.risk_score_norm >= $min " + _RET)
    rows = run_query(cql, params)
    ids = [r["id"] for r in rows]
    ring_map: Dict[str, List[str]] = {}
    exp_map: Dict[str, float] = {}
    if ids:
        for rr in run_query(
            "MATCH (r:Ring)-[:INCLUDES]->(g:GSTIN) WHERE g.gstin_id IN $ids "
            "RETURN g.gstin_id AS id, collect(DISTINCT r.ring_id) AS rings",
            {"ids": ids},
        ):
            ring_map[rr["id"]] = rr.get("rings") or []
        for er in run_query(
            # DISTINCT invoices (EXISTS, not a join over events) so an invoice
            # with multiple blocking outcomes counts its GST once.
            "MATCH (g:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice) "
            "WHERE g.gstin_id IN $ids AND "
            "  EXISTS { (i)<-[:ABOUT]-(m:MatchEvent) WHERE m.outcome IN $blocking } "
            "RETURN g.gstin_id AS id, sum(coalesce(i.total_gst,0)) AS exposure",
            {"ids": ids, "blocking": BLOCKING_OUTCOMES},
        ):
            exp_map[er["id"]] = round(float(er.get("exposure") or 0.0), 2)

    # Full-population band distribution (respects min_score, IGNORES band /
    # limit / q). This is the portfolio summary the UI's distribution bar
    # renders and doubles as a band filter, so it must be stable regardless of
    # the current page or which band is being viewed — not a count of the
    # returned page.
    band_counts: Dict[str, int] = {"LOW": 0, "MED": 0, "HIGH": 0, "CRITICAL": 0}
    for br in run_query(
        "MATCH (g:GSTIN) WHERE g.risk_score_norm IS NOT NULL AND g.risk_score_norm >= $min "
        "RETURN g.risk_band AS band, g.risk_score_norm AS score",
        {"min": float(min_score)},
    ):
        band_counts[_safe_band(br.get("band"), br.get("score")).value] += 1

    cases: List[CaseListItem] = []
    for r in rows:
        reasons = _parse_reasons(r.get("reasons_json"))
        top_reasons = [rs.detail or rs.name for rs in reasons[:3] if (rs.detail or rs.name)]
        name = r.get("name") or r["id"]
        if q:
            hay = f"{r['id']} {name} {' '.join(top_reasons)}".lower()
            if q.lower() not in hay:
                continue
        bnd = _safe_band(r.get("band"), r.get("score")).value
        inv_status = r.get("inv_status") or "open"
        cases.append(CaseListItem(
            case_id=r["id"], gstin_id=r["id"], name=name, state_code=r.get("state"),
            status=r.get("status"), scenario=r.get("scenario"),
            risk_score=float(r.get("score") or 0.0), band=Band(bnd),
            exposure_inr=exp_map.get(r["id"], 0.0),
            ring_ids=ring_map.get(r["id"], []), ring_count=len(ring_map.get(r["id"], [])),
            top_reasons=top_reasons,
            primary_signal=(top_reasons[0] if top_reasons else None),
            investigation_status=InvestigationStatus(inv_status)
                if inv_status in [s.value for s in InvestigationStatus] else InvestigationStatus.OPEN,
        ))
    return CaseList(
        count=len(cases), band_counts=band_counts,
        materialization=_materialization(), cases=cases,
    )
