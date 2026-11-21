"""Transaction sampler.

Given the sampled network (list of GSTINRecords + supplier→buyer edges),
this module emits per-invoice records + the return / payment / EWB / IRN
records they generate.

Everything is stored in the pure-data records defined here; there is no
Neo4j dependency in this file. The loader turns records into Cypher.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Optional

from .catalog import BANKS, HSN_CATALOG, SECTOR_TO_HSN, TRANSPORTERS
from .config import GenerationConfig
from .identifiers import (synth_challan, synth_ewb, synth_irn, synth_return_id,
                          synth_utr, synth_vehicle)
from .network import GSTINRecord
from .rng import derive


# ────────────────────────────────────────────────────────────────────────
# Record dataclasses. Each mirrors a CSV column set.
# ────────────────────────────────────────────────────────────────────────

@dataclass
class InvoiceRec:
    invoice_id: str
    supplier_gstin: str
    buyer_gstin: str
    date: str
    hsn: str
    description: str
    taxable_value: float
    cgst: float
    sgst: float
    igst: float
    total_gst: float
    place_of_supply: str  # state code of buyer
    ewb_required: bool
    status: str = "MATCHED"       # overwritten by anomalies/rings
    scenario: str = "NORMAL"      # tagged when planted
    period: str = ""              # 'YYYY-MM'


@dataclass
class GSTR1Rec:
    return_id: str
    gstin: str
    period: str
    filed_date: str
    filed_status: str = "FILED"


@dataclass
class GSTR3BRec:
    return_id: str
    gstin: str
    period: str
    filed_date: str
    tax_paid_status: str = "PAID"
    tax_paid: float = 0.0
    itc_claimed: float = 0.0


@dataclass
class GSTR2BRec:
    return_id: str
    gstin: str
    period: str


@dataclass
class TaxPaymentRec:
    challan_no: str
    gstr3b_return_id: str
    payment_date: str
    amount_paid: float
    cgst_paid: float = 0.0
    sgst_paid: float = 0.0
    igst_paid: float = 0.0
    bank: str = ""
    utr: str = ""
    status: str = "CLEARED"


@dataclass
class EWayBillRec:
    ewb_id: str
    invoice_id: str
    vehicle_number: str
    distance_km: int
    from_pin: str
    to_pin: str
    valid_until: str
    transporter: str
    phantom: bool = False
    scenario: str = ""


@dataclass
class IRNRec:
    irn: str
    invoice_id: str
    generated_at: str
    portal_status: str = "ACTIVE"


@dataclass
class PurchaseRegisterRec:
    """Buyer-side book entry. Enables symmetric reconciliation in V6."""
    pr_line_id: str
    buyer_gstin: str
    invoice_id: str
    booked_date: str
    booked_amount: float
    booked_tax: float


@dataclass
class TransactionBundle:
    """Everything a single sampled invoice produces."""
    invoice: InvoiceRec
    ewb: Optional[EWayBillRec]
    irn: IRNRec
    pr: PurchaseRegisterRec

    def as_rows(self) -> dict:
        return {
            "invoice": asdict(self.invoice),
            "ewb": asdict(self.ewb) if self.ewb else None,
            "irn": asdict(self.irn),
            "pr": asdict(self.pr),
        }


# ────────────────────────────────────────────────────────────────────────
# Sampling helpers
# ────────────────────────────────────────────────────────────────────────

def _period_dates(start: date, months: int) -> list[str]:
    out = []
    y, m = start.year, start.month
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _sample_hsn_for_sector(rng: random.Random, sector: str) -> str:
    return rng.choice(SECTOR_TO_HSN.get(sector, list(HSN_CATALOG.keys())))


def _sample_amount(rng: random.Random, cfg: GenerationConfig) -> float:
    """Log-normal invoice amount."""
    v = rng.lognormvariate(cfg.amount_lognorm_mu, cfg.amount_lognorm_sigma)
    # round to nearest 100 for readability
    return round(v / 100) * 100


def _split_tax(amount: float, rate: float, same_state: bool) -> tuple[float, float, float, float]:
    """Return (cgst, sgst, igst, total_gst) rounded to 2 decimals."""
    total = round(amount * rate, 2)
    if same_state:
        half = round(total / 2, 2)
        return half, total - half, 0.0, total
    return 0.0, 0.0, total, total


def _date_in_period(rng: random.Random, period_ym: str) -> date:
    y, m = map(int, period_ym.split("-"))
    # days per month roughly — we don't need calendar rigor
    dpm = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, rng.randint(1, dpm))


# ────────────────────────────────────────────────────────────────────────
# Main sampler
# ────────────────────────────────────────────────────────────────────────

def sample_transactions(
    cfg: GenerationConfig,
    gstins: list[GSTINRecord],
    edges: list[tuple[str, str]],
) -> list[TransactionBundle]:
    """For each edge (supplier→buyer) draw between 0 and K invoices over
    the simulated months. Returns pure-data bundles.

    The number of invoices per edge follows Poisson(1) — most edges see
    a few invoices per period; some see many.
    """
    rng = derive(cfg.seed, "transactions.sample")
    by_id: dict[str, GSTINRecord] = {g.gstin_id: g for g in gstins}
    periods = _period_dates(cfg.start_date(), cfg.months)
    bundles: list[TransactionBundle] = []
    inv_counter = 0
    ewb_counter = 0
    for supplier_id, buyer_id in edges:
        sup = by_id[supplier_id]
        buy = by_id[buyer_id]
        for period in periods:
            n = _poisson(rng, lam=1.0)
            for _ in range(n):
                inv_counter += 1
                ewb_counter += 1
                bundle = _one_invoice(rng, cfg, sup, buy, period, inv_counter, ewb_counter)
                bundles.append(bundle)
    return bundles


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's Poisson sampler; fine for small lam."""
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


