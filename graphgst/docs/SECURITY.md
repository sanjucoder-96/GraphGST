# Graph GST — Security Model

Scope: this is a **demo / research backend**, not a production multi-tenant
IAM system. The goal is sensible, correct controls on the operations that
mutate state or read the filesystem — not enterprise identity. Known
limitations are listed explicitly.

## Threat model

| Asset | Threat | Control | Status |
|---|---|---|---|
| Graph (Neo4j) | Unauthorized wipe / mutation | `require_admin` on `DELETE /api/seed`, `POST /api/seed?force`, `/api/datagen/generate`, `/api/datagen/load`, `/api/demo/reset`, `/api/embed/train`, `/api/benchmarks/run`, `/api/reconcile2/run?persist=true`, `/api/rings/detect` when `persist`/`propagate=true` | ✅ |
| Admin token | Timing attack | `hmac.compare_digest` (constant-time), shared `security.require_admin` used by every router | ✅ |
| Filesystem | Path traversal / arbitrary file read via `dir=` params (`/api/datagen/load`, `/api/datagen/truth`) | `security.resolve_within` — resolves symlinks + `..`, requires containment in an allowed root | ✅ |
| Neo4j | Cypher injection via user input | All user values are bound as `$params`; no string-interpolated user data in Cypher. The one f-string (`multi_hop` var-length `*1..N`) uses an int clamped to `1..5`. | ✅ |
| Browser | Cross-origin abuse | CORS restricted to `CORS_ORIGINS` (env); never `*` in the shipped default | ✅ |
| Secrets | Leakage | `.env` git-ignored; `.env.example` has placeholders; `ADMIN_TOKEN` fails **closed** (503) when unset — endpoints are disabled, never open | ✅ |
| Errors | Info disclosure | Endpoints return terse messages; internal exceptions are logged, not returned verbatim; the removed `read_truth` verbose path echo is gone | ✅ |

## Controls in detail

### Authentication / authorization
There is one privilege level: **admin**, proven by the `X-Admin-Token`
header matching the server's `ADMIN_TOKEN`. Every destructive or mutating
endpoint depends on `security.require_admin` (constant-time compare, 401 on
mismatch, **503 when `ADMIN_TOKEN` is unset** so a misconfigured server is
disabled rather than open). Read-only analytics endpoints are unauthenticated
by design (demo).

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

These are acceptable for the current phase (demo + research) and documented so
they are not mistaken for oversights.
