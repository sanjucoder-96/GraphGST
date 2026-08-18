# Graph GST — Knowledge Graph Intelligence for Indian GST Reconciliation

Graph GST is a graph-native platform for reconciling GST filings, quantifying ITC risk, and discovering circular-trading rings across the Indian GST supply chain.

Unlike table-based reconciliation, it models GSTIN, Invoice, GSTR-1/2B/3B, TaxPayment, e-Way Bill, and IRN as connected nodes in Neo4j. Reconciliation, cycle detection, and risk scoring all run as native graph queries, and every alert is explainable by pointing at the exact hops in the graph that produced it.

**Status:** V6 in active development. See `IMPLEMENTATION_LOG.md` for the running change log and `ARCHITECTURE.md` for the design.

---

## Quick start — one command

```bash
docker compose up --build
```

Then:
- Web UI:    <http://localhost:3000>
- API docs:  <http://localhost:8000/docs>
- Neo4j:     <http://localhost:7474>  (`neo4j` / `graphgst-dev-password`)

The compose file starts three services: `neo4j` (with APOC + GDS plugins), `backend` (FastAPI), and `web` (nginx serving the static shell).

## Quick start — without Docker

Requires Python 3.11+ and a running Neo4j 5.x with APOC and Graph Data Science plugins.

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                 # fill in NEO4J_URI, USERNAME, PASSWORD, ADMIN_TOKEN
uvicorn main:app --reload --port 8000
```

Serve the static shell:

```bash
python -m http.server 3000           # from the graphgst/ directory
```

## Seed the demo scenarios

Ten well-known fraud/compliance scenarios (SC1–SC9 from V5 plus a validity case) can be planted with:

```bash
curl -X POST http://localhost:8000/api/seed
```

This is idempotent (uses `MERGE`); re-seeding never duplicates nodes.

## Generate synthetic data with ground truth

For anything beyond a canned demo, use the synthetic generator (Phase 1). See `datagen/README.md`.

```bash
python -m datagen.cli \
  --n-gstins 5000 --months 6 \
  --normal-share 0.90 --recon-issue-share 0.05 --circular-share 0.03 \
  --n-rings 15 --ring-size-min 3 --ring-size-max 8 \
  --seed 42 --out ./datagen_output
```

Emits `gstr1.csv`, `gstr2b.csv`, `gstr3b.csv`, `pr.csv`, `ewb.csv`, `irn.csv`, and `truth.json` — the labeled anomalies used by every benchmark.

## Load a generated dataset into Neo4j

```bash
curl -X POST -H "X-Admin-Token: <your-token>" \
     "http://localhost:8000/api/datagen/load?dir=./datagen_output"
```

---

## Where things live

| Path | Purpose |
|---|---|
| `main.py` | FastAPI app, all HTTP routes |
| `db.py` | Neo4j driver singleton, `run_query`, `run_write` |
| `seeder.py` | Nine hand-crafted scenarios + graph constraints and indexes |
| `risk_engine.py` | Rule scoring, cycle detection, audit narrative, IsolationForest |
| `datagen/` | Synthetic GST generator with ground truth (Phase 1) |
| `pages/`, `assets/`, `index.html` | Vanilla-JS investigator shell |
| `tests/` | Pytest test suite |
| `ARCHITECTURE.md` | Design of V6 |
| `IMPLEMENTATION_LOG.md` | Running change log |
| `DEV_GUIDE.md` | Beginner-friendly walkthrough |

## Historical notes

- The older `D:\GraphGST\Hack_Me\` snapshot was a broken subset of V5 (missing `db.py`, missing `pages/dashboard.js` / `add.js` / `agent.js`, folders flattened). It is now obsolete; work happens here in `graphgst/`.
- V5's checked-in `isolation_forest_model.pkl` has been removed. The model is now retrained on demand from the current graph — see Phase 4.

## License

MIT. See `LICENSE`.
