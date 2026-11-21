"""Unit tests for the realdata/ ingestion + evaluation layer.

All in-memory: no Neo4j, no network. Covers adapter mapping, validation,
anonymization, idempotency, graph integrity, dataset isolation, engine
compatibility, and privacy guarantees (Phase 10).
"""
from __future__ import annotations

import csv
import os

import pytest

from realdata.schemas.canonical import (
    CanonicalDataset, CanonicalEntity, CanonicalTxn, FieldMapping,
    canonical_gstin_id, to_ring_graph_source, write_canonical_csvs,
)
from realdata.validation.quality import (
    validate_and_normalize, feature_availability, quality_report,
)
from realdata.normalization.anonymize import anonymize_dataset, pseudonym
from realdata.normalization.normalize import is_valid_gstin
from realdata import evaluate as ev


def _ring_dataset(labeled=False, dated=False) -> CanonicalDataset:
    tag = "TST"
    ids = {n: canonical_gstin_id(tag, n) for n in ("A", "B", "C", "D")}
    ents = [CanonicalEntity(entity_id=v, source_id=k, name=f"E{k}") for k, v in ids.items()]
    edges = [("A", "B"), ("B", "C"), ("C", "A"), ("A", "D")]
    txns = []
    for i, (s, d) in enumerate(edges):
        txns.append(CanonicalTxn(
            txn_id=f"{tag}-{i}", supplier_id=ids[s], buyer_id=ids[d],
            date=(f"2024-01-{i+1:02d}" if dated else None), taxable_value=1000.0 + i,
            label=(1 if (labeled and (s, d) in {("A", "B"), ("B", "C"), ("C", "A")}) else (0 if labeled else None))))
    return CanonicalDataset(name="tst", source_url="x", license="x", description="x",
                            is_real_taxpayer_data=False, tag=tag, entities=ents, txns=txns,
                            mapping=[FieldMapping("Seller", "supplier_id", "(:GSTIN)", "rings")],
                            field_availability={"filing_returns": False})


# ── canonical id + GSTIN validator ───────────────────────────────────────────

def test_canonical_id_is_not_a_real_gstin():
    cid = canonical_gstin_id("IRONDLR", "1309")
    assert cid == "IRONDLR:1309" and not is_valid_gstin(cid)


def test_gstin_validator():
    assert is_valid_gstin("29ABCDE1234F1Z5")     # well-formed
    assert not is_valid_gstin("IRONDLR:1309")
    assert not is_valid_gstin("29ABCDE1234F1Z")  # too short


# ── validation ───────────────────────────────────────────────────────────────

def test_validate_drops_self_loops_and_missing_endpoints():
    tag = "TST"
    a, b = canonical_gstin_id(tag, "A"), canonical_gstin_id(tag, "B")
    ds = CanonicalDataset("t", "", "", "", False, tag,
                          entities=[CanonicalEntity(a, "A"), CanonicalEntity(b, "B")],
                          txns=[CanonicalTxn("t0", a, b, taxable_value=10),
                                CanonicalTxn("t1", a, a, taxable_value=10),
                                CanonicalTxn("t2", a, "", taxable_value=10)])
    ds, rep = validate_and_normalize(ds)
    assert rep.txns_out == 1
    assert rep.reject_reasons.get("self_loop") == 1
    assert rep.reject_reasons.get("missing_endpoint") == 1


def test_validate_prunes_edgeless_entities():
    tag = "TST"
    a, b, c = (canonical_gstin_id(tag, x) for x in ("A", "B", "C"))
    ds = CanonicalDataset("t", "", "", "", False, tag,
                          entities=[CanonicalEntity(a, "A"), CanonicalEntity(b, "B"), CanonicalEntity(c, "C")],
                          txns=[CanonicalTxn("t0", a, b)])
    ds, _ = validate_and_normalize(ds)
    assert {e.entity_id for e in ds.entities} == {a, b}


# ── comprehensive quality report ─────────────────────────────────────────────

def test_quality_report_counts_and_issues():
    ds = _ring_dataset(dated=False)
    q = quality_report(ds)
    assert q.records == 4 and q.unique_taxpayers == 4
    assert q.self_loops == 0
    assert q.field_coverage_pct["date"] == 0.0
    # unlabeled + undated + no tax -> those three issues are surfaced
    joined = " ".join(q.issues)
    assert "UNSUPERVISED" in joined and "temporal" in joined


# ── feature availability ─────────────────────────────────────────────────────

def test_feature_matrix_unsupervised():
    ds, _ = validate_and_normalize(_ring_dataset(labeled=False, dated=False))
    can = {r.feature: r.can_run for r in feature_availability(ds)}
    assert can["Ring / circular-trade detection"] == "YES"
    assert can["Temporal analysis"] == "NO"
    assert can["Ground-truth evaluation (precision/recall)"] == "NO"


