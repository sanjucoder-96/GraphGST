"""Hard ring planter (audit Phase E).

Used only when `cfg.ring_difficulty > 0` (benchmarks). The demo uses the
legacy easy planter in `rings.py`, so HERO_RING stays byte-stable.

Adds, per ring, a random difficulty profile that DROPS tells:
  * shared vehicle kept only with prob (1 - difficulty)
  * shared director kept only with prob (1 - difficulty)
  * hop timing jittered across a wider window
  * hop amounts multiplied by lognormal noise (breaks geometric inflation)

A `ring_broken_share` fraction of rings omit the closing edge (near-rings /
broken rings) — ground-truthed separately; they must NOT be recovered as
closed rings.

`n_hard_negatives` legitimate cyclic trade communities are planted as HARD
NEGATIVES: a real cycle exists (Johnson finds it) but the characteristics
are legitimate (distinct vehicles/directors, wide timing, small margin added
per hop, not returned) so the six-signal scorer should rate them LOW.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

from .catalog import BANKS, HSN_CATALOG, SECTOR_TO_HSN
from .identifiers import (synth_challan, synth_director_id, synth_ewb,
                          synth_irn, synth_return_id, synth_utr, synth_vehicle)
from .rng import derive
from .rings import _pick_ring_members
from .transactions import (EWayBillRec, GSTR1Rec, GSTR3BRec, IRNRec,
                            InvoiceRec, PurchaseRegisterRec, TaxPaymentRec,
                            TransactionBundle)


def _emit_hop(*, sup, buy, inv_id, hop_dt, hsn, info, hop_amt, vehicle_number,
              rng, challan_seq, scenario, status, bundles, gstr1s, gstr3bs,
              taxpays, ewb_threshold):
    period = hop_dt.strftime("%Y-%m")
    same_state = sup.state_code == buy.state_code
    total_tax = round(hop_amt * info["rate"], 2)
    if same_state:
        cgst = round(total_tax / 2, 2); sgst = total_tax - cgst; igst = 0.0
    else:
        cgst = sgst = 0.0; igst = total_tax

    inv = InvoiceRec(
        invoice_id=inv_id, supplier_gstin=sup.gstin_id, buyer_gstin=buy.gstin_id,
        date=hop_dt.isoformat(), hsn=hsn, description=info["label"],
        taxable_value=hop_amt, cgst=cgst, sgst=sgst, igst=igst, total_gst=total_tax,
        place_of_supply=buy.state_code, ewb_required=hop_amt >= ewb_threshold,
        status=status, scenario=scenario, period=period)
    ewb = EWayBillRec(
        ewb_id=synth_ewb(rng, rng.randint(1, 9_999_999)), invoice_id=inv_id,
        vehicle_number=vehicle_number, distance_km=rng.randint(5, 600),
        from_pin=sup.pincode, to_pin=buy.pincode,
        valid_until=(hop_dt + timedelta(days=2)).isoformat(),
        transporter=rng.choice(["FastCargo", "BharatShip", "SpeedEx", "LocalHaul"]),
        phantom=False, scenario=scenario)
    irn = IRNRec(irn=synth_irn(rng), invoice_id=inv_id,
                 generated_at=hop_dt.isoformat() + "T10:00:00")
    pr = PurchaseRegisterRec(
        pr_line_id=f"PR-{inv_id}", buyer_gstin=buy.gstin_id, invoice_id=inv_id,
        booked_date=hop_dt.isoformat(), booked_amount=hop_amt, booked_tax=total_tax)
    bundles.append(TransactionBundle(invoice=inv, ewb=ewb, irn=irn, pr=pr))

    gstr1s.append(GSTR1Rec(return_id=synth_return_id("GSTR1", sup.gstin_id, period),
                           gstin=sup.gstin_id, period=period, filed_date=f"{period}-11"))
    g3b_id = synth_return_id("GSTR3B", sup.gstin_id, period)
    gstr3bs.append(GSTR3BRec(return_id=g3b_id, gstin=sup.gstin_id, period=period,
                             filed_date=f"{period}-20", tax_paid_status="PAID",
                             tax_paid=total_tax, itc_claimed=total_tax))
    taxpays.append(TaxPaymentRec(
        challan_no=synth_challan(rng, period.replace("-", ""), challan_seq),
        gstr3b_return_id=g3b_id, payment_date=f"{period}-20", amount_paid=total_tax,
        cgst_paid=cgst, sgst_paid=sgst, igst_paid=igst, bank=rng.choice(BANKS),
        utr=synth_utr(rng), status="CLEARED"))
    return total_tax


def plant_rings_hard(cfg, gstins):
    rng = derive(cfg.seed, "rings.plant.hard")
    diff = max(0.0, min(1.0, cfg.ring_difficulty))
    horizon_start = cfg.start_date()
    horizon_days = 30 * cfg.months
    plant_start = max(0, horizon_days - 30 * max(cfg.months // 2, 1))

    bundles = []; gstr1s = []; gstr3bs = []; taxpays = []; planted = []
    used: set[str] = set()
    inv_seq = 900_000_000; challan_seq = 800_000; dir_seq = 500_000

    for ring_ix in range(cfg.n_rings):
        k = rng.randint(cfg.ring_size_min, cfg.ring_size_max)
        members = _pick_ring_members(rng, gstins, k, used)
        if members is None:
            continue
        used.update(m.gstin_id for m in members)

        keep_vehicle = cfg.ring_common_vehicle and (rng.random() > diff)
        keep_director = cfg.ring_common_directors and (rng.random() > diff)
        is_broken = rng.random() < cfg.ring_broken_share

        for m in members:
            m.scenario = "CIRCULAR_TRADING"
        shared_dir = None
        if keep_director:
            shared_dir = synth_director_id(rng, dir_seq); dir_seq += 1
            for m in members:
                m.directors = [shared_dir]

        hsn = rng.choice(SECTOR_TO_HSN[members[0].sector]); info = HSN_CATALOG[hsn]
        start_offset = plant_start + rng.randint(0, max(1, horizon_days // 4))
        d0 = horizon_start + timedelta(days=start_offset)
        max_span = max(k, int(round((k - 1) * (1.0 + diff * 4.0))))
        offs = sorted(rng.randint(0, max_span) for _ in range(k))
        veh = synth_vehicle(rng)
        base_amt = round(rng.lognormvariate(cfg.amount_lognorm_mu + 1.5,
                                             cfg.amount_lognorm_sigma * 0.5) / 100) * 100

        n_edges = (k - 1) if is_broken else k
        ring_inv_ids: list[str] = []; ring_tax = 0.0
        for i in range(n_edges):
            sup = members[i]; buy = members[(i + 1) % k]
            hop_dt = d0 + timedelta(days=offs[i])
            infla = (1.0 + cfg.ring_value_inflation) ** i
            noise = math.exp(rng.gauss(0.0, diff * 0.3)) if diff > 0 else 1.0
            hop_amt = round(max(1000.0, base_amt * infla * noise), 2)
            inv_seq += 1; challan_seq += 1
            inv_id = f"INV-{hop_dt.strftime('%Y%m')}-HRING-{ring_ix:03d}-{i:02d}"
            ring_inv_ids.append(inv_id)
            ring_tax += _emit_hop(
                sup=sup, buy=buy, inv_id=inv_id, hop_dt=hop_dt, hsn=hsn, info=info,
                hop_amt=hop_amt,
                vehicle_number=(veh if keep_vehicle else synth_vehicle(rng)),
                rng=rng, challan_seq=challan_seq, scenario="CIRCULAR_TRADING",
                status="CIRCULAR_FRAUD", bundles=bundles, gstr1s=gstr1s,
                gstr3bs=gstr3bs, taxpays=taxpays, ewb_threshold=cfg.ewb_threshold_amount)

        planted.append({
            "type": "RING",
            "kind": "BROKEN_RING" if is_broken else "CLOSED_RING",
            "ring_id": f"RING-{cfg.seed}-{ring_ix:05d}",
            "size": k, "members": [m.gstin_id for m in members],
            "invoices": ring_inv_ids, "hsn": hsn, "broken": is_broken,
            "profile": {"shared_vehicle": keep_vehicle, "shared_director": keep_director,
                         "jittered": diff > 0, "amount_noise": diff > 0, "difficulty": diff},
            "common_vehicle": veh if keep_vehicle else None,
            "shared_director": shared_dir,
            "total_ring_gst": round(ring_tax, 2),
            "closure_start_date": d0.isoformat(),
        })

    # Hard negatives — legitimate cyclic trade communities.
    for hn_ix in range(cfg.n_hard_negatives):
        k = rng.randint(3, 4)
        members = _pick_ring_members(rng, gstins, k, used)
        if members is None:
            continue
        used.update(m.gstin_id for m in members)
        hsn = rng.choice(SECTOR_TO_HSN[members[0].sector]); info = HSN_CATALOG[hsn]
        hn_inv_ids: list[str] = []
        base_amt = round(rng.lognormvariate(cfg.amount_lognorm_mu,
                                             cfg.amount_lognorm_sigma) / 100) * 100
        for i in range(k):
            sup = members[i]; buy = members[(i + 1) % k]
            hop_dt = horizon_start + timedelta(days=rng.randint(0, max(1, horizon_days - 1)))
            hop_amt = round(max(1000.0, base_amt * (1.0 + 0.05 * i)
                                 * math.exp(rng.gauss(0, 0.25))), 2)
            inv_seq += 1; challan_seq += 1
            inv_id = f"INV-{hop_dt.strftime('%Y%m')}-HNEG-{hn_ix:03d}-{i:02d}"
            hn_inv_ids.append(inv_id)
            _emit_hop(
                sup=sup, buy=buy, inv_id=inv_id, hop_dt=hop_dt, hsn=hsn, info=info,
                hop_amt=hop_amt, vehicle_number=synth_vehicle(rng), rng=rng,
                challan_seq=challan_seq, scenario="LEGIT_DENSE", status="MATCHED",
                bundles=bundles, gstr1s=gstr1s, gstr3bs=gstr3bs, taxpays=taxpays,
                ewb_threshold=cfg.ewb_threshold_amount)
        planted.append({
            "type": "HARD_NEGATIVE", "kind": "HARD_NEGATIVE",
            "ring_id": f"HNEG-{cfg.seed}-{hn_ix:05d}",
            "size": k, "members": [m.gstin_id for m in members],
            "invoices": hn_inv_ids, "hsn": hsn,
            "note": "legitimate cyclic trade community (low-signal negative)",
        })

    return bundles, gstr1s, gstr3bs, taxpays, planted
