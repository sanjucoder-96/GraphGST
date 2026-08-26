"""LIVE Neo4j integration tests (audit V6.2 — Part 1).

These are the real production-path tests the V6.1 report said were missing:
they drive an ACTUAL Neo4j database through the whole stack —
CSV → loader → persistence → read-back → ring detection → risk → FastAPI —
with no mocks. The V6.1 property-drift fix (`date`/`amount`/`total_gst`) is
proven here against a real database, not just an in-memory graph_source.

Gating
------
Marked `neo4j` and **deselected by default** (`pytest.ini` sets
`-m "not neo4j"`), so the fast unit stage never touches a database. Run them
explicitly in the integration stage with:

    pytest -m neo4j

They self-skip if no reachable Neo4j is configured (e.g. `.env` missing or the
instance is down), so `pytest -m neo4j` on a laptop without the DB is a skip,
not a failure.

WARNING: the module fixture WIPES the configured database and reloads a small
synthetic dataset. Point `NEO4J_*` at a disposable instance (the project's
dedicated Aura instance is fine — deterministic reset is by design).
"""
import tempfile

import pytest

import db

pytestmark = pytest.mark.neo4j


def _reachable() -> bool:
    try:
        db.get_driver().verify_connectivity()
        db.run_query("RETURN 1 AS ok")
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    if not _reachable():
        pytest.skip("no reachable Neo4j (NEO4J_* not configured or instance down)")
    from benchmarks.bench_risk_discrimination import _generate
    from datagen.config import GenerationConfig
    from datagen.loader import load_directory

    out = str(tmp_path_factory.mktemp("neo4j_ds"))
    _generate(GenerationConfig(n_gstins=150, months=2, n_rings=3,
                               ring_size_min=3, ring_size_max=4, seed=42, out_dir=out))
    db.run_write("MATCH (n) DETACH DELETE n")           # deterministic clean slate
    stats = load_directory(out)                         # constraints + all CSVs
    yield {"dir": out, "stats": stats}
    db.close_driver()


# ── 1. connection ──────────────────────────────────────────────────────
def test_connection(live):
    assert db.run_query("RETURN 1 AS ok")[0]["ok"] == 1


# ── 2. schema: constraints ─────────────────────────────────────────────
def test_constraints_exist(live):
    names = {c["name"] for c in db.run_query("SHOW CONSTRAINTS YIELD name RETURN name")}
    # At least the load-critical uniqueness constraints must be present.
    labels = {tuple(c["labelsOrTypes"] or []) for c in
              db.run_query("SHOW CONSTRAINTS YIELD labelsOrTypes RETURN labelsOrTypes")}
    flat = {l for t in labels for l in t}
    assert {"GSTIN", "Invoice"} <= flat, f"missing core constraints; have {flat}"
    assert len(names) >= 5


# ── 3. schema: indexes ─────────────────────────────────────────────────
def test_indexes_exist(live):
    idx = db.run_query("SHOW INDEXES YIELD name, type RETURN name, type")
    # More than just the two default token-lookup indexes.
    assert len(idx) > 2


# ── 4. CSV ingestion produced rows ─────────────────────────────────────
def test_ingestion_counts(live):
    s = live["stats"]
    assert s.get("gstins.csv", 0) > 0
    assert s.get("invoices.csv", 0) > 0


# ── 5. nodes created ───────────────────────────────────────────────────
def test_nodes_created(live):
    labels = {r["l"]: r["c"] for r in db.run_query(
        "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c")}
    for lbl in ("GSTIN", "Invoice", "GSTR1", "GSTR3B", "TaxPayment", "EWayBill"):
        assert labels.get(lbl, 0) > 0, f"no {lbl} nodes loaded"


# ── 6. relationships created ───────────────────────────────────────────
def test_relationships_created(live):
    rels = {r["t"]: r["c"] for r in db.run_query(
        "MATCH ()-[x]->() RETURN type(x) AS t, count(*) AS c")}
    for rt in ("ISSUED_INVOICE", "BILLED_TO", "FILED"):
        assert rels.get(rt, 0) > 0, f"no {rt} relationships loaded"


# ── 7. graph loading — property fidelity (THE drift proof) ─────────────
def test_graph_read_property_fidelity(live):
    from rings.engine import load_graph_from_neo4j
    gs = load_graph_from_neo4j()
    edges = gs["edges"]
    assert edges, "load_graph_from_neo4j returned no edges"
    # Every edge must carry a real date, amount, and gst — the V6.1 fix.
    assert all(e.get("date") is not None for e in edges), "null date (property drift!)"
    assert sum(1 for e in edges if (e.get("amount") or 0) > 0) > 0, "all amounts zero"
    assert sum(1 for e in edges if (e.get("gst_amount") or 0) > 0) > 0, "all gst zero"


# ── 8. ring detection on the live graph ────────────────────────────────
def test_ring_detection_live(live):
    from rings.engine import EngineConfig, run_pipeline
    rings = run_pipeline(EngineConfig(hop_max=6, window_days=90,
                                      persist=False, propagate=False))
    assert rings, "no rings detected on a graph with planted rings"
    r = rings[0]
    assert r.total_gst > 0, "ring total_gst is zero — drift not fixed on live path"
    assert all(0.0 <= v <= 1.0 for v in r.signals.values())
    assert 0.0 <= r.score <= 1.0


