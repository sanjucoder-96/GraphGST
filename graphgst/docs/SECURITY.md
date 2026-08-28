# Graph GST — Security Model

Scope: this is a **demo / research backend**, not a production multi-tenant
IAM system. The goal is sensible, correct controls on the operations that
mutate state or read the filesystem — not enterprise identity. Known
limitations are listed explicitly.

## Threat model

| Asset | Threat | Control | Status |
|---|---|---|---|
| Graph (Neo4j) | Unauthorized wipe / mutation | `require_admin` on `POST /api/seed` (unconditional; `force=true` calls `clear_graph()` to wipe first), `DELETE /api/seed`, `POST /api/invoices`, `PATCH /api/cases/{id}`, `/api/datagen/generate`, `/api/datagen/load`, `/api/demo/reset`, `/api/embed/train`, `/api/benchmarks/run`, `/api/reconcile2/run?persist=true`, `/api/rings/detect` when `persist`/`propagate=true` | ✅ |
| Admin token | Timing attack | `hmac.compare_digest` (constant-time), shared `security.require_admin` used by every router | ✅ |
| Filesystem | Path traversal / arbitrary file read via `dir=` params (`/api/datagen/load`, `/api/datagen/truth`) | `security.resolve_within` — resolves symlinks + `..`, requires containment in an allowed root | ✅ |
| Neo4j | Cypher injection via user input | All user values are bound as `$params`; no string-interpolated user data in Cypher. The one f-string (`multi_hop` var-length `*1..N`) uses an int clamped to `1..5`. | ✅ |
| Browser | Cross-origin abuse | CORS restricted to `CORS_ORIGINS` (env), never `*` in the shipped default; `allow_methods` = `GET,POST,PATCH,DELETE` (PATCH added for `/api/cases/{id}`) | ✅ |
| Secrets | Leakage | `.env` git-ignored; `.env.example` has placeholders; `ADMIN_TOKEN` fails **closed** (503) when unset — endpoints are disabled, never open | ✅ |
| Feedback log | Unbounded disk write (DoS) via anonymous `POST /api/agent/feedback` | Pydantic `Field(max_length=…)` caps every field — label 64, query 2000, intent 64, `subgraph_node_ids` 200 items, comment 4000 — returning **422** on overflow before the record reaches `feedback.jsonl` | ✅ |
| Errors | Info disclosure | `GET /api/health` (unauthenticated) no longer returns the DB URI or raw exception text — it maps the failure to `"error"`; `read_truth` verbose path echo removed. **Residual:** several other endpoints still echo exception text in the HTTP `detail` — see Known limitations. | ⚠️ |

## Controls in detail

### Authentication / authorization
There is one privilege level: **admin**, proven by the `X-Admin-Token`
header matching the server's `ADMIN_TOKEN`. Every destructive or mutating
endpoint depends on `security.require_admin` (constant-time compare, 401 on
mismatch, **503 when `ADMIN_TOKEN` is unset** so a misconfigured server is
disabled rather than open). Read-only analytics endpoints are unauthenticated
by design (demo).

**V6.4 hardening pass.** The audit closed three unguarded write paths and one
DoS vector:

- `POST /api/invoices` (creates GSTIN/Invoice/GSTR/TaxPayment/EWB nodes) now
  depends on `require_admin`.
- `PATCH /api/cases/{gstin_id}` (persists investigation workflow status onto
  the graph — it conceals/surfaces cases in the queue) now depends on
  `require_admin`.
- `POST /api/seed` requires admin **unconditionally** (seeding mutates the
  graph regardless of `force`); `force=true` now calls `seeder.clear_graph()`
  to actually wipe the graph *before* re-seeding, so a seeder model cannot be
  silently overlaid on a loader-populated graph.
- `POST /api/agent/feedback` fields are length-capped (see the Feedback-log row
  above) so an anonymous caller cannot append arbitrarily large records.
- `GET /api/health` was tightened to stop disclosing the DB URI / backend
  exception text on an unauthenticated surface.
- `CORSMiddleware.allow_methods` now includes `PATCH` (required by the Case
  status update).

