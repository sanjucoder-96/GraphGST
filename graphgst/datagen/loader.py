"""Batch-load a generated dataset into Neo4j.

Uses `UNWIND $rows AS row MERGE …` — the standard idiom for bulk MERGE
in Neo4j — with `apoc.periodic.iterate` when APOC is available for
larger datasets.

Every load operation is chunked into batches of `BATCH` rows so the
transaction size stays manageable on a 1 GB heap.
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Callable, Iterable

from db import run_write, run_query

logger = logging.getLogger(__name__)

BATCH = 1000


def _read_csv(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _chunks(rows: list[dict], n: int) -> Iterable[list[dict]]:
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def _cast_num(row: dict, keys: list[str]) -> dict:
    """Convert '' → None and numeric strings → floats for a CSV row."""
    out = dict(row)
    for k in keys:
        v = out.get(k, "")
        if v == "" or v is None:
            out[k] = None
        else:
            try:
                out[k] = float(v) if "." in str(v) else int(v)
            except (TypeError, ValueError):
                out[k] = v
    return out


def _cast_bool(row: dict, keys: list[str]) -> dict:
    out = dict(row)
    for k in keys:
        v = out.get(k, "")
        if isinstance(v, bool):
            continue
        out[k] = str(v).lower() in ("true", "1", "yes", "y")
    return out


# ── loaders per node type ─────────────────────────────────────────────────

def load_gstins(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MERGE (g:GSTIN {gstin_id: r.gstin_id})
    SET g.name = r.name,
        g.state_code = r.state_code,
        g.state = r.state,
        g.pincode = r.pincode,
        g.sector = r.sector,
        g.status = r.status,
        g.scenario = r.scenario,
        g.incorp_date = r.incorp_date,
        g.cancellation_date = r.cancellation_date
    // Attach directors as Director nodes
    WITH g, r
    UNWIND (CASE WHEN r.directors IS NULL OR r.directors = '' THEN [] ELSE split(r.directors, ';') END) AS did
    MERGE (d:Director {director_id: did})
    MERGE (g)-[:DIRECTED_BY]->(d)
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        run_write(q, {"rows": chunk})
        n += len(chunk)
    return n


def load_invoices(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MATCH (s:GSTIN {gstin_id: r.supplier_gstin})
    MATCH (b:GSTIN {gstin_id: r.buyer_gstin})
    MERGE (i:Invoice {invoice_id: r.invoice_id})
    SET i.date = date(r.date),
        i.hsn = r.hsn,
        i.description = r.description,
        i.taxable_value = toFloat(r.taxable_value),
        i.amount = toFloat(r.taxable_value),
        i.cgst = toFloat(r.cgst),
        i.sgst = toFloat(r.sgst),
        i.igst = toFloat(r.igst),
        i.total_gst = toFloat(r.total_gst),
        i.place_of_supply = r.place_of_supply,
        i.ewb_required = (r.ewb_required = 'True' OR r.ewb_required = 'true'),
        i.status = r.status,
        i.scenario = r.scenario,
        i.period = r.period
    MERGE (s)-[:ISSUED_INVOICE]->(i)
    MERGE (i)-[:BILLED_TO]->(b)
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        casted = [_cast_num(x, ["taxable_value", "cgst", "sgst", "igst", "total_gst"]) for x in chunk]
        run_write(q, {"rows": casted})
        n += len(chunk)
    return n


def load_ewb(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MATCH (i:Invoice {invoice_id: r.invoice_id})
    MERGE (e:EWayBill {ewb_id: r.ewb_id})
    SET e.vehicle_number = r.vehicle_number,
        e.distance_km = toInteger(r.distance_km),
        e.from_pin = r.from_pin,
        e.to_pin = r.to_pin,
        e.valid_until = r.valid_until,
        e.transporter = r.transporter,
        e.phantom = (r.phantom = 'True' OR r.phantom = 'true'),
        e.scenario = r.scenario
    MERGE (i)-[:TRANSPORTED_VIA]->(e)
    MERGE (v:Vehicle {vehicle_number: r.vehicle_number})
    MERGE (e)-[:USED_VEHICLE]->(v)
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        run_write(q, {"rows": chunk})
        n += len(chunk)
    return n


def load_irn(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MATCH (i:Invoice {invoice_id: r.invoice_id})
    MERGE (irn:IRN {irn: r.irn})
    SET irn.generated_at = r.generated_at,
        irn.portal_status = r.portal_status
    MERGE (i)-[:AUTHENTICATED_BY]->(irn)
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        run_write(q, {"rows": chunk})
        n += len(chunk)
    return n


def load_pr(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MERGE (p:PurchaseRegister {pr_line_id: r.pr_line_id})
    SET p.buyer_gstin = r.buyer_gstin,
        p.invoice_id = r.invoice_id,
        p.booked_date = r.booked_date,
        p.booked_amount = toFloat(r.booked_amount),
        p.booked_tax = toFloat(r.booked_tax)
    // Attempt to link to buyer + invoice if they exist
    WITH p, r
    OPTIONAL MATCH (b:GSTIN {gstin_id: r.buyer_gstin})
    FOREACH (_ IN CASE WHEN b IS NULL THEN [] ELSE [1] END |
      MERGE (b)-[:BOOKED_PR]->(p))
    WITH p, r
    OPTIONAL MATCH (i:Invoice {invoice_id: r.invoice_id})
    FOREACH (_ IN CASE WHEN i IS NULL THEN [] ELSE [1] END |
      MERGE (i)-[:BOOKED_AS]->(p))
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        run_write(q, {"rows": chunk})
        n += len(chunk)
    return n


def load_gstr1(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MERGE (g:GSTR1 {return_id: r.return_id})
    SET g.period = r.period,
        g.filed_date = r.filed_date,
        g.filed_status = r.filed_status
    WITH g, r
    MATCH (s:GSTIN {gstin_id: r.gstin})
    MERGE (s)-[:FILED]->(g)
    // Link every invoice for (supplier, period) to this GSTR-1
    WITH s, g, r
    MATCH (s)-[:ISSUED_INVOICE]->(i:Invoice) WHERE i.period = r.period
    MERGE (i)-[:DECLARED_IN]->(g)
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        run_write(q, {"rows": chunk})
        n += len(chunk)
    return n


def load_gstr3b(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MERGE (g:GSTR3B {return_id: r.return_id})
    SET g.period = r.period,
        g.filed_date = r.filed_date,
        g.tax_paid_status = r.tax_paid_status,
        g.tax_paid = toFloat(r.tax_paid),
        g.itc_claimed = toFloat(r.itc_claimed)
    WITH g, r
    MATCH (s:GSTIN {gstin_id: r.gstin})
    MERGE (s)-[:FILED]->(g)
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        run_write(q, {"rows": chunk})
        n += len(chunk)
    return n


def load_gstr2b(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MERGE (g:GSTR2B {return_id: r.return_id})
    SET g.period = r.period
    WITH g, r
    MATCH (b:GSTIN {gstin_id: r.gstin})
    MERGE (b)-[:FILED]->(g)
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        run_write(q, {"rows": chunk})
        n += len(chunk)
    return n


def load_taxpayments(rows: list[dict]) -> int:
    q = """
    UNWIND $rows AS r
    MERGE (tp:TaxPayment {challan_no: r.challan_no})
    SET tp.payment_date = r.payment_date,
        tp.amount_paid = toFloat(r.amount_paid),
        tp.cgst_paid = toFloat(r.cgst_paid),
        tp.sgst_paid = toFloat(r.sgst_paid),
        tp.igst_paid = toFloat(r.igst_paid),
        tp.bank = r.bank,
        tp.utr = r.utr,
        tp.status = r.status
    WITH tp, r
    MATCH (g:GSTR3B {return_id: r.gstr3b_return_id})
    MERGE (g)-[:SETTLED_BY]->(tp)
    """
    n = 0
    for chunk in _chunks(rows, BATCH):
        run_write(q, {"rows": chunk})
        n += len(chunk)
    return n


# ── driver ────────────────────────────────────────────────────────────────

_LOAD_ORDER = [
    ("gstins.csv", load_gstins),
    ("invoices.csv", load_invoices),
    ("ewb.csv", load_ewb),
    ("irn.csv", load_irn),
    ("pr.csv", load_pr),
    ("gstr1.csv", load_gstr1),
    ("gstr3b.csv", load_gstr3b),
    ("gstr2b.csv", load_gstr2b),
    ("taxpayments.csv", load_taxpayments),
]


def load_directory(dir_path: str) -> dict:
    """Load every CSV in dir_path in the correct dependency order.

    Uniqueness constraints must exist first — call
    `seeder.create_constraints()` before this if the DB is fresh.
    """
    from seeder import create_constraints
    create_constraints()
    stats = {}
    for name, fn in _LOAD_ORDER:
        path = os.path.join(dir_path, name)
        if not os.path.exists(path):
            logger.warning(f"{name} missing in {dir_path} — skipping")
            stats[name] = 0
            continue
        rows = _read_csv(path)
        stats[name] = fn(rows)
        logger.info(f"loaded {stats[name]} rows from {name}")
    stats["orphans_removed"] = _gc_orphans()
    return stats


def _gc_orphans() -> int:
    """Delete structurally-isolated child nodes left when a parent row was
    absent (a TaxPayment whose GSTR3B is missing, a PurchaseRegister whose
    Invoice is missing). These would otherwise be counted but never reachable.
    Returns the number deleted."""
    n = 0
    for label in ("TaxPayment", "PurchaseRegister"):
        rows = run_write(
            f"MATCH (x:{label}) WHERE NOT (x)--() "
            "WITH x LIMIT 100000 DETACH DELETE x RETURN count(x) AS c")
        try:
            n += int(rows[0]["c"]) if rows else 0
        except (KeyError, TypeError, IndexError):
            pass
    if n:
        logger.info("GC removed %d orphan child nodes", n)
    return n
