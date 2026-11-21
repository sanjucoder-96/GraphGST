"""Adapter: IBM "Transactions for Anti-Money Laundering" (AMLworld), HI-Small.

Source : Altman et al., NeurIPS 2023 — https://github.com/IBM/AML-Data
Mirror : https://huggingface.co/datasets/eexzzm/IBM-Transactions-for-Anti-Money-Laundering-HI-Small-Trans
License: CDLA-Sharing-1.0 (commercial use OK, share-alike).
What   : a large, published, LABELLED directed payment graph — 5,078,345
         transfers, 0.102% flagged `Is Laundering`, whose typologies include a
         "simple cycle" = the ground-truth analog of GST circular trading.

This is realistic SYNTHETIC financial-crime data, NOT real taxpayer data and NOT
GST. Used as the strongest legally-usable LABELLED graph so the ring detector +
risk scorer get a genuine ground-truth evaluation. "Laundering" is a documented
ANALOG of "GST circular trading", surfaced with a caveat in the report.

Sampling (deterministic, reproducible, no RNG): ALL laundering transactions are
kept; normal transactions are systematically down-sampled (every `normal_stride`th
row). The exact composition is logged in notes — nothing silently dropped.
"""
from __future__ import annotations

import csv
import io
import os
import zipfile
from typing import Optional

from ..schemas.canonical import (
    CanonicalDataset, CanonicalEntity, CanonicalTxn, FieldMapping, canonical_gstin_id,
)

RAW_URL = ("https://huggingface.co/datasets/eexzzm/"
           "IBM-Transactions-for-Anti-Money-Laundering-HI-Small-Trans/"
           "resolve/main/HI-Small_Trans.csv.zip")
TAG = "IBMAML"
_RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw", "ibm_aml")
RAW_ZIP = os.path.join(_RAW_DIR, "HI-Small_Trans.csv.zip")

C_TS, C_FROM_BANK, C_FROM_ACC, C_TO_BANK, C_TO_ACC = 0, 1, 2, 3, 4
C_AMT_RECV, C_RECV_CCY, C_AMT_PAID, C_PAY_CCY, C_FMT, C_LAUND = 5, 6, 7, 8, 9, 10

MAPPING = [
    FieldMapping("From Bank + Account", "supplier_id", "(:GSTIN {gstin_id})", "rings, risk, embeddings",
                 "concat → IBMAML:<bank>-<acct>; bank account, not a GSTIN"),
    FieldMapping("To Bank + Account", "buyer_id", "(:Invoice)-[:BILLED_TO]->(:GSTIN)", "rings, reconcile"),
    FieldMapping("Timestamp", "date", "Invoice.date", "temporal, rings", "minute-resolution → ISO date"),
    FieldMapping("Amount Paid", "taxable_value", "Invoice.taxable_value", "rings (value), risk",
                 "payment value, not GST"),
    FieldMapping("(row index)", "txn_id", "(:GSTIN)-[:ISSUED_INVOICE]->(:Invoice)", "rings, reconcile",
                 "synthesised — source has no invoice id"),
    FieldMapping("Is Laundering", "label", "(ground-truth, not a graph field)", "supervised evaluation",
                 "0/1 laundering flag; cycle typology = circular-trading analog"),
]


def ensure_downloaded(path: str = RAW_ZIP, url: str = RAW_URL) -> str:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    import urllib.request
    os.makedirs(os.path.dirname(path), exist_ok=True)
    urllib.request.urlretrieve(url, path)
    return path


def _iso(ts: str) -> Optional[str]:
    ts = (ts or "").strip()
    if len(ts) >= 10 and ts[4] == "/" and ts[7] == "/":
        return f"{ts[0:4]}-{ts[5:7]}-{ts[8:10]}"
    return None


def load(raw_path: Optional[str] = None, limit: Optional[int] = None,
         normal_stride: int = 40) -> CanonicalDataset:
    path = raw_path or ensure_downloaded()
    entities: dict = {}
    txns = []
    n_scanned = n_laund = n_normal_kept = 0

    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(name) as fh:
            reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8"))
            next(reader, None)
            for r in reader:
                if limit is not None and n_scanned >= limit:
                    break
                n_scanned += 1
                if len(r) <= C_LAUND:
                    continue
                try:
                    is_laund = int(r[C_LAUND])
                except ValueError:
                    is_laund = 0
                if is_laund:
                    n_laund += 1
                else:
                    if (n_scanned % normal_stride) != 0:
                        continue
                    n_normal_kept += 1
                from_src = f"{r[C_FROM_BANK].strip()}-{r[C_FROM_ACC].strip()}"
                to_src = f"{r[C_TO_BANK].strip()}-{r[C_TO_ACC].strip()}"
                sup_id = canonical_gstin_id(TAG, from_src)
                buy_id = canonical_gstin_id(TAG, to_src)
                for src, node in ((from_src, sup_id), (to_src, buy_id)):
                    if node not in entities:
                        entities[node] = CanonicalEntity(entity_id=node, source_id=src,
                                                         name=f"Account {src}", status="Unknown",
                                                         kind="bank_account")
                try:
                    amt = float(r[C_AMT_PAID])
                except ValueError:
                    amt = None
                txns.append(CanonicalTxn(txn_id=f"{TAG}-TXN-{n_scanned:08d}", supplier_id=sup_id,
                                         buyer_id=buy_id, date=_iso(r[C_TS]), taxable_value=amt,
                                         tax_amount=None, currency=r[C_PAY_CCY].strip() or None,
                                         label=is_laund,
                                         extra={"amount_received": r[C_AMT_RECV], "format": r[C_FMT]}))

    notes = (f"Deterministic sample of AMLworld HI-Small: scanned {n_scanned:,} source rows; kept ALL "
             f"{n_laund:,} laundering txns + every {normal_stride}th normal txn ({n_normal_kept:,} kept) "
             f"= {len(txns):,} transactions, {len(entities):,} accounts. Realistic SYNTHETIC AML "
             f"benchmark, NOT real taxpayer data; 'laundering' is a documented analog of GST circular trading.")
    return CanonicalDataset(
        name="ibm_aml",
        source_url="https://github.com/IBM/AML-Data",
        license="CDLA-Sharing-1.0 (commercial OK, share-alike)",
        description=("IBM AMLworld HI-Small: a published, labelled directed payment graph "
                     "(Altman et al., NeurIPS 2023). Directed From→To account transfers with "
                     "timestamps, amounts, and a per-transaction Is-Laundering label whose "
                     "typologies include a 'simple cycle' (ground-truth circular trading)."),
        is_real_taxpayer_data=False, tag=TAG,
        entities=list(entities.values()), txns=txns, mapping=MAPPING,
        field_availability={"dates": True, "invoice_ids": False, "tax_amounts": False,
                            "filing_returns": False, "labels": True,
                            "supplier_buyer_edges": True, "amounts": True},
        notes=notes,
    )
