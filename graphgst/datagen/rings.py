"""Ring planter — inject `cfg.n_rings` circular trading rings with truth.

Each ring is planted as follows:

1. Pick `k` ring members from the GSTIN pool (prefer same state, active
   status, and — if ring_common_directors — force one shared Director).
2. Choose a start date in the second half of the simulated horizon.
3. Emit `k` invoices arranged head-to-tail:
        R_0 → R_1 → R_2 → … → R_{k-1} → R_0
   with dates spaced 1 day apart and invoice values inflated by
   `ring_value_inflation` per hop (SC9 signature).
4. Emit `k` EWBs all bearing the same vehicle number if
   `ring_common_vehicle`.
5. Emit GSTR-1, GSTR-3B, TaxPayment records that make the chain look
   legitimate at first glance — the "polished ring".
6. Record ground truth for every ring and every ring invoice.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional

from .catalog import BANKS, HSN_CATALOG, SECTOR_TO_HSN
from .config import GenerationConfig
from .identifiers import (synth_challan, synth_director_id, synth_ewb,
                          synth_irn, synth_return_id, synth_utr, synth_vehicle)
from .network import GSTINRecord
from .rng import derive
from .transactions import (EWayBillRec, GSTR1Rec, GSTR3BRec, IRNRec,
                            InvoiceRec, PurchaseRegisterRec, TaxPaymentRec,
                            TransactionBundle)


def _pick_ring_members(
    rng: random.Random,
    gstins: list[GSTINRecord],
    k: int,
    already_used: set[str],
) -> Optional[list[GSTINRecord]]:
    # Prefer same-state active taxpayers so the ring is geographically tight.
    by_state: dict[str, list[GSTINRecord]] = {}
    for g in gstins:
        if g.status != "Active" or g.gstin_id in already_used:
            continue
        by_state.setdefault(g.state_code, []).append(g)
    states_sorted = sorted(by_state.items(), key=lambda kv: -len(kv[1]))
    for _, pool in states_sorted:
        if len(pool) >= k:
            return rng.sample(pool, k=k)
    return None


def plant_rings(
    cfg: GenerationConfig,
    gstins: list[GSTINRecord],
) -> tuple[
    list[TransactionBundle], list[GSTR1Rec], list[GSTR3BRec],
    list[TaxPaymentRec], list[dict],
]:
    """Return (bundles, gstr1s, gstr3bs, taxpays, planted_truth)."""
    rng = derive(cfg.seed, "rings.plant")
    horizon_start = cfg.start_date()
    horizon_days = 30 * cfg.months
    ring_planting_start_offset = max(0, horizon_days - 30 * max(cfg.months // 2, 1))

    bundles: list[TransactionBundle] = []
    gstr1s: list[GSTR1Rec] = []
    gstr3bs: list[GSTR3BRec] = []
    taxpays: list[TaxPaymentRec] = []
    planted: list[dict] = []

    used: set[str] = set()
    ewb_seq = 900_000_000     # reserve a separate range so ring EWBs are recognizable in debug
    inv_seq = 900_000_000
    challan_seq = 800_000
    dir_seq = 500_000
    for ring_ix in range(cfg.n_rings):
        k = rng.randint(cfg.ring_size_min, cfg.ring_size_max)
        members = _pick_ring_members(rng, gstins, k, used)
        if members is None:
            continue
        used.update(m.gstin_id for m in members)

        # Shared director between all ring members (shell-cluster signal)
        shared_dir = synth_director_id(rng, dir_seq)
        dir_seq += 1
        for m in members:
            m.directors = [shared_dir]  # collapse to shared director
            m.scenario = "CIRCULAR_TRADING"

        # Choose an HSN from the first member's sector so the story is coherent
        hsn = rng.choice(SECTOR_TO_HSN[members[0].sector])
        info = HSN_CATALOG[hsn]

        # Start date — anywhere in the last half of the horizon
        start_offset = ring_planting_start_offset + rng.randint(0, max(1, horizon_days // 4))
        d0 = horizon_start + timedelta(days=start_offset)
        period = d0.strftime("%Y-%m")

        # Shared vehicle
        veh = synth_vehicle(rng)

        # Base amount and inflation per hop
        base_amt = round(rng.lognormvariate(cfg.amount_lognorm_mu + 1.5,
                                             cfg.amount_lognorm_sigma * 0.5) / 100) * 100

        ring_invoice_ids: list[str] = []
        ring_total_fraud = 0.0

        # Ring id — deterministic hash so truth.json and Neo4j Ring node line up
        ring_id = f"RING-{cfg.seed}-{ring_ix:05d}"

        # Emit invoices head-to-tail
        for i, sup in enumerate(members):
            buy = members[(i + 1) % k]
            hop_dt = d0 + timedelta(days=i)
            inv_seq += 1
            ewb_seq += 1

            hop_amt = round(base_amt * ((1.0 + cfg.ring_value_inflation) ** i), 2)
            same_state = sup.state_code == buy.state_code
            total_tax = round(hop_amt * info["rate"], 2)
            if same_state:
                cgst = round(total_tax / 2, 2); sgst = total_tax - cgst; igst = 0.0
            else:
                cgst = sgst = 0.0; igst = total_tax
            inv_id = f"INV-{hop_dt.strftime('%Y%m')}-RING-{ring_ix:03d}-{i:02d}"

            inv = InvoiceRec(
                invoice_id=inv_id,
                supplier_gstin=sup.gstin_id,
                buyer_gstin=buy.gstin_id,
                date=hop_dt.isoformat(),
                hsn=hsn,
                description=info["label"] + " (ring)",
                taxable_value=hop_amt,
                cgst=cgst, sgst=sgst, igst=igst, total_gst=total_tax,
                place_of_supply=buy.state_code,
                ewb_required=hop_amt >= cfg.ewb_threshold_amount,
                status="CIRCULAR_FRAUD",
                scenario="CIRCULAR_TRADING",
                period=period,
            )
            ring_invoice_ids.append(inv_id)
            ring_total_fraud += total_tax

            ewb = EWayBillRec(
                ewb_id=synth_ewb(rng, ewb_seq),
                invoice_id=inv_id,
                vehicle_number=veh if cfg.ring_common_vehicle else synth_vehicle(rng),
                distance_km=rng.randint(5, 30),
                from_pin=sup.pincode,
                to_pin=buy.pincode,
                valid_until=(hop_dt + timedelta(days=1)).isoformat(),
                transporter="Ring Logistics",
                phantom=True,
                scenario="CIRCULAR_TRADING",
            )
            irn = IRNRec(
                irn=synth_irn(rng),
                invoice_id=inv_id,
                generated_at=hop_dt.isoformat() + "T10:00:00",
            )
            pr = PurchaseRegisterRec(
                pr_line_id=f"PR-{inv_id}",
                buyer_gstin=buy.gstin_id,
                invoice_id=inv_id,
                booked_date=hop_dt.isoformat(),
                booked_amount=hop_amt,
                booked_tax=total_tax,
            )
            bundles.append(TransactionBundle(invoice=inv, ewb=ewb, irn=irn, pr=pr))

            # Rings look "compliant" at first glance: file returns + pay tax
            gstr1s.append(GSTR1Rec(
                return_id=synth_return_id("GSTR1", sup.gstin_id, period),
                gstin=sup.gstin_id, period=period, filed_date=f"{period}-11",
            ))
            g3b_id = synth_return_id("GSTR3B", sup.gstin_id, period)
            gstr3bs.append(GSTR3BRec(
                return_id=g3b_id, gstin=sup.gstin_id, period=period,
                filed_date=f"{period}-20", tax_paid_status="PAID", tax_paid=total_tax,
                itc_claimed=total_tax,
            ))
            challan_seq += 1
            taxpays.append(TaxPaymentRec(
                challan_no=synth_challan(rng, period.replace("-", ""), challan_seq),
                gstr3b_return_id=g3b_id,
                payment_date=f"{period}-20",
                amount_paid=total_tax, cgst_paid=cgst, sgst_paid=sgst, igst_paid=igst,
                bank=rng.choice(BANKS), utr=synth_utr(rng), status="CLEARED",
            ))

        planted.append({
            "type": "RING",
            "ring_id": ring_id,
            "size": k,
            "members": [m.gstin_id for m in members],
            "invoices": ring_invoice_ids,
            "hsn": hsn,
            "hop_inflation": cfg.ring_value_inflation,
            "temporal_window_days": (k - 1),
            "common_vehicle": veh if cfg.ring_common_vehicle else None,
            "shared_director": shared_dir if cfg.ring_common_directors else None,
            "total_ring_gst": round(ring_total_fraud, 2),
            "closure_start_date": d0.isoformat(),
        })
    return bundles, gstr1s, gstr3bs, taxpays, planted
