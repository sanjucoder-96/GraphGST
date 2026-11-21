// Typed fetch wrappers with mock fallback.
//
// Every call:
//   1. AbortSignal-limited to TIMEOUT_MS.
//   2. On network error / non-2xx: resolves from src/lib/mocks.ts and marks
//      the app as DEMO for the next 30s.
//   3. Never throws — the UI never needs a try/catch for backend flakiness.

import type {
  AgentResponse,
  DashboardSummary,
  LookalikeResp,
  ModelCard,
  Ring
} from '../types/domain';
import type { CaseList, InvestigationCase, InvestigationStatus } from '../types/case';
import {
  MOCK_DASHBOARD,
  lookMockFor,
  MOCK_MODEL_CARD,
  MOCK_RINGS
} from './mocks';

// API base is configurable via VITE_API_BASE so the backend can run on any
// host/port (e.g. when :8000 is taken). Defaults to :8000 for the standard
// local/docker setup. Set VITE_API_BASE in web/.env.local to override.
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ||
  'http://localhost:8000';
// DEMO MODE: an admin token shipped to the browser so the demo can persist
// investigation-status changes (PATCH /api/cases/{id}) live. In a real
// DEPLOYMENT this is left unset — status mutation then requires a separately
// authenticated operator flow, never a bundled token. See docs/SECURITY.md.
const ADMIN_TOKEN = (import.meta.env.VITE_ADMIN_TOKEN as string | undefined) || '';
export function adminEnabled(): boolean { return ADMIN_TOKEN.length > 0; }
// Client-side abort budget. A DOWN backend rejects almost instantly
// (connection refused), so this only bounds slow-but-alive responses. The
// compute-heavy endpoints (vendor risk = IsolationForest + graph features,
// ring detection) legitimately take several seconds against a REMOTE Aura
// instance; a 2.5s cap made the UI spuriously fall back to mock data even
// though the live backend was answering. 8s keeps genuine outages fast to
// detect while letting real remote queries complete.
const TIMEOUT_MS = 8000;
const DEMO_WINDOW_MS = 30_000;

let lastFallbackAtMs = 0;
let lastRoundtripMs = 0;
let lastNeo4jOk: boolean | null = null;

export function environmentIsDemoNow(): boolean {
  return Date.now() - lastFallbackAtMs < DEMO_WINDOW_MS;
}
export function latencyMs(): number { return lastRoundtripMs; }
export function neo4jSeen(): boolean | null { return lastNeo4jOk; }

export interface ApiResult<T> {
  data: T;
  fromMock: boolean;
  latency_ms: number;
  status: number | 'timeout' | 'network';
}

async function safeGet<T>(path: string, fallback: T): Promise<ApiResult<T>> {
  const started = performance.now();
  const ctrl = new AbortController();
  try {
    const t = setTimeout(() => ctrl.abort('timeout'), TIMEOUT_MS);
    const res = await fetch(API_BASE + path, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error(`http_${res.status}`);
    const body = (await res.json()) as T;
    lastRoundtripMs = Math.round(performance.now() - started);
    return { data: body, fromMock: false, latency_ms: lastRoundtripMs, status: res.status };
  } catch (err) {
    // Distinguish OUR timeout from an EXTERNAL abort (page navigation, HMR,
    // StrictMode remount). Only a real timeout / network error should poison
    // the cache with demo fixtures; an external cancel is re-thrown so React
    // Query discards it and refetches — otherwise a rapid reload can leave a
    // live page showing the empty fallback for the whole staleTime window.
    const aborted = err instanceof DOMException && err.name === 'AbortError';
    if (aborted && ctrl.signal.reason !== 'timeout') throw err;
    lastRoundtripMs = Math.round(performance.now() - started);
    lastFallbackAtMs = Date.now();
    const status: number | 'timeout' | 'network' = aborted ? 'timeout' : 'network';
    return { data: fallback, fromMock: true, latency_ms: lastRoundtripMs, status };
  }
}

async function safePost<T>(path: string, payload: unknown, fallback: T): Promise<ApiResult<T>> {
  const started = performance.now();
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort('timeout'), TIMEOUT_MS);
    const res = await fetch(API_BASE + path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
      signal: ctrl.signal
    });
    clearTimeout(t);
    if (!res.ok) throw new Error(`http_${res.status}`);
    const body = (await res.json()) as T;
    lastRoundtripMs = Math.round(performance.now() - started);
    return { data: body, fromMock: false, latency_ms: lastRoundtripMs, status: res.status };
  } catch (err) {
    lastRoundtripMs = Math.round(performance.now() - started);
    lastFallbackAtMs = Date.now();
    const status: number | 'timeout' | 'network' =
      err instanceof DOMException && err.name === 'AbortError' ? 'timeout' : 'network';
    return { data: fallback, fromMock: true, latency_ms: lastRoundtripMs, status };
  }
}

// ---- Concrete endpoints -------------------------------------------------

export function getRings(): Promise<ApiResult<Ring[]>> {
  return safeGet<Ring[]>('/api/rings/', MOCK_RINGS);
}
export function getRing(ringId: string): Promise<ApiResult<Ring>> {
  const local = MOCK_RINGS.find(r => r.ring_id === ringId) ?? MOCK_RINGS[0];
  return safeGet<Ring>(`/api/rings/${ringId}`, local);
}
// (V6.3) getVendorRisk / normalizeLiveVendors removed — the deprecated
// /api/vendors/risk is no longer consumed by the frontend.
// (V7) getCases()/normalizeComposerRows removed — the Case Queue migrated to the
// canonical getCaseList() (GET /api/cases), which carries real exposure, ring
// count, status and primary_signal per row. The legacy composer summary
// (GET /api/risk/summary) is no longer called by the frontend; it remains on the
// backend for tests/tools. The Investigation page uses getCase() (Case API).

