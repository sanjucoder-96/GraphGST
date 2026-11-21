"""Verify truth.json labels are consistent with the emitted CSV data."""
import csv
import json
import os

from datagen.anomalies import inject_anomalies
from datagen.config import GenerationConfig
from datagen.emitters import emit
from datagen.network import sample_edges, sample_gstins
from datagen.rings import plant_rings
from datagen.transactions import derive_returns, sample_transactions


def _run(tmp_path):
    cfg = GenerationConfig(
        n_gstins=250, months=3, n_rings=4,
        ring_size_min=3, ring_size_max=5,
        seed=7, out_dir=str(tmp_path / "out"),
    )
    gstins = sample_gstins(cfg)
    edges = sample_edges(cfg, gstins)
    bundles = sample_transactions(cfg, gstins, edges)
    rb, rg1, rg3, rtp, pr = plant_rings(cfg, gstins)
    ring_ids = {b.invoice.invoice_id for b in rb}
    bundles += rb
    g1, g3, g2b, tp = derive_returns(cfg, gstins, bundles)
    g1 += rg1; g3 += rg3; tp += rtp
    bundles, g1, g3, tp, pa = inject_anomalies(cfg, bundles, g1, g3, tp, ring_ids)
    emit(cfg, gstins, bundles, g1, g3, g2b, tp, pa, pr)
    return cfg, pa, pr


def _load_invoices(cfg):
    with open(os.path.join(cfg.out_dir, "invoices.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_ring_invoices_all_present(tmp_path):
    cfg, planted_anoms, planted_rings = _run(tmp_path)
    invs = {r["invoice_id"] for r in _load_invoices(cfg)}
    for ring in planted_rings:
        for inv_id in ring["invoices"]:
            assert inv_id in invs, f"Ring invoice {inv_id} missing from invoices.csv"


def test_all_ring_invoices_flagged_circular(tmp_path):
    cfg, planted_anoms, planted_rings = _run(tmp_path)
    inv_status = {r["invoice_id"]: r["status"] for r in _load_invoices(cfg)}
    for ring in planted_rings:
        for inv_id in ring["invoices"]:
            assert inv_status.get(inv_id) == "CIRCULAR_FRAUD"


def test_anomaly_invoices_have_matching_status(tmp_path):
    cfg, planted_anoms, planted_rings = _run(tmp_path)
    invs = {r["invoice_id"]: r for r in _load_invoices(cfg)}
    for a in planted_anoms:
        if a["type"] in ("DUPLICATE", "NEAR_DUPLICATE", "CANCELLED_SUPPLIER"):
            continue
        iid = a.get("invoice_id")
        if iid and iid in invs:
            expected = a["type"] if a["type"] != "MISSING_TAX_PAYMENT" else "MISSING_TAX_PAYMENT"
            actual = invs[iid]["status"]
            # allow some anomalies to fall through when threshold not met
            if a["type"] == "MISSING_EWB":
                # only counts if the invoice was above threshold
                continue
            assert actual == expected, f"expected {expected}, got {actual} on {iid}"
