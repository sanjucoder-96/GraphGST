"""Batch reconciliation engine.

Runs `matcher.match_one_invoice` over every invoice in the graph and
returns a list of `MatchEvent` dicts. Two invocation modes:

  1. In-memory (`graph_source={"invoices":[...], "pr":[...], "gstins":[...],
     "gstr1_keys":set(...), "gstr3b_keys":set(...), "settled_keys":set(...),
     "ewb_by_invoice":set(...) }`) — used by tests and benchmarks.
  2. From Neo4j — pass `graph_source=None`; the engine issues a single
     multi-part Cypher to hydrate everything it needs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from .matcher import match_one_invoice

logger = logging.getLogger(__name__)


@dataclass
class ReconcileConfig:
    tolerances: Dict[str, float] = field(default_factory=lambda: {
        "amount_abs": 1.0, "amount_rel": 0.001, "date_days": 3,
        "invoice_id_jw": 0.90,
    })
    hsn_catalog: Optional[Dict[str, dict]] = None    # inject via datagen.catalog if desired
    persist: bool = False                             # write MatchEvent nodes into Neo4j
    include_matched: bool = True                      # emit MATCHED events too


@dataclass
class MatchEvent:
    """Thin wrapper so callers can consume dataclass objects instead of dicts
    if they prefer. The wire format remains dicts (via `to_dict`)."""
    event_id: str
    outcome: str
    severity: str
    invoice_id: str
    supplier_gstin: str
    buyer_gstin: str
    delta: Optional[float]
    at: str
    reasons: List[dict]

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "outcome": self.outcome,
            "severity": self.severity,
            "invoice_id": self.invoice_id,
            "supplier_gstin": self.supplier_gstin,
            "buyer_gstin": self.buyer_gstin,
            "delta": self.delta,
            "at": self.at,
            "reasons": self.reasons,
        }


def run_reconcile(
    graph_source: Optional[Mapping[str, Any]] = None,
    config: Optional[ReconcileConfig] = None,
) -> List[dict]:
    """Return a list of MatchEvent dicts."""
    cfg = config or ReconcileConfig()
    if graph_source is None:
        graph_source = _hydrate_from_neo4j()

    invoices: List[dict] = list(graph_source.get("invoices") or [])
    pr_lines: List[dict] = list(graph_source.get("pr") or [])
    gstin_by_id: Dict[str, dict] = {g["gstin_id"]: g for g in (graph_source.get("gstins") or [])}
    gstr1_keys = set(graph_source.get("gstr1_keys") or ())    # {(gstin, period), …}
    gstr3b_keys = set(graph_source.get("gstr3b_keys") or ())
    settled_keys = set(graph_source.get("settled_keys") or ())   # gstr3b return_ids that are settled
    ewb_by_invoice = set(graph_source.get("ewb_by_invoice") or ())   # {invoice_id, …}

    # Index PR lines by (invoice_id, buyer_gstin) for O(1) join.
    pr_by_inv: Dict[str, List[dict]] = {}
    pr_by_buyer: Dict[str, List[dict]] = {}
    for p in pr_lines:
        pr_by_inv.setdefault(p.get("invoice_id") or "", []).append(p)
        pr_by_buyer.setdefault(p.get("buyer_gstin") or "", []).append(p)

    events: List[dict] = []
    for inv in invoices:
        sup_id = inv.get("supplier_gstin")
        period = inv.get("period")
        supplier = gstin_by_id.get(sup_id, {"gstin_id": sup_id, "status": "Unknown"})
        pr_lines_for_inv = pr_by_inv.get(inv.get("invoice_id") or "", [])
        buyer_pr = pr_by_buyer.get(inv.get("buyer_gstin") or "", [])

        supplier_filed_gstr1 = (sup_id, period) in gstr1_keys
        supplier_filed_gstr3b = (sup_id, period) in gstr3b_keys
        # A supplier is considered "settled" if any GSTR3B they filed for
        # the period has a corresponding TaxPayment in `settled_keys`.
        # `settled_keys` is a set of GSTR3B return_ids; we derive the
        # expected return_id from convention (datagen uses this convention).
        expected_g3b_id = _expected_gstr3b_id(sup_id, period)
        supplier_gstr3b_settled = expected_g3b_id in settled_keys

        one_events = match_one_invoice(
            invoice=inv,
            pr_lines=pr_lines_for_inv,
            supplier=supplier,
            supplier_filed_gstr1=supplier_filed_gstr1,
            supplier_filed_gstr3b=supplier_filed_gstr3b,
            supplier_gstr3b_settled=supplier_gstr3b_settled,
            ewb_present=(inv.get("invoice_id") in ewb_by_invoice),
            all_pr_lines_for_buyer=buyer_pr,
            hsn_catalog=cfg.hsn_catalog,
            tolerances=cfg.tolerances,
        )
        if not cfg.include_matched:
            one_events = [e for e in one_events if e["outcome"] != "MATCHED"]
        events.extend(one_events)

    if cfg.persist:
        # Re-raise on failure (mirrors rings/engine.py). Swallowing here would
        # let a caller (e.g. risk materialization) report a phantom "persisted"
        # count and compute risk from events that never reached the graph.
        from .persist import upsert_events
        upsert_events(events)

    return events


# ── helpers ────────────────────────────────────────────────────────────
def _expected_gstr3b_id(gstin: str, period: str) -> str:
    """Mirror `datagen.identifiers.synth_return_id` for GSTR3B."""
    if not gstin or not period:
        return ""
    return f"GSTR3B-{gstin[:7]}-{period.replace('-', '')}"


def _hydrate_from_neo4j() -> Dict[str, Any]:
    """Pull everything the engine needs from Neo4j in a few round-trips."""
    from db import run_query

    invoices = run_query(
        "MATCH (s:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)-[:BILLED_TO]->(b:GSTIN) "
        "RETURN i.invoice_id AS invoice_id, s.gstin_id AS supplier_gstin, "
        "       b.gstin_id AS buyer_gstin, toString(i.date) AS date, i.hsn AS hsn, "
        "       coalesce(i.taxable_value, i.amount) AS taxable_value, "
        "       i.total_gst AS total_gst, i.cgst AS cgst, i.sgst AS sgst, i.igst AS igst, "
        "       i.place_of_supply AS place_of_supply, "
        "       coalesce(i.ewb_required, false) AS ewb_required, i.period AS period"
    )
    pr = run_query(
        "MATCH (p:PurchaseRegister) "
        "RETURN p.pr_line_id AS pr_line_id, p.invoice_id AS invoice_id, "
        "       p.buyer_gstin AS buyer_gstin, p.booked_date AS booked_date, "
        "       p.booked_amount AS booked_amount, p.booked_tax AS booked_tax"
    )
    gstins = run_query(
        "MATCH (g:GSTIN) "
        "RETURN g.gstin_id AS gstin_id, g.status AS status, g.state_code AS state_code, "
        "       g.cancellation_date AS cancellation_date, "
        "       coalesce(g.name, g.legal_name, g.trade_name) AS name, g.scenario AS scenario"
    )
    gstr1_keys = {
        (r["gstin"], r["period"]) for r in run_query(
            "MATCH (g:GSTIN)-[:FILED]->(r:GSTR1) RETURN g.gstin_id AS gstin, r.period AS period"
        )
    }
    gstr3b_keys = {
        (r["gstin"], r["period"]) for r in run_query(
            "MATCH (g:GSTIN)-[:FILED]->(r:GSTR3B) RETURN g.gstin_id AS gstin, r.period AS period"
        )
    }
    settled_keys = {
        r["return_id"] for r in run_query(
            "MATCH (g:GSTR3B)-[:SETTLED_BY]->(:TaxPayment {status:'CLEARED'}) "
            "RETURN g.return_id AS return_id"
        )
    }
    ewb_by_invoice = {
        r["invoice_id"] for r in run_query(
            "MATCH (i:Invoice)-[:TRANSPORTED_VIA]->(:EWayBill) RETURN i.invoice_id AS invoice_id"
        )
    }
    return {
        "invoices": invoices, "pr": pr, "gstins": gstins,
        "gstr1_keys": gstr1_keys, "gstr3b_keys": gstr3b_keys,
        "settled_keys": settled_keys, "ewb_by_invoice": ewb_by_invoice,
    }
