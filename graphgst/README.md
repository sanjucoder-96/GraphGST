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
- Investigator Console (React):  <http://localhost:5173>
- Legacy vanilla-JS shell:       <http://localhost:3000>
- API docs:                       <http://localhost:8000/docs>
- Neo4j Browser:                  <http://localhost:7474>  (`neo4j` / `graphgst-dev-password`)

The compose file starts four services: `neo4j` (with APOC + GDS plugins), `backend` (FastAPI on :8000), `web` (React SPA on :5173) and `web-legacy` (vanilla-JS shell on :3000 for regression comparison).

## Scripted 3-5 minute demo

Graph GST ships with a fully reproducible investigation story built around one controlled hero ring with known ground truth. See [`demo/README.md`](demo/README.md).

```bash
# 1. Reset — regenerates the fixed dataset (byte-deterministic, seed 42)
python -m demo.reset

# 2. Verify — asserts every narrator number against real engine output
python -m demo.verify

# 3. Present — /model-card shows the numbers gating each claim, /ring/…
#    walks the case queue → investigation → timeline → break-simulator flow
```

Verification runs in-memory (no Neo4j needed) and exits non-zero if any story number drifts.

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

| Path | Purpose | Phase |
|---|---|---|
| `main.py` | FastAPI app, mounts every module router | 0 |
| `db.py` | Neo4j driver singleton (`run_query`, `run_write`) | 0 |
| `seeder.py` | Hand-crafted scenarios + graph constraints + indexes | 0 |
| `datagen/` | Synthetic GST generator with `truth.json` | 1 |
| `reconcile/` | MatchEvent nodes + fuzzy matchers | 2 |
| `rings/` | SCC → bounded Johnson → six-signal ring engine + counterfactual | 3 |
| `risk/` | Composable scorers + `Reason[]` attribution + composed score | 4 |
| `embed/` | Random walks + PMI-SVD embeddings + cosine lookalike | 5 |
| `web/` | React 18 + TS Investigator Console (Vite) | 6 |
| `benchmarks/` | Unified runner + baseline + comparator + Model Card | 7 |
| `demo/` | Reproducible 3-5 minute scripted story | 8 |
| `tests/` | Pytest test suite (160+ tests) | — |
| `pages/`, `assets/`, `index.html` | Vanilla-JS legacy shell (kept for regression) | 0 |
| `.github/workflows/ci.yml` | pytest + benchmarks + web build on push | — |
| `ARCHITECTURE.md` | V6 target design | — |
| `IMPLEMENTATION_LOG.md` | Running change log | — |
| `DEV_GUIDE.md` | Beginner-friendly walkthrough | — |

## What Graph GST claims and what number backs it

These are the **V6.1-corrected, honest** headline metrics — measured on the
*hardened* benchmark (dropped ring tells, broken near-rings, legit-cycle
negatives). The V6.1 audit replaced three earlier numbers that were circular or
tautological; see [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) for the full
old→new correction and why.

| Claim | Number | Where measured |
|---|---:|---|
| Ring detection — Average Precision (threshold-free, hard data) | **0.971** | `benchmarks/bench_ring_recall.py` |
| Reconciliation micro-F1 | **0.961** | `benchmarks/bench_reconcile_prf.py` |
| Composed risk ROC-AUC (ring-**independent** label) | **0.887** | `benchmarks/bench_risk_discrimination.py` |
| Lookalike structural Hit@10 (non-adjacent same-ring member) | **0.667** | `benchmarks/bench_embed_lookalike.py` |

> Corrected in V6.1 (do not reinstate the old numbers): ring **recall 1.000** was
> *recoverability* (Johnson finds every cycle), not detection; risk **AUC 0.937**
> used a *circular* ring-membership label; embedding **Hit@10 1.000** was
> *tautological* (ring members are 1-hop neighbours).

Nine metrics are baseline-gated. `python -m benchmarks.run_all` exits 1 if any
regresses by more than 0.02. The Model Card page renders them live in the
Investigator Console.

## Historical notes

- The older `D:\GraphGST\Hack_Me\` snapshot was a broken subset of V5 (missing `db.py`, missing `pages/dashboard.js` / `add.js` / `agent.js`, folders flattened). It is now obsolete; work happens here in `graphgst/`.
- V5's checked-in `isolation_forest_model.pkl` has been removed. The model is now retrained on demand from the current graph — see Phase 4.

## License

MIT. See `LICENSE`.
