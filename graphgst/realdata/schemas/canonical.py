"""The canonical GST representation every real-data adapter maps TO.

An adapter's ONLY job is to turn a real dataset into a `CanonicalDataset`
(entities + directed value-transactions + a declared field mapping).
Everything downstream — validation, in-memory ring/risk analysis, the Neo4j
load — is dataset-agnostic and reuses the EXISTING Graph GST graph model
(docs/NEO4J_SCHEMA.md) and engines. We deliberately do NOT invent a second
graph model.

Integrity rules baked in here:
  * Nothing fabricates a value. A field absent in the source stays ``None``.
  * Canonical node ids are NOT real GSTINs — `canonical_gstin_id()` produces an
    obviously-synthetic id (``<TAG>:<source_id>``). For a source that carries
    REAL identifiers, the normalization layer's anonymizer replaces them with
    stable pseudonyms *before* they reach the graph (see
    realdata/normalization/anonymize.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Mapping, Optional


def canonical_gstin_id(tag: str, source_id: str) -> str:
    """A canonical node id that is *obviously not* a real 15-char GSTIN
    (``<TAG>:<source_id>``) — so a public-dataset entity can never be mistaken
    for a real taxpayer's GSTIN."""
    return f"{tag.upper()}:{str(source_id).strip()}"


@dataclass
class FieldMapping:
    """One row of an adapter's documented SOURCE → CANONICAL → GRAPH → ENGINE
    mapping. Rendered into the ingestion report and docs so every field is
    traceable to a real source column."""
    source_field: str
    canonical_field: str
    graph: str          # node/relationship it becomes
    engine: str         # which downstream engine consumes it
    note: str = ""


@dataclass
class CanonicalEntity:
    entity_id: str
    source_id: str
    name: Optional[str] = None
    jurisdiction: Optional[str] = None
    status: str = "Active"                 # Active | Cancelled | Unknown
    registration_date: Optional[str] = None
    kind: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalTxn:
    txn_id: str
    supplier_id: str
    buyer_id: str
    date: Optional[str] = None             # ISO 'YYYY-MM-DD' or None
    taxable_value: Optional[float] = None
    tax_amount: Optional[float] = None
    total_value: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    label: Optional[int] = None            # ground-truth fraud/laundering label if any
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalDataset:
    name: str
    source_url: str
    license: str
    description: str
    is_real_taxpayer_data: bool            # False for every legitimate public source
    tag: str
    entities: List[CanonicalEntity] = field(default_factory=list)
    txns: List[CanonicalTxn] = field(default_factory=list)
    field_availability: Dict[str, bool] = field(default_factory=dict)
    mapping: List[FieldMapping] = field(default_factory=list)
    anonymized: bool = False               # set by the anonymizer if it ran
    notes: str = ""


# ── date helpers ─────────────────────────────────────────────────────────────

def parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


# ── graph_source builders (in-memory, no Neo4j) ──────────────────────────────
# Mirror benchmarks/bench_ring_recall._load_edges_from_csv and
# risk.context.build_context_from_graph_source EXACTLY.

def to_ring_graph_source(ds: CanonicalDataset) -> Dict[str, Any]:
    edges: List[Dict[str, Any]] = []
    for t in ds.txns:
        edges.append({
            "src": t.supplier_id, "dst": t.buyer_id, "invoice_id": t.txn_id,
            "date": parse_iso_date(t.date),
            "amount": float(t.taxable_value) if t.taxable_value is not None else 0.0,
            "gst_amount": float(t.tax_amount) if t.tax_amount is not None else 0.0,
            "vehicle_id": None, "hsn": None, "pin_prefix": None,
        })
    member_meta = {e.entity_id: {"directors": []} for e in ds.entities}
    return {"edges": edges, "member_meta": member_meta}


def to_risk_graph_source(ds: CanonicalDataset) -> Dict[str, Any]:
    gstins = [{
        "gstin_id": e.entity_id, "name": e.name or e.entity_id,
        "status": e.status, "state_code": e.jurisdiction, "scenario": None,
    } for e in ds.entities]
    invoices = [{
        "invoice_id": t.txn_id, "supplier_gstin": t.supplier_id,
        "buyer_gstin": t.buyer_id, "date": t.date,
        "amount": float(t.taxable_value) if t.taxable_value is not None else 0.0,
        "total_gst": float(t.tax_amount) if t.tax_amount is not None else 0.0,
        "status": t.status or "UNKNOWN",
        "period": (t.date[:7] if t.date else None), "hsn": None,
    } for t in ds.txns]
    edges = to_ring_graph_source(ds)["edges"]
    return {
        "gstins": gstins, "invoices": invoices, "edges": edges,
        "gstr1_keys": set(), "gstr3b_keys": set(),
        "settled_keys": set(), "ewb_by_invoice": set(),
    }


# ── canonical CSV emit (for the Neo4j loader path) ───────────────────────────
# Writes gstins.csv + invoices.csv in the EXACT schema datagen/loader.py reads.

def write_canonical_csvs(ds: CanonicalDataset, out_dir: str,
                         dataset_id: Optional[str] = None) -> Dict[str, int]:
    import csv
    import os
    os.makedirs(out_dir, exist_ok=True)
    scenario = dataset_id or "PUBLIC_DATASET"

    with open(os.path.join(out_dir, "gstins.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gstin_id", "name", "state_code", "state", "pincode", "sector",
                    "status", "scenario", "incorp_date", "cancellation_date", "directors"])
        for e in ds.entities:
            w.writerow([e.entity_id, e.name or e.entity_id, e.jurisdiction or "", "",
                        "", e.kind or "", e.status, scenario, e.registration_date or "", "", ""])

    with open(os.path.join(out_dir, "invoices.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["invoice_id", "supplier_gstin", "buyer_gstin", "date", "hsn",
                    "description", "taxable_value", "cgst", "sgst", "igst", "total_gst",
                    "place_of_supply", "ewb_required", "status", "scenario", "period"])
        for t in ds.txns:
            tv = "" if t.taxable_value is None else t.taxable_value
            tg = "" if t.tax_amount is None else t.tax_amount
            w.writerow([t.txn_id, t.supplier_id, t.buyer_id, t.date or "", "",
                        "", tv, "", "", "", tg, "", "False",
                        t.status or "UNKNOWN", scenario, (t.date[:7] if t.date else "")])

    return {"gstins.csv": len(ds.entities), "invoices.csv": len(ds.txns)}


def mapping_markdown(ds: CanonicalDataset) -> str:
    if not ds.mapping:
        return "_(no field mapping declared)_"
    out = ["| Source field | Canonical field | Graph node / relationship | Downstream engine |",
           "|---|---|---|---|"]
    for m in ds.mapping:
        out.append(f"| `{m.source_field}` | `{m.canonical_field}` | {m.graph} | {m.engine} |")
    return "\n".join(out)