# ── 9. risk scoring on the live graph ──────────────────────────────────
def test_risk_scoring_live(live):
    from reconcile.engine import _hydrate_from_neo4j
    from rings.engine import EngineConfig, run_pipeline
    from risk.api import default_composer
    from risk.context import build_context_from_graph_source

    # Use the SAME live hydration the risk API uses (gstins + invoices + filing
    # keys + edges), plus rings detected from the live graph, then compose with
    # the shipped four-scorer composer.
    gs = _hydrate_from_neo4j()
    rings = run_pipeline(EngineConfig(hop_max=6, window_days=90,
                                      persist=False, propagate=False))
    ctx = build_context_from_graph_source(
        gs, detected_rings=[r.to_dict() for r in rings])
    ranked = default_composer().compose_all(ctx)
    assert ranked, "composer produced no rankings from live-hydrated context"
    assert all(0.0 <= r.score <= 1.0 for r in ranked)
    assert all(r.band in {"LOW", "MED", "HIGH", "CRITICAL"} for r in ranked)
    # At least some entities should carry a non-zero composed risk.
    assert any(r.score > 0 for r in ranked)


# ── 10. FastAPI endpoints against the live DB ──────────────────────────
def test_api_endpoints_live(live, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    # Persist rings first so the retrieval endpoints actually serialize a Ring
    # node — this is what caught the neo4j.time.DateTime serialization bug that
    # an empty ring list would have hidden.
    from rings.engine import EngineConfig, run_pipeline
    run_pipeline(EngineConfig(hop_max=6, window_days=90, persist=True, propagate=False))
    with TestClient(main.app) as c:
        h = c.get("/api/health")
        assert h.status_code == 200
        assert h.json().get("node_count", 0) > 0, "health reports empty graph"
        rings = c.get("/api/rings/")
        assert rings.status_code == 200, rings.text
        rj = rings.json()
        assert isinstance(rj, list) and rj, "no persisted rings returned"
        # detected_at must be a JSON string, not a raw neo4j.time.DateTime.
        assert isinstance(rj[0].get("detected_at"), (str, type(None)))
        one = c.get(f"/api/rings/{rj[0]['ring_id']}")
        assert one.status_code == 200, one.text
        assert isinstance(one.json().get("detected_at"), (str, type(None)))
        # Full live risk path: reconcile + rings + composer hydrated from Neo4j.
        summary = c.get("/api/risk/summary?limit=10")
        assert summary.status_code == 200, summary.text
        body = summary.json()
        assert "top" in body and isinstance(body["top"], list)
        for row in body["top"]:
            assert 0.0 <= row["score"] <= 1.0
            assert row["band"] in {"LOW", "MED", "HIGH", "CRITICAL"}


# ── V6.3: risk materialization + canonical Case API ────────────────────
@pytest.fixture(scope="module")
def live_materialized(live):
    """Materialize composed risk onto the loaded graph, once."""
    from risk.materialize import refresh_intelligence
    refresh_intelligence(persist=True)
    return live


def test_materialize_writes_risk_and_meta(live_materialized):
    scored = db.run_query(
        "MATCH (g:GSTIN) WHERE g.risk_score_norm IS NOT NULL RETURN count(g) AS c")[0]["c"]
    assert scored > 0, "no GSTIN carries materialized risk"
    # every scored node has all canonical risk properties
    bad = db.run_query(
        "MATCH (g:GSTIN) WHERE g.risk_score_norm IS NOT NULL AND "
        "(g.risk_score IS NULL OR g.risk_band IS NULL) RETURN count(g) AS c")[0]["c"]
    assert bad == 0, "materialized node missing risk_score/risk_band"
    meta = db.run_query("MATCH (m:RiskMeta {id:'singleton'}) RETURN count(m) AS c")[0]["c"]
    assert meta == 1, "RiskMeta stamp not written"


def test_materialization_not_stale_after_refresh(live_materialized):
    from risk.materialize import read_materialization_status
    st = read_materialization_status()
    assert st["stale"] is False
    assert st["n_scored"] > 0
    assert st["fingerprint"] == st["current_fingerprint"]


def test_staleness_detects_graph_change(live_materialized):
    from risk.materialize import read_materialization_status
    assert read_materialization_status()["stale"] is False
    # Mutating the graph fingerprint must flip stale True — stale risk can never
    # silently read as current.
    db.run_write("CREATE (:Ring {ring_id:'TEST-STALE-SENTINEL'})")
    try:
        assert read_materialization_status()["stale"] is True
    finally:
        db.run_write("MATCH (r:Ring {ring_id:'TEST-STALE-SENTINEL'}) DETACH DELETE r")
    assert read_materialization_status()["stale"] is False


def test_cases_list_live(live_materialized):
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as c:
        r = c.get("/api/cases/?limit=10")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] > 0
        assert body["materialization"]["stale"] is False
        row = body["cases"][0]
        for key in ("case_id", "gstin_id", "risk_score", "band", "exposure_inr",
                    "ring_ids", "top_reasons"):
            assert key in row
        assert 0.0 <= row["risk_score"] <= 1.0
        assert row["band"] in {"LOW", "MED", "HIGH", "CRITICAL"}


