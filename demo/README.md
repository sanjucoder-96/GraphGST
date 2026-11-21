# demo — the reproducible investigation story (Phase 8)

A 3-5 minute demo of Graph GST V6 driven by ONE controlled hero ring
with fully known ground truth. Every number the presenter says on
stage is either produced by the real system or lives in a fixture
labelled DEMO in the frontend.

## One-command lifecycle

```bash
# 1. Reset the demo state — regenerates the fixed dataset (byte-deterministic)
#    and, if Neo4j is reachable, wipes and reloads it from the fresh CSVs.
python -m demo.reset

# 2. Verify — hits the reconcile / rings / embed engines in-memory and
#    asserts every number in the story. Non-zero exit code if any drifted.
python -m demo.verify

# 3. Boot the app (any of these works)
docker compose up --build          # full stack on :3000, :5173, :8000, :7474
uvicorn main:app --port 8000       # backend only
npm --prefix web run dev           # frontend only, mocks fall through if backend down
```

## The hero ring

`RING-42-00000` — 4 Maharashtra beverage-trade GSTINs. All four
invoices are pairwise-clean (reconciliation reports ZERO events on
them) but they form a closed cycle with:

- **Shared vehicle** `TN84WC2559` on every e-Way Bill
- **Shared director** `DIR-500000-Meera-Kumar` across two members
- **+15 % value inflation per hop** — invoice values escalate
- **3-day temporal window** — all four invoices booked in 72 hours
- **HSN 2202** (aerated beverages) throughout
- **Closure date** 2024-06-19

Detected metrics (verified deterministically):

- Ring score **0.593** (threshold 0.45)
- Signals: **C 1.00 · V 0.84 · T 0.97 · R 0.00 · N 0.75 · H 0.00**
- Total GST at risk: **₹2,19,229**
- Break-edge recommendation: `INV-202406-RING-000-02`

## The 8-step story

Total: ~5:00. Every step has `expected` assertions the verifier checks
before the presenter goes on stage.

| # | Duration | Title | Route | Backing endpoint |
|---:|---:|---|---|---|
| 1 | 0:30 | Setup — one-command reset | — | `demo.reset.reset()` |
| 2 | 0:30 | Ingest & reconcile — what the tables show | `/` | `GET /api/reconcile2/summary` |
| 3 | 0:30 | What reconciliation misses — hero invoices are clean | `/` | `GET /api/reconcile2/summary` |
| 4 | 1:00 | The graph engine catches the ring | `/ring/R-68383043e2e47603` | `GET /api/rings/…` |
| 5 | 0:45 | Temporal replay — watch the ring form over 3 days | same | `edges[].date` on ring |
| 6 | 0:45 | Break-edge counterfactual | same | `break_edge`, `per_edge` |
| 7 | 0:45 | Related vendors — embedding finds ring co-members | — | `GET /api/embed/lookalike/…` |
| 8 | 0:45 | Model Card — every claim, with the number | `/model-card` | `GET /api/benchmarks/model-card` |

Full narrator text and per-step expected assertions live in `story.py`.

## HTTP surface

- `GET /api/demo/status` — has the demo state been initialized?
- `GET /api/demo/hero` — full HERO_RING dict
- `GET /api/demo/story` — full narrator script + expected values
- `GET /api/demo/verify` — live verify + facts (200 always; check
  `exit_code` in the body)
- `POST /api/demo/reset?load_neo4j=true` — admin-only

## The reproducibility contract

- **Seed 42** everywhere (datagen, rings, embed, ML scorers).
- **PYTHONHASHSEED=0** auto-set by `demo.reset` and `benchmarks.run_all`
  via `os.execvpe` — protects against Python's per-process hash salt
  cascading into set-iteration order and NetworkX SCC output.
- **Baseline JSON** at `benchmarks/baseline.json` — the numbers the
  Model Card page displays and the CI job gates on.
- **Story verifier** at `demo/verify.py` — a second, story-shaped
  gate that runs BEFORE the presenter is on stage. Hard-fails if any
  narrator number drifts from what the live engines produce.

If the demo fails the verifier, do NOT go on stage. Fix or roll back
first. That is the point of the whole harness.

## Failure modes and their fixes

| symptom | likely cause | fix |
|---|---|---|
| `demo.reset` reports `neo4j_loaded: false` | Neo4j not running / wrong creds | Start `docker compose up neo4j` or fix `NEO4J_*` env |
| Verifier says hero ring `detected: False` | Datagen changed and hero id shifted | Re-run `python -m demo.probe_hero` and update `scenario.py` |
| Verifier says embed hits < 2 | Embed training params changed | Update `expected.embed_lookalike_min_hero_in_top10` or restore params |
| Model Card shows FAIL | Bench headline regressed | Fix the regression, or knowingly `run_all --write-baseline` and log in `IMPLEMENTATION_LOG.md` |