### Path safety
`security.resolve_within(candidate)` resolves the user path (following
symlinks and `..`) and returns it only if it lives under an allowed root:
`datagen_output/`, `demo/artifacts/`, `benchmarks/`, and the system temp dir,
overridable with `GRAPHGST_DATA_ROOTS`. `/api/datagen/load` and
`/api/datagen/truth` both go through it, closing the previous
arbitrary-file-read on `read_truth`.

### Cypher injection
User-controlled values reach Neo4j only as bound parameters (`$sg`, `$id`,
`$g`, …). Cypher string concatenation (`'GSTR1-'+$sg+'-USER'`) happens
**server-side on the already-bound value** and cannot inject structure. The
only interpolated Cypher fragment is the variable-length bound in
`multi_hop`, which is an integer clamped to `1..5`.

### Input validation
Request bodies are Pydantic models with typed fields. Query ints are clamped
where they feed Cypher. Label columns from the synthetic generator are
stripped before scoring (evaluation integrity, not security, but same
defence-in-depth reflex — see `benchmarks/evalsafe.py`).

## Known limitations (explicit)

- **No user identity / RBAC.** One shared admin token. Fine for a demo;
  a real deployment needs per-user auth + audit logging.
- **No rate limiting.** A determined caller can hammer read endpoints.
- **`/api/embed/train` and `/api/benchmarks/run` are CPU-heavy** and admin
  gated, but there is no job queue — a synchronous call blocks a worker.
- **CORS credentials** are allowed for the configured origins; tighten if the
  frontend is ever served cross-site with cookies.
- **Neo4j credentials** live in the process environment; use a secrets
  manager in production.

### Audit-flagged, out of scope this pass (V6.4)

The V6.4 pass fixed the write-side and DoS findings above. The following gaps
were flagged by the same audit but **deliberately left for a later pass** — they
are recorded here so they are tracked, not forgotten. They are consistent with
the demo/research posture and none of them is a newly introduced regression.

- **The read surface is unauthenticated.** `GET /api/cases` and
  `GET /api/cases/{id}`, `GET /api/vendors` and `GET /api/vendors/risk`, the
  fraud endpoints (`/api/fraud/circular`, `/api/fraud/circular-gst`,
  `/api/fraud/phantom-ewb`, `/api/fraud/cancelled-gstin`), `GET /api/graph/full`,
  and the agent's **draft-SCN** path (`POST /api/agent/query`, which composes a
  show-cause-notice draft from graph evidence) all serve without a token. A real
  deployment must gate these behind per-user auth.
- **No rate limiting on compute-heavy routes.** Even the admin-gated
  `/api/embed/train`, `/api/benchmarks/run`, and the reconcile/rings recompute
  paths run synchronously with no throttle or job queue — a caller with the
  token (or an unauthenticated caller on the heavy *read* graph queries) can pin
  a worker.
- **Several endpoints still return raw exception text in the HTTP `detail`.**
  `POST /api/seed` (`HTTPException(500, str(e))`) and every handler in
  `investigation/api.py` (`f"case list unavailable: {e}"`,
  `f"case unavailable: {e}"`, `f"status update failed: {e}"`) echo the
  underlying exception to the client. `/api/health` was the only leak closed
  this pass.
- **`/docs` and `/openapi.json` are public.** FastAPI's interactive docs and the
  full OpenAPI schema are served with no `docs_url`/`openapi_url` gating, so the
  entire route map (including admin endpoints) is enumerable.
- **`joblib.load` of the IsolationForest `.pkl` is a pickle load.**
  `risk_engine.py` does `joblib.load(_MODEL_PATH)` where `_MODEL_PATH` is a
  fixed path next to the source (`isolation_forest_model.pkl`). The path is
  trusted and not user-controlled, so this is not currently exploitable, but
  `joblib.load` deserializes pickle and would execute arbitrary code if that
  file were ever attacker-writable.
- **`db.py` defaults `NEO4J_PASSWORD` to a weak literal.** When the env var is
  unset, `get_driver()` falls back to `os.getenv("NEO4J_PASSWORD", "password")`.
  Convenient for local Docker, but a deployment that forgets to set the variable
  connects (or attempts to) with a guessable credential rather than failing.

These are acceptable for the current phase (demo + research) and documented so
they are not mistaken for oversights.