// ── Canonical Case API (V6.3) ───────────────────────────────────────────
// The final Investigator UI should consume these two functions: getCaseList()
// for the queue and getCase(gstin) for the whole investigation object. Both
// return the backend's canonical, strongly-typed shapes (see types/case.ts).
const _EMPTY_MATERIALIZATION = {
  stale: true, fingerprint: {}, current_fingerprint: {}, n_scored: 0,
};

export function getCaseList(
  params: { band?: string; min_score?: number; limit?: number; q?: string } = {},
): Promise<ApiResult<CaseList>> {
  const qs = new URLSearchParams();
  if (params.band) qs.set('band', params.band);
  if (params.min_score != null) qs.set('min_score', String(params.min_score));
  qs.set('limit', String(params.limit ?? 100));
  if (params.q) qs.set('q', params.q);
  const fallback: CaseList = {
    count: 0, band_counts: {}, materialization: _EMPTY_MATERIALIZATION, cases: [],
  };
  return safeGet<CaseList>(`/api/cases/?${qs.toString()}`, fallback);
}

export interface StatusPatchResult {
  ok: boolean;
  status?: InvestigationStatus;
  code: number | 'network' | 'disabled';
}
/** Persist an investigation status via PATCH /api/cases/{id} (admin-gated).
 *  Returns ok:false with a code the caller can surface — never throws. */
export async function patchCaseStatus(
  gstin: string, status: InvestigationStatus,
): Promise<StatusPatchResult> {
  if (!ADMIN_TOKEN) return { ok: false, code: 'disabled' };
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort('timeout'), TIMEOUT_MS);
    const res = await fetch(`${API_BASE}/api/cases/${encodeURIComponent(gstin)}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json', 'X-Admin-Token': ADMIN_TOKEN },
      body: JSON.stringify({ status }),
      signal: ctrl.signal,
    });
    clearTimeout(t);
    if (!res.ok) return { ok: false, code: res.status };
    const body = await res.json() as { investigation_status?: InvestigationStatus };
    return { ok: true, status: body.investigation_status, code: res.status };
  } catch {
    return { ok: false, code: 'network' };
  }
}

export function getCase(gstin: string): Promise<ApiResult<InvestigationCase>> {
  const fallback: InvestigationCase = {
    case_id: gstin,
    entity: { gstin_id: gstin },
    risk: {
      score: 0, score_100: 0, band: 'LOW', contributions: {}, reasons: [],
      scorers_fired: [], scorers_run: [], materialized: false,
    },
    exposure: { total_inr: 0, by_outcome: {}, invoice_count: 0 },
    rings: [], reconciliation: [], related_vendors: [], timeline: [],
    subgraph: null, investigation_status: 'open',
    materialization: _EMPTY_MATERIALIZATION,
  };
  return safeGet<InvestigationCase>(`/api/cases/${encodeURIComponent(gstin)}`, fallback);
}
// (V6.3) getGraphFull / getAuditTrail removed — the Investigation page no longer
// assembles a case from the full graph + per-invoice audit trails; getCase()
// returns the ring-scoped subgraph and reconciliation events in one response.
export async function getDashboardSummary(): Promise<ApiResult<DashboardSummary>> {
  const res = await safeGet<DashboardSummary>('/api/dashboard/summary', MOCK_DASHBOARD);
  lastNeo4jOk = res.fromMock ? false : Boolean(res.data.neo4j);
  return res;
}
export function postDetect(): Promise<ApiResult<Ring[]>> {
  return safePost<Ring[]>('/api/rings/detect', { hop_max: 8, window_days: 30 }, MOCK_RINGS);
}
export function postAgentQuery(payload: { intent: string; payload: unknown }): Promise<ApiResult<AgentResponse>> {
  const fallback: AgentResponse = {
    intent: payload.intent,
    text: null,
    error: 'agent_unavailable'
  };
  return safePost<AgentResponse>('/api/agent/query', payload, fallback);
}

export function getModelCard(): Promise<ApiResult<ModelCard>> {
  return safeGet<ModelCard>('/api/benchmarks/model-card', MOCK_MODEL_CARD);
}

export interface DatasetInfo {
  kind: 'SYNTHETIC_DEMO' | 'PUBLIC_DATASET';
  name: string;
  dataset_id: string;
  source: string;
  license: string;
  is_real_taxpayer_data: boolean;
  anonymized: boolean;
  entities: number | null;
  transactions: number | null;
  date_min: string | null;
  date_max: string | null;
  warnings: string[];
  notes: string;
  ingested_at: string | null;
}
/** Provenance of the graph currently loaded — drives the console's
 *  SYNTHETIC DEMO vs PUBLIC DATASET banner. Never conflates the two. */
export function getDatasetCurrent(): Promise<ApiResult<DatasetInfo>> {
  const fallback: DatasetInfo = {
    kind: 'SYNTHETIC_DEMO', name: 'synthetic demo', dataset_id: 'synthetic_v7',
    source: 'datagen (seed 42)', license: 'internal / research',
    is_real_taxpayer_data: false, anonymized: false,
    entities: null, transactions: null, date_min: null, date_max: null, warnings: [],
    notes: 'Deterministic synthetic dataset (seed 42) — NOT real taxpayer data.',
    ingested_at: null,
  };
  return safeGet<DatasetInfo>('/api/dataset/current', fallback);
}

export function getLookalike(gstin: string, k = 5): Promise<ApiResult<LookalikeResp>> {
  return safeGet<LookalikeResp>(`/api/embed/lookalike/${gstin}?k=${k}`, lookMockFor(gstin, k));
}
