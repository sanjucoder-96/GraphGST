"""Adapter: the "Iron Dealers" commercial-tax transaction dataset.

Source : https://github.com/Sindhuja-5/circular-trade-detection
Raw    : https://raw.githubusercontent.com/Sindhuja-5/circular-trade-detection/main/Iron_dealers_data.csv
What   : a REAL (non-synthetic) Indian commercial-tax dealer transaction graph
         used in circular-trading research. 130,535 transactions between 799
         anonymised dealers. Columns: `Seller ID, Buyer ID, Value`.
License: no LICENSE file in the source repo — treat as all-rights-reserved
         (research/testing only). NOT identifiable taxpayer data (dealers are
         anonymised integers, not GSTINs).

Deliberate limitations (recorded, never papered over): no dates → temporal
disabled; no invoice ids → synthesised deterministically; no tax → reconciliation
/ ITC disabled ("value" is the transaction value, NOT GST); no labels →
UNSUPERVISED ring analysis only.
"""
from __future__ import annotations

import csv
import os
import urllib.request
from typing import Optional

from ..schemas.canonical import (
    CanonicalDataset, CanonicalEntity, CanonicalTxn, FieldMapping, canonical_gstin_id,
)

RAW_URL = ("https://raw.githubusercontent.com/Sindhuja-5/"
           "circular-trade-detection/main/Iron_dealers_data.csv")
TAG = "IRONDLR"
_RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw", "iron_dealers")
RAW_PATH = os.path.join(_RAW_DIR, "Iron_dealers_data.csv")

MAPPING = [
    FieldMapping("Seller ID", "supplier_id", "(:GSTIN {gstin_id})", "rings, risk, embeddings",
                 "canonicalised as IRONDLR:<id>; anonymised integer, not a GSTIN"),
    FieldMapping("Buyer ID", "buyer_id", "(:Invoice)-[:BILLED_TO]->(:GSTIN)", "rings, reconcile"),
    FieldMapping("(row index)", "txn_id", "(:GSTIN)-[:ISSUED_INVOICE]->(:Invoice)", "rings, reconcile",
                 "synthesised — source has no invoice id"),
    FieldMapping("Value", "taxable_value", "Invoice.taxable_value / Invoice.amount", "rings (value signal), risk",
                 "transaction VALUE, not GST (no tax split in source)"),
]


def ensure_downloaded(path: str = RAW_PATH, url: str = RAW_URL) -> str:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    urllib.request.urlretrieve(url, path)
    return path


def load(raw_path: Optional[str] = None, limit: Optional[int] = None) -> CanonicalDataset:
    path = raw_path or ensure_downloaded()
    entities: dict = {}
    txns = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                break
            seller = (row.get("Seller ID") or "").strip()
            buyer = (row.get("Buyer ID") or "").strip()
            val = (row.get("Value") or "").strip()
            if not seller or not buyer:
                continue
            sup_id = canonical_gstin_id(TAG, seller)
            buy_id = canonical_gstin_id(TAG, buyer)
            for src, node in ((seller, sup_id), (buyer, buy_id)):
                if node not in entities:
                    entities[node] = CanonicalEntity(entity_id=node, source_id=src,
                                                     name=f"Dealer {src}", status="Unknown", kind="dealer")
            try:
                value = float(val) if val else None
            except ValueError:
                value = None
            txns.append(CanonicalTxn(txn_id=f"{TAG}-TXN-{i:06d}", supplier_id=sup_id,
                                     buyer_id=buy_id, date=None, taxable_value=value,
                                     tax_amount=None, label=None))

    return CanonicalDataset(
        name="iron_dealers",
        source_url="https://github.com/Sindhuja-5/circular-trade-detection",
        license="No license file (treat as all-rights-reserved; research/testing use only)",
        description=("Real (non-synthetic) Indian commercial-tax dealer transaction graph used in "
                     "circular-trading research: 130,535 directed seller→buyer transactions between "
                     "799 anonymised dealers. Anonymised dealer integers (NOT GSTINs)."),
        is_real_taxpayer_data=False, tag=TAG,
        entities=list(entities.values()), txns=txns, mapping=MAPPING,
        field_availability={"dates": False, "invoice_ids": False, "tax_amounts": False,
                            "filing_returns": False, "labels": False,
                            "supplier_buyer_edges": True, "amounts": True},
        notes=("Genuine (non-synthetic) transactions, but anonymised: dealer ids are integers, not "
               "GSTINs; no dates, tax split, filings or fraud labels. Suitable for UNSUPERVISED "
               "ring/graph analysis only."),
    )