def _one_invoice(
    rng: random.Random,
    cfg: GenerationConfig,
    sup: GSTINRecord,
    buy: GSTINRecord,
    period: str,
    inv_seq: int,
    ewb_seq: int,
) -> TransactionBundle:
    hsn = _sample_hsn_for_sector(rng, sup.sector)
    info = HSN_CATALOG[hsn]
    amt = _sample_amount(rng, cfg)
    same_state = sup.state_code == buy.state_code
    cgst, sgst, igst, total_gst = _split_tax(amt, info["rate"], same_state)
    inv_dt = _date_in_period(rng, period)
    inv_id = f"INV-{inv_dt.strftime('%Y%m')}-{inv_seq:08d}"
    ewb_required = amt >= cfg.ewb_threshold_amount

    # EWB
    ewb: Optional[EWayBillRec] = None
    if ewb_required:
        ewb = EWayBillRec(
            ewb_id=synth_ewb(rng, ewb_seq),
            invoice_id=inv_id,
            vehicle_number=synth_vehicle(rng),
            distance_km=rng.randint(20, 2200),
            from_pin=sup.pincode,
            to_pin=buy.pincode,
            valid_until=(inv_dt + timedelta(days=3)).isoformat(),
            transporter=rng.choice(TRANSPORTERS),
            phantom=False,
            scenario="",
        )
    # IRN — required for taxpayers > ₹5cr turnover; treat as always present in demo
    irn = IRNRec(
        irn=synth_irn(rng),
        invoice_id=inv_id,
        generated_at=inv_dt.isoformat() + "T10:00:00",
    )
    # Purchase Register — buyer-side book entry, may differ later via anomalies
    pr = PurchaseRegisterRec(
        pr_line_id=f"PR-{inv_id}",
        buyer_gstin=buy.gstin_id,
        invoice_id=inv_id,
        booked_date=inv_dt.isoformat(),
        booked_amount=amt,
        booked_tax=total_gst,
    )

    inv = InvoiceRec(
        invoice_id=inv_id,
        supplier_gstin=sup.gstin_id,
        buyer_gstin=buy.gstin_id,
        date=inv_dt.isoformat(),
        hsn=hsn,
        description=info["label"],
        taxable_value=amt,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        total_gst=total_gst,
        place_of_supply=buy.state_code,
        ewb_required=ewb_required,
        status="MATCHED",
        scenario="NORMAL",
        period=period,
    )
    return TransactionBundle(invoice=inv, ewb=ewb, irn=irn, pr=pr)


# ────────────────────────────────────────────────────────────────────────
# Returns / payments generator — derived from invoices, not sampled fresh
# ────────────────────────────────────────────────────────────────────────

def derive_returns(
    cfg: GenerationConfig,
    gstins: list[GSTINRecord],
    bundles: list[TransactionBundle],
) -> tuple[list[GSTR1Rec], list[GSTR3BRec], list[GSTR2BRec], list[TaxPaymentRec]]:
    rng = derive(cfg.seed, "transactions.returns")
    by_supplier_period: dict[tuple[str, str], list[InvoiceRec]] = {}
    by_buyer_period: dict[tuple[str, str], list[InvoiceRec]] = {}
    for b in bundles:
        by_supplier_period.setdefault((b.invoice.supplier_gstin, b.invoice.period), []).append(b.invoice)
        by_buyer_period.setdefault((b.invoice.buyer_gstin, b.invoice.period), []).append(b.invoice)

    gstr1s: list[GSTR1Rec] = []
    gstr3bs: list[GSTR3BRec] = []
    gstr2bs: list[GSTR2BRec] = []
    taxpays: list[TaxPaymentRec] = []
    challan_seq = 0
    for (supplier, period), invs in by_supplier_period.items():
        filed_dt = f"{period}-11"
        gstr1s.append(GSTR1Rec(
            return_id=synth_return_id("GSTR1", supplier, period),
            gstin=supplier, period=period, filed_date=filed_dt,
        ))
        tax_paid = round(sum(i.total_gst for i in invs), 2)
        g3b_id = synth_return_id("GSTR3B", supplier, period)
        gstr3bs.append(GSTR3BRec(
            return_id=g3b_id, gstin=supplier, period=period,
            filed_date=f"{period}-20", tax_paid_status="PAID", tax_paid=tax_paid,
        ))
        if tax_paid > 0:
            challan_seq += 1
            taxpays.append(TaxPaymentRec(
                challan_no=synth_challan(rng, period.replace("-", ""), challan_seq),
                gstr3b_return_id=g3b_id,
                payment_date=f"{period}-20",
                amount_paid=tax_paid,
                cgst_paid=round(sum(i.cgst for i in invs), 2),
                sgst_paid=round(sum(i.sgst for i in invs), 2),
                igst_paid=round(sum(i.igst for i in invs), 2),
                bank=rng.choice(BANKS),
                utr=synth_utr(rng),
                status="CLEARED",
            ))
    for (buyer, period), invs in by_buyer_period.items():
        gstr2bs.append(GSTR2BRec(
            return_id=synth_return_id("GSTR2B", buyer, period),
            gstin=buyer, period=period,
        ))
    return gstr1s, gstr3bs, gstr2bs, taxpays
