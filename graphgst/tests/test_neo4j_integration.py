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
