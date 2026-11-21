"""Data-quality validation + the feature-availability matrix.

Two layers, both dataset-agnostic:

  * `quality_report(ds)` — a comprehensive, READ-ONLY audit of the dataset as
    loaded: counts, duplicates, missing/invalid fields, structural problems,
    coverage. It DISCARDS NOTHING; it only reports. This is the "REAL DATA
    QUALITY REPORT" (Phase 3).
  * `validate_and_normalize(ds)` — the minimal cleaning the engines require:
    drop only *structurally impossible* transactions (missing endpoint,
    self-loop), prune edge-less entities, coerce bad numerics to None. Every
    drop is counted and reported, never silent.
  * `feature_availability(ds)` — which Graph GST capabilities can honestly run.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..schemas.canonical import CanonicalDataset, CanonicalEntity
from ..normalization.normalize import is_valid_gstin, parse_amount, valid_iso_date


# ── Comprehensive quality audit (reports, never drops) ───────────────────────

@dataclass
class DataQualityReport:
    records: int
    unique_taxpayers: int
    unique_suppliers: int
    unique_buyers: int
    unique_invoices: int
    duplicate_invoice_ids: int
    exact_duplicate_rows: int
    missing_supplier: int
    missing_buyer: int
    self_loops: int
    missing_invoice_id: int
    missing_dates: int
    invalid_dates: int
    negative_or_invalid_tax: int
    valid_gstin_ids: int
    non_gstin_ids: int
    orphan_invoice_endpoints: int
    pure_suppliers: int
    pure_buyers: int
    field_coverage_pct: Dict[str, float]
    date_range: Tuple[str, str]
    months_covered: int
    issues: List[str] = field(default_factory=list)


def quality_report(ds: CanonicalDataset) -> DataQualityReport:
    txns = ds.txns
    n = len(txns)
    ent_ids = {e.entity_id for e in ds.entities}

    suppliers = Counter(t.supplier_id for t in txns if t.supplier_id)
    buyers = Counter(t.buyer_id for t in txns if t.buyer_id)
    taxpayers = set(suppliers) | set(buyers)

    inv_ids = Counter(t.txn_id for t in txns if t.txn_id)
    dup_inv = sum(1 for v in inv_ids.values() if v > 1)
    row_sig = Counter((t.supplier_id, t.buyer_id, t.date, t.taxable_value) for t in txns)
    exact_dup = sum(v - 1 for v in row_sig.values() if v > 1)

    missing_sup = sum(1 for t in txns if not t.supplier_id)
    missing_buy = sum(1 for t in txns if not t.buyer_id)
    self_loops = sum(1 for t in txns if t.supplier_id and t.supplier_id == t.buyer_id)
    missing_inv = sum(1 for t in txns if not t.txn_id)
    missing_dt = sum(1 for t in txns if not t.date)
    invalid_dt = sum(1 for t in txns if t.date and not valid_iso_date(t.date))
    bad_tax = sum(1 for t in txns
                  if (t.taxable_value is not None and parse_amount(t.taxable_value) is None)
                  or (t.tax_amount is not None and parse_amount(t.tax_amount) is None))

    # GSTIN-format audit runs on the RAW source id (what a real GST feed would carry)
    valid_gstin = sum(1 for e in ds.entities if is_valid_gstin(e.source_id))
    non_gstin = len(ds.entities) - valid_gstin

    orphan = sum(1 for t in txns
                 if (t.supplier_id and t.supplier_id not in ent_ids)
                 or (t.buyer_id and t.buyer_id not in ent_ids))
    pure_sup = len(set(suppliers) - set(buyers))
    pure_buy = len(set(buyers) - set(suppliers))

    def cov(pred) -> float:
        return round(100.0 * sum(1 for t in txns if pred(t)) / max(1, n), 1)
    coverage = {
        "supplier": cov(lambda t: bool(t.supplier_id)),
        "buyer": cov(lambda t: bool(t.buyer_id)),
        "invoice_id": cov(lambda t: bool(t.txn_id)),
        "date": cov(lambda t: bool(t.date)),
        "taxable_value": cov(lambda t: t.taxable_value is not None),
        "tax_amount": cov(lambda t: t.tax_amount is not None),
        "label": cov(lambda t: t.label is not None),
    }
    dated = [t.date[:10] for t in txns if t.date]
    dr = (min(dated), max(dated)) if dated else ("—", "—")
    months = len({d[:7] for d in dated})

    issues: List[str] = []
    if missing_sup or missing_buy:
        issues.append(f"{missing_sup+missing_buy} rows missing an endpoint (dropped at load, counted).")
    if self_loops:
        issues.append(f"{self_loops} self-transactions (supplier==buyer) — not a supplier→buyer edge (dropped at load, counted).")
    if dup_inv:
        issues.append(f"{dup_inv} duplicate invoice ids.")
    if exact_dup:
        issues.append(f"{exact_dup} exact-duplicate rows (kept — may be legitimate repeat trades).")
    if coverage["date"] < 100:
        issues.append(f"date coverage {coverage['date']}% → temporal analysis limited/disabled.")
    if coverage["tax_amount"] == 0:
        issues.append("no tax amounts → reconciliation / ITC-mismatch cannot run.")
    if coverage["label"] == 0:
        issues.append("no fraud/ring labels → UNSUPERVISED analysis only (no precision/recall).")
    if valid_gstin == 0:
        issues.append("no source id is a valid 15-char GSTIN → entity ids are non-GSTIN (public/anonymised data).")

    return DataQualityReport(
        records=n, unique_taxpayers=len(taxpayers), unique_suppliers=len(suppliers),
        unique_buyers=len(buyers), unique_invoices=len(inv_ids),
        duplicate_invoice_ids=dup_inv, exact_duplicate_rows=exact_dup,
        missing_supplier=missing_sup, missing_buyer=missing_buy, self_loops=self_loops,
        missing_invoice_id=missing_inv, missing_dates=missing_dt, invalid_dates=invalid_dt,
        negative_or_invalid_tax=bad_tax, valid_gstin_ids=valid_gstin, non_gstin_ids=non_gstin,
        orphan_invoice_endpoints=orphan, pure_suppliers=pure_sup, pure_buyers=pure_buy,
        field_coverage_pct=coverage, date_range=dr, months_covered=months, issues=issues,
    )


def quality_markdown(q: DataQualityReport, ds: CanonicalDataset) -> str:
    L = ["## REAL DATA QUALITY REPORT", "",
         f"Records:        {q.records:,}",
         f"Taxpayers:      {q.unique_taxpayers:,}  (suppliers {q.unique_suppliers:,}, buyers {q.unique_buyers:,})",
         f"Invoices:       {q.unique_invoices:,}  (duplicate ids: {q.duplicate_invoice_ids:,})",
         f"Date range:     {q.date_range[0]} → {q.date_range[1]}  ({q.months_covered} month(s))",
         "",
         "Coverage:",
         f"  GSTIN/entity:   supplier {q.field_coverage_pct['supplier']}% · buyer {q.field_coverage_pct['buyer']}%",
         f"  Invoice ID:     {q.field_coverage_pct['invoice_id']}%",
         f"  Tax amount:     {q.field_coverage_pct['tax_amount']}%",
         f"  Date:           {q.field_coverage_pct['date']}%",
         f"  Label:          {q.field_coverage_pct['label']}%",
         "",
         "Structural:",
         f"  self-transactions:        {q.self_loops:,}",
         f"  missing endpoints:        {q.missing_supplier + q.missing_buyer:,}",
         f"  exact-duplicate rows:     {q.exact_duplicate_rows:,}",
         f"  orphan invoice endpoints: {q.orphan_invoice_endpoints:,}",
         f"  pure suppliers / buyers:  {q.pure_suppliers:,} / {q.pure_buyers:,}",
         f"  valid-GSTIN source ids:   {q.valid_gstin_ids:,} (non-GSTIN: {q.non_gstin_ids:,})",
         f"  invalid dates:            {q.invalid_dates:,}",
         f"  negative/invalid tax:     {q.negative_or_invalid_tax:,}",
         "", "Potential issues:"]
    L += [f"  - {i}" for i in q.issues] or ["  - none"]
    return "\n".join(L)


# ── Minimal cleaning the engines require ─────────────────────────────────────

@dataclass
class ValidationReport:
    entities_in: int
    txns_in: int
    entities_out: int
    txns_out: int
    txns_rejected: int
    reject_reasons: Dict[str, int] = field(default_factory=dict)
    entities_inferred: int = 0
    missing_field_pct: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def validate_and_normalize(ds: CanonicalDataset) -> Tuple[CanonicalDataset, ValidationReport]:
    rep = ValidationReport(entities_in=len(ds.entities), txns_in=len(ds.txns),
                           entities_out=0, txns_out=0, txns_rejected=0)
    seen_e: Dict[str, CanonicalEntity] = {}
    for e in ds.entities:
        eid = str(e.entity_id).strip()
        if not eid:
            continue
        e.entity_id = eid
        seen_e.setdefault(eid, e)

    good_txns = []
    referenced: set = set()
    for t in ds.txns:
        sup = str(t.supplier_id).strip() if t.supplier_id is not None else ""
        buy = str(t.buyer_id).strip() if t.buyer_id is not None else ""
        if not sup or not buy:
            rep.txns_rejected += 1
            rep.reject_reasons["missing_endpoint"] = rep.reject_reasons.get("missing_endpoint", 0) + 1
            continue
        if sup == buy:
            rep.txns_rejected += 1
            rep.reject_reasons["self_loop"] = rep.reject_reasons.get("self_loop", 0) + 1
            continue
        t.supplier_id, t.buyer_id = sup, buy
        for attr in ("taxable_value", "tax_amount", "total_value"):
            v = getattr(t, attr)
            if v is not None:
                setattr(t, attr, parse_amount(v))
        good_txns.append(t)
        referenced.add(sup)
        referenced.add(buy)

    final: Dict[str, CanonicalEntity] = {}
    for eid in referenced:
        if eid in seen_e:
            final[eid] = seen_e[eid]
        else:
            final[eid] = CanonicalEntity(entity_id=eid, source_id=eid.split(":", 1)[-1],
                                         name=eid, status="Unknown", kind="inferred_from_txn")
            rep.entities_inferred += 1
    orphaned = len(seen_e) - sum(1 for eid in seen_e if eid in referenced)

    ds.entities = list(final.values())
    ds.txns = good_txns
    rep.entities_out = len(ds.entities)
    rep.txns_out = len(ds.txns)
    if orphaned:
        rep.notes.append(f"{orphaned} entities dropped as edge-less after removing invalid transactions.")
    if rep.entities_inferred:
        rep.notes.append(f"{rep.entities_inferred} entities inferred from transaction endpoints.")

    n = max(1, len(ds.txns))
    def _miss(pred) -> float:
        return round(100.0 * sum(1 for t in ds.txns if pred(t)) / n, 1)
    rep.missing_field_pct = {
        "date": _miss(lambda t: not t.date),
        "taxable_value": _miss(lambda t: t.taxable_value is None),
        "tax_amount": _miss(lambda t: t.tax_amount is None),
        "label": _miss(lambda t: t.label is None),
        "status": _miss(lambda t: not t.status),
    }
    return ds, rep


# ── Feature-availability matrix ──────────────────────────────────────────────

@dataclass
class FeatureRow:
    feature: str
    required_fields: str
    available: bool
    can_run: str
    reason: str


def feature_availability(ds: CanonicalDataset) -> List[FeatureRow]:
    has_edges = len(ds.txns) > 0
    has_dates = any(t.date for t in ds.txns)
    has_tax = any(t.tax_amount is not None for t in ds.txns)
    has_labels = any(t.label is not None for t in ds.txns)
    has_filing = bool(ds.field_availability.get("filing_returns"))

    def row(f, req, avail, run, reason):
        return FeatureRow(f, req, avail, run, reason)
    return [
        row("Reconciliation (GSTR-1↔2B↔3B, ITC)", "GSTR filings + tax amounts", has_filing and has_tax,
            "YES" if (has_filing and has_tax) else "NO",
            "runs on filing + tax data" if (has_filing and has_tax)
            else "requires GSTR-1/2B/3B filing rows the source does not provide"),
        row("ITC-mismatch detection", "invoice tax vs claimed ITC", has_filing and has_tax,
            "YES" if (has_filing and has_tax) else "NO",
            "runs" if (has_filing and has_tax) else "needs statutory tax amounts and filed returns"),
        row("Ring / circular-trade detection", "directed supplier→buyer edges", has_edges,
            "YES" if has_edges else "NO",
            "the core graph capability; runs on the edge list" if has_edges else "no directed edges"),
        row("GSTIN / entity relationships", "entities + edges", has_edges,
            "YES" if has_edges else "NO",
            "neighbourhood + community structure" if has_edges else "no graph"),
        row("Temporal analysis", "per-transaction dates", has_dates,
            "YES" if has_dates else "NO",
            "runs on transaction timestamps" if has_dates
            else "source has no per-transaction dates → temporal engine skipped"),
        row("Risk scoring (composed)", "ring + temporal (+ reconcile/rules if filings)", has_edges,
            "PARTIAL" if has_edges else "NO",
            "ring + temporal scorers fire; reconcile/rules contribute ~0 without filing/status data"
            if has_edges else "no graph to score"),
        row("Graph embeddings (structural)", "graph structure", has_edges,
            "YES" if has_edges else "NO",
            "node2vec/PMI-SVD over the real graph" if has_edges else "no graph"),
        row("Ground-truth evaluation (precision/recall)", "fraud/ring labels", has_labels,
            "YES" if has_labels else "NO",
            "labels present → supervised eval" if has_labels
            else "no labels → UNSUPERVISED analysis only (no P/R/AUC)"),
    ]


def matrix_markdown(rows: List[FeatureRow]) -> str:
    out = ["| Feature | Available | Required fields | Can run? |", "|---|:--:|---|:--:|"]
    for r in rows:
        out.append(f"| {r.feature} | {'YES' if r.available else 'NO'} | {r.required_fields} | **{r.can_run}** |")
    return "\n".join(out)
