"""End-to-end test — generate a small dataset and inspect its shape."""
import json
import os
import tempfile

import pytest

from datagen.anomalies import inject_anomalies
from datagen.config import GenerationConfig
from datagen.emitters import emit
from datagen.network import sample_edges, sample_gstins
from datagen.rings import plant_rings
from datagen.transactions import derive_returns, sample_transactions


@pytest.fixture
def small_cfg(tmp_path):
    return GenerationConfig(
        n_gstins=200,
        months=2,
        n_rings=3,
        ring_size_min=3,
        ring_size_max=5,
        seed=123,
        out_dir=str(tmp_path / "out"),
    )


def test_config_validates(small_cfg):
    small_cfg.validate()  # must not raise


def test_config_bad_shares_raise():
    bad = GenerationConfig(
        normal_share=0.5,
        recon_issue_share=0.5,
        circular_share=0.1,
        duplicate_share=0.0,
    )
    with pytest.raises(ValueError):
        bad.validate()


def test_end_to_end(small_cfg):
    cfg = small_cfg
    gstins = sample_gstins(cfg)
    assert len(gstins) == cfg.n_gstins
    edges = sample_edges(cfg, gstins)
    assert len(edges) > 0
    bundles = sample_transactions(cfg, gstins, edges)
    assert len(bundles) > 0
    ring_bundles, ring_g1, ring_g3, ring_tp, planted_rings = plant_rings(cfg, gstins)
    ring_ids = {b.invoice.invoice_id for b in ring_bundles}
    bundles = bundles + ring_bundles
    g1, g3, g2b, tp = derive_returns(cfg, gstins, bundles)
    g1.extend(ring_g1); g3.extend(ring_g3); tp.extend(ring_tp)
    bundles, g1, g3, tp, planted_anoms = inject_anomalies(cfg, bundles, g1, g3, tp, ring_ids)
    counts = emit(cfg, gstins, bundles, g1, g3, g2b, tp, planted_anoms, planted_rings)

    # Expected CSVs exist
    for name in ("gstins.csv", "invoices.csv", "gstr1.csv", "gstr3b.csv",
                 "gstr2b.csv", "taxpayments.csv", "pr.csv", "ewb.csv",
                 "irn.csv", "truth.json"):
        assert os.path.exists(os.path.join(cfg.out_dir, name)), name

    # truth.json shape
    with open(os.path.join(cfg.out_dir, "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)
    assert "planted_rings" in truth
    assert "planted_anomalies" in truth
    assert truth["config"]["seed"] == cfg.seed
    # At least some rings landed
    assert 1 <= len(truth["planted_rings"]) <= cfg.n_rings


def test_deterministic(tmp_path):
    def run(seed, out):
        cfg = GenerationConfig(n_gstins=100, months=2, n_rings=2,
                                ring_size_min=3, ring_size_max=4,
                                seed=seed, out_dir=str(out))
        gstins = sample_gstins(cfg)
        edges = sample_edges(cfg, gstins)
        bundles = sample_transactions(cfg, gstins, edges)
        rb, rg1, rg3, rtp, pr = plant_rings(cfg, gstins)
        rings_ids = {b.invoice.invoice_id for b in rb}
        bundles += rb
        g1, g3, g2b, tp = derive_returns(cfg, gstins, bundles)
        g1 += rg1; g3 += rg3; tp += rtp
        bundles, g1, g3, tp, pa = inject_anomalies(cfg, bundles, g1, g3, tp, rings_ids)
        emit(cfg, gstins, bundles, g1, g3, g2b, tp, pa, pr)
        with open(os.path.join(cfg.out_dir, "invoices.csv"), "rb") as f:
            return f.read()
    a = run(999, tmp_path / "a")
    b = run(999, tmp_path / "b")
    assert a == b


def test_ring_invoices_labeled(small_cfg):
    cfg = small_cfg
    gstins = sample_gstins(cfg)
    ring_bundles, *_rest, planted = plant_rings(cfg, gstins)
    assert len(planted) >= 1
    for p in planted:
        assert p["type"] == "RING"
        assert p["size"] == len(p["members"])
        assert len(p["invoices"]) == p["size"]