def test_feature_matrix_labeled_and_dated():
    ds, _ = validate_and_normalize(_ring_dataset(labeled=True, dated=True))
    can = {r.feature: r.can_run for r in feature_availability(ds)}
    assert can["Temporal analysis"] == "YES"
    assert can["Ground-truth evaluation (precision/recall)"] == "YES"


# ── anonymization (Phase 4) ──────────────────────────────────────────────────

def test_anonymize_is_deterministic_and_preserves_topology():
    ds1, _ = validate_and_normalize(_ring_dataset())
    ds2, _ = validate_and_normalize(_ring_dataset())
    e_before = len(to_ring_graph_source(ds1)["edges"])
    anonymize_dataset(ds1)
    anonymize_dataset(ds2)
    # deterministic: same salt -> identical pseudonyms across runs (import idempotency)
    assert sorted(e.entity_id for e in ds1.entities) == sorted(e.entity_id for e in ds2.entities)
    # topology preserved: same number of edges, all endpoints still resolve to entities
    gs = to_ring_graph_source(ds1)
    assert len(gs["edges"]) == e_before
    ids = {e.entity_id for e in ds1.entities}
    assert all(e["src"] in ids and e["dst"] in ids for e in gs["edges"])


def test_anonymize_privacy_no_original_ids_leak():
    ds, _ = validate_and_normalize(_ring_dataset())
    originals = {e.source_id for e in ds.entities} | {e.name for e in ds.entities}
    anonymize_dataset(ds)
    for e in ds.entities:
        assert e.entity_id.startswith("ANON-")
        # original source id / name must be scrubbed
        assert e.source_id.startswith("ANON-") and e.name.startswith("ANON-")
    # no transaction endpoint reveals an original id
    for t in ds.txns:
        assert t.supplier_id.startswith("ANON-") and t.buyer_id.startswith("ANON-")


def test_pseudonym_salt_changes_mapping():
    assert pseudonym("29ABCDE1234F1Z5", b"salt-a") != pseudonym("29ABCDE1234F1Z5", b"salt-b")
    assert pseudonym("x", b"k") == pseudonym("x", b"k")   # stable


# ── graph integrity + dataset isolation ──────────────────────────────────────

def test_ring_graph_source_integrity():
    ds, _ = validate_and_normalize(_ring_dataset(dated=True))
    gs = to_ring_graph_source(ds)
    assert len(gs["edges"]) == len(ds.txns)
    from datetime import date as _d
    e = gs["edges"][0]
    assert set(("src", "dst", "invoice_id", "date", "amount", "gst_amount")) <= set(e)
    assert e["date"] is None or isinstance(e["date"], _d)


def test_dataset_id_isolation_written_to_csv(tmp_path):
    ds, _ = validate_and_normalize(_ring_dataset())
    write_canonical_csvs(ds, str(tmp_path), dataset_id="real_tst_v1")
    with open(os.path.join(str(tmp_path), "invoices.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and all(r["scenario"] == "real_tst_v1" for r in rows)
    with open(os.path.join(str(tmp_path), "gstins.csv"), encoding="utf-8") as f:
        grows = list(csv.DictReader(f))
    assert all(r["scenario"] == "real_tst_v1" for r in grows)


# ── engine compatibility: evaluate() runs the REAL engines ───────────────────

def test_evaluate_unsupervised_detects_ring_with_evidence():
    ds, _ = validate_and_normalize(_ring_dataset(labeled=False, dated=True))
    rep = ev.evaluate(ds, hop_max=4)
    assert rep["evaluation_mode"].startswith("UNSUPERVISED")
    assert rep["ring_detection"]["rings_detected"] >= 1
    # evidence chain exists and forms a closed walk with dates/amounts
    chains = rep["ring_detection"]["evidence_chains"]
    assert chains and len(chains[0]["chain"]) >= 2
    step = chains[0]["chain"][0]
    assert "from" in step and "to" in step and "invoice_id" in step


def test_evaluate_supervised_reports_metrics():
    ds, _ = validate_and_normalize(_ring_dataset(labeled=True, dated=True))
    rep = ev.evaluate(ds, hop_max=4)
    assert rep["evaluation_mode"].startswith("GROUND_TRUTH")
    prf = rep["supervised_evaluation"]["ring_membership_vs_labels"]
    assert prf["precision"] == 1.0 and prf["tp"] >= 3


# ── adapter smoke (skip if raw file absent) ──────────────────────────────────

def test_iron_dealers_adapter_declares_mapping():
    from realdata.adapters.iron_dealers import load, RAW_PATH, MAPPING
    assert MAPPING and all(isinstance(m, FieldMapping) for m in MAPPING)
    if not os.path.exists(RAW_PATH):
        pytest.skip("iron_dealers raw CSV not downloaded")
    ds = load(limit=200)
    assert ds.name == "iron_dealers" and ds.is_real_taxpayer_data is False
    assert all(t.date is None and t.label is None for t in ds.txns)
    assert ds.mapping  # canonical mapping present
