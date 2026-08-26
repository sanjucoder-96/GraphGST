"""CSV + truth.json emitters.

Each `write_*` function is idempotent — repeatedly calling it with the
same data overwrites the file byte-for-byte identical.

CSVs are minimal (no BOM, LF line terminators, quoted only where needed)
so pandas / DuckDB / Excel can all read them. Field order is stable so
diffing two runs is meaningful.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Iterable

from .config import GenerationConfig
from .network import GSTINRecord
from .transactions import (EWayBillRec, GSTR1Rec, GSTR2BRec, GSTR3BRec,
                            IRNRec, PurchaseRegisterRec, TaxPaymentRec,
                            TransactionBundle)


def _write_dicts(path: str, rows: Iterable[dict], columns: list[str]) -> int:
    """Write rows to CSV; return count."""
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
            n += 1
    return n


def emit(
    cfg: GenerationConfig,
    gstins: list[GSTINRecord],
    bundles: list[TransactionBundle],
    gstr1s: list[GSTR1Rec],
    gstr3bs: list[GSTR3BRec],
    gstr2bs: list[GSTR2BRec],
    taxpays: list[TaxPaymentRec],
    planted_anomalies: list[dict],
    planted_rings: list[dict],
) -> dict:
    os.makedirs(cfg.out_dir, exist_ok=True)
    p = lambda name: os.path.join(cfg.out_dir, name)  # noqa: E731

    counts = {}
    counts["gstins.csv"] = _write_dicts(
        p("gstins.csv"), (g.to_row() for g in gstins),
        columns=[
            "gstin_id", "name", "state_code", "state", "pincode", "sector",
            "status", "cancellation_date", "incorp_date", "directors", "scenario",
        ],
    )
    counts["invoices.csv"] = _write_dicts(
        p("invoices.csv"), (asdict(b.invoice) for b in bundles),
        columns=[
            "invoice_id", "supplier_gstin", "buyer_gstin", "date",
            "hsn", "description", "taxable_value", "cgst", "sgst",
            "igst", "total_gst", "place_of_supply", "ewb_required",
            "status", "scenario", "period",
        ],
    )
    counts["ewb.csv"] = _write_dicts(
        p("ewb.csv"), (asdict(b.ewb) for b in bundles if b.ewb),
        columns=[
            "ewb_id", "invoice_id", "vehicle_number", "distance_km",
            "from_pin", "to_pin", "valid_until", "transporter",
            "phantom", "scenario",
        ],
    )
    counts["irn.csv"] = _write_dicts(
        p("irn.csv"), (asdict(b.irn) for b in bundles),
        columns=["irn", "invoice_id", "generated_at", "portal_status"],
    )
    counts["pr.csv"] = _write_dicts(
        p("pr.csv"), (asdict(b.pr) for b in bundles),
        columns=[
            "pr_line_id", "buyer_gstin", "invoice_id",
            "booked_date", "booked_amount", "booked_tax",
        ],
    )
    counts["gstr1.csv"] = _write_dicts(
        p("gstr1.csv"), (asdict(g) for g in gstr1s),
        columns=["return_id", "gstin", "period", "filed_date", "filed_status"],
    )
    counts["gstr3b.csv"] = _write_dicts(
        p("gstr3b.csv"), (asdict(g) for g in gstr3bs),
        columns=["return_id", "gstin", "period", "filed_date",
                  "tax_paid_status", "tax_paid", "itc_claimed"],
    )
    counts["gstr2b.csv"] = _write_dicts(
        p("gstr2b.csv"), (asdict(g) for g in gstr2bs),
        columns=["return_id", "gstin", "period"],
    )
    counts["taxpayments.csv"] = _write_dicts(
        p("taxpayments.csv"), (asdict(t) for t in taxpays),
        columns=[
            "challan_no", "gstr3b_return_id", "payment_date",
            "amount_paid", "cgst_paid", "sgst_paid", "igst_paid",
            "bank", "utr", "status",
        ],
    )

    # Split ring truth by kind. Legacy entries have no `kind` → all closed
    # rings. `planted_rings` stays the CLOSED-ring recall target; broken and
    # hard-negative communities are recorded separately for FP measurement.
    closed = [r for r in planted_rings if r.get("kind", "CLOSED_RING") == "CLOSED_RING"]
    near = [r for r in planted_rings if r.get("kind") == "BROKEN_RING"]
    hardneg = [r for r in planted_rings if r.get("kind") == "HARD_NEGATIVE"]
    truth = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": cfg.to_dict(),
        "counts": counts,
        "planted_rings": closed,
        "planted_near_rings": near,
        "hard_negatives": hardneg,
        "planted_anomalies": planted_anomalies,
    }
    with open(p("truth.json"), "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=2, ensure_ascii=False)
    counts["truth.json"] = 1
    return counts