def test_case_detail_is_coherent(live_materialized):
    from fastapi.testclient import TestClient
    import main
    gid = db.run_query(
        "MATCH (g:GSTIN) WHERE g.risk_score_norm IS NOT NULL "
        "RETURN g.gstin_id AS id ORDER BY g.risk_score_norm DESC LIMIT 1")[0]["id"]
    with TestClient(main.app) as c:
        r = c.get(f"/api/cases/{gid}")
        assert r.status_code == 200, r.text
        case = r.json()
        # ONE response carries the whole investigation object.
        assert case["case_id"] == gid
        assert case["entity"]["gstin_id"] == gid
        assert case["risk"]["materialized"] is True
        assert case["risk"]["band"] in {"LOW", "MED", "HIGH", "CRITICAL"}
        assert 0.0 <= case["risk"]["score"] <= 1.0
        for key in ("exposure", "rings", "reconciliation", "related_vendors",
                    "timeline", "subgraph", "materialization"):
            assert key in case
        assert case["subgraph"] is not None
        # a 404 for an unknown entity
        assert c.get("/api/cases/NOSUCHGSTIN").status_code == 404


def test_vendors_risk_now_reads_materialized(live_materialized):
    """The retired /api/vendors/risk must serve the materialized composer risk
    (fast, band vocabulary), not recompute the legacy IsolationForest."""
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as c:
        r = c.get("/api/vendors/risk")
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["model_used"].startswith("composer")
        assert body["vendors"], "no vendors returned"
        assert all("risk_band" in v for v in body["vendors"][:5])


def test_exposure_no_double_count(live_materialized):
    """ITC exposure must count each invoice's GST once, even when the invoice
    carries multiple blocking outcomes (regression for the double-count bug)."""
    from investigation.service import BLOCKING_OUTCOMES, _exposure_for
    multi = db.run_query(
        "MATCH (g:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)<-[:ABOUT]-(m:MatchEvent) "
        "WHERE m.outcome IN $b WITH g, i, count(DISTINCT m.outcome) AS k WHERE k>=2 "
        "RETURN g.gstin_id AS id LIMIT 1", {"b": BLOCKING_OUTCOMES})
    if not multi:
        pytest.skip("no invoice with >=2 blocking outcomes in this dataset")
    gid = multi[0]["id"]
    truth = db.run_query(
        "MATCH (g:GSTIN {gstin_id:$id})-[:ISSUED_INVOICE]->(i:Invoice) "
        "WHERE EXISTS { (i)<-[:ABOUT]-(m:MatchEvent) WHERE m.outcome IN $b } "
        "RETURN sum(coalesce(i.total_gst,0)) AS total, count(i) AS n",
        {"id": gid, "b": BLOCKING_OUTCOMES})[0]
    exp = _exposure_for(gid)
    assert abs(exp.total_inr - round(float(truth["total"] or 0), 2)) < 0.01
    assert exp.invoice_count == int(truth["n"])


def test_recurrence_survives_refresh(live_materialized):
    """Re-materializing the same graph must INCREMENT ring sighting_count (the
    H/R recurrence signals read prior history), not reset it — regression for the
    wipe-before-detect bug."""
    from risk.materialize import refresh_intelligence
    before = db.run_query("MATCH (r:Ring) RETURN max(r.sighting_count) AS m, count(r) AS c")[0]
    refresh_intelligence(persist=True)
    after = db.run_query("MATCH (r:Ring) RETURN max(r.sighting_count) AS m, count(r) AS c")[0]
    assert after["m"] > before["m"], "sighting_count did not increment across refreshes"
    assert after["c"] == before["c"], "ring count drifted across identical refreshes"


# ── 11. idempotent reload ──────────────────────────────────────────────
def test_idempotent_reload(live):
    from datagen.loader import load_directory
    before_n = db.run_query("MATCH (n) RETURN count(n) AS c")[0]["c"]
    before_r = db.run_query("MATCH ()-[x]->() RETURN count(x) AS c")[0]["c"]
    load_directory(live["dir"])                          # same data again
    after_n = db.run_query("MATCH (n) RETURN count(n) AS c")[0]["c"]
    after_r = db.run_query("MATCH ()-[x]->() RETURN count(x) AS c")[0]["c"]
    assert (before_n, before_r) == (after_n, after_r), \
        f"reload not idempotent: nodes {before_n}->{after_n}, rels {before_r}->{after_r}"


# ── 12. reset / cleanup ────────────────────────────────────────────────
def test_reset_wipes_graph(live):
    db.run_write("MATCH (n) DETACH DELETE n")
    assert db.run_query("MATCH (n) RETURN count(n) AS c")[0]["c"] == 0
