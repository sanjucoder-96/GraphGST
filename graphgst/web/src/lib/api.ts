// Typed fetch wrappers with mock fallback.
//
// Every call:
//   1. AbortSignal-limited to TIMEOUT_MS.
//   2. On network error / non-2xx: resolves from src/lib/mocks.ts and marks
//      the app as DEMO for the next 30s.
//   3. Never throws — the UI never needs a try/catch for backend flakiness.

import type {
  AgentResponse,
  AuditTrail,
  DashboardSummary,
  GraphPayload,
  LookalikeResp,
  ModelCard,
  Ring,
  Vendor
} from '../types/domain';
import {
  MOCK_AUDIT_TRAILS,
  MOCK_DASHBOARD,
  MOCK_GRAPH,
  lookMockFor,
  MOCK_MODEL_CARD,
  MOCK_RINGS,
  MOCK_VENDORS
} from './mocks';

// API base is configurable via VITE_API_BASE so the backend can run on any
// host/port (e.g. when :8000 is taken). Defaults to :8000 for the standard
// local/docker setup. Set VITE_API_BASE in web/.env.local to override.
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ||
  'http://localhost:8000';
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
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort('timeout'), TIMEOUT_MS);
    const res = await fetch(API_BASE + path, { signal: ctrl.signal });
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
/** Normalize the LIVE /api/vendors/risk payload into the Vendor[] shape the UI
 *  renders. The backend returns `{vendors:[…], summary}` where each vendor uses
 *  `gstin_id`, a 0-100 `risk_score`, `risk_level`, and `flags` — while the UI
 *  (and the mocks) use `gstin`, a 0-1 `risk_score`, `severity`, and `reasons`.
 *  Without this adapter the live Case Queue rendered zero rows. Fields the
 *  endpoint doesn't provide (exposure, rings, sparkline) default safely. */
function normalizeLiveVendors(raw: unknown): Vendor[] {
  const list: any[] = Array.isArray(raw) ? raw : ((raw as any)?.vendors ?? []);
  const sev: Record<string, 'high' | 'med' | 'low'> =
    { HIGH: 'high', CRITICAL: 'high', MEDIUM: 'med', MED: 'med', LOW: 'low' };
  return list.map((v: any): Vendor => {
    const raw01 = typeof v.risk_score === 'number' ? v.risk_score : 0;
    const score = raw01 > 1 ? raw01 / 100 : raw01;   // live is 0-100, UI is 0-1
    const gstin = v.gstin_id ?? v.gstin ?? '';
    return {
      gstin,
      name: v.name ?? gstin ?? 'Unknown entity',
      state: v.state ?? '',
      pan: v.pan ?? (gstin ? String(gstin).slice(2, 12) : ''),
      incorp_date: v.incorp_date ?? '',
      risk_score: score,
      anomaly_score: typeof v.anomaly_score === 'number' ? v.anomaly_score : 0,
      rings: Array.isArray(v.rings) ? v.rings : [],
      exposure_inr: typeof v.exposure_inr === 'number' ? v.exposure_inr : 0,
      first_seen: v.first_seen ?? '',
      last_seen: v.last_seen ?? '',
      reasons: Array.isArray(v.reasons) ? v.reasons
             : Array.isArray(v.flags) ? v.flags : [],
      sparkline: Array.isArray(v.sparkline) ? v.sparkline : [],
      severity: sev[String(v.risk_level ?? '').toUpperCase()]
             ?? (score >= 0.75 ? 'high' : score >= 0.4 ? 'med' : 'low'),
      scenario: v.scenario ?? '',
      entity_type: (v.entity_type ?? 'vendor') as Vendor['entity_type'],
      assignee: v.assignee,
    };
  });
}

export async function getVendorRisk(): Promise<ApiResult<Vendor[]>> {
  const res = await safeGet<unknown>('/api/vendors/risk', MOCK_VENDORS);
  if (res.fromMock) return res as ApiResult<Vendor[]>;
  return { ...res, data: normalizeLiveVendors(res.data) };
}

/** Normalize the modern composer's /api/risk/summary `top[]` into Vendor[].
 *  The composer returns the explainable shape (score 0-1, band, reasons with
 *  `detail`) enriched server-side with name/state/scenario. This is the
 *  investigation queue's primary source: it is ~3.5× faster than the legacy
 *  vendor-risk endpoint and its `reasons` carry real evidence text. */
function normalizeComposerRows(raw: unknown): Vendor[] {
  const rows: any[] = (raw as any)?.top ?? (Array.isArray(raw) ? raw : []);
  const sev: Record<string, 'high' | 'med' | 'low'> =
    { CRITICAL: 'high', HIGH: 'high', MED: 'med', MEDIUM: 'med', LOW: 'low' };
  return rows.map((r: any): Vendor => {
    const gstin = r.gstin_id ?? r.gstin ?? '';
    const score = typeof r.score === 'number' ? r.score : 0;
    const reasons: string[] = Array.isArray(r.reasons)
      ? r.reasons.map((x: any) => (typeof x === 'string' ? x : (x.detail ?? x.name ?? ''))).filter(Boolean)
      : [];
    return {
      gstin,
      name: r.name ?? gstin ?? 'Unknown entity',
      state: r.state ?? '',
      pan: gstin ? String(gstin).slice(2, 12) : '',
      incorp_date: '',
      risk_score: score,
      anomaly_score: 0,
      rings: Array.isArray(r.rings) ? r.rings : [],
      exposure_inr: typeof r.exposure_inr === 'number' ? r.exposure_inr : 0,
      first_seen: '',
      last_seen: '',
      reasons,
      sparkline: [],
      severity: sev[String(r.band ?? '').toUpperCase()]
             ?? (score >= 0.75 ? 'high' : score >= 0.4 ? 'med' : 'low'),
      scenario: r.scenario ?? '',
      entity_type: 'vendor',
      assignee: undefined,
    };
  });
}

/** Investigation queue: modern composed risk, enriched + normalized. Falls back
 *  to demo fixtures when the backend is unreachable. */
export async function getCases(): Promise<ApiResult<Vendor[]>> {
  const res = await safeGet<unknown>('/api/risk/summary?limit=200', MOCK_VENDORS);
  if (res.fromMock) return res as ApiResult<Vendor[]>;
  return { ...res, data: normalizeComposerRows(res.data) };
}
export function getGraphFull(): Promise<ApiResult<GraphPayload>> {
  return safeGet<GraphPayload>('/api/graph/full', MOCK_GRAPH);
}
export function getAuditTrail(invoiceId: string): Promise<ApiResult<AuditTrail>> {
  const local = MOCK_AUDIT_TRAILS.find(a => a.invoice_id === invoiceId) ?? MOCK_AUDIT_TRAILS[0];
  return safeGet<AuditTrail>(`/api/reconcile/audit-trail/${invoiceId}`, local);
}
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

export function getLookalike(gstin: string, k = 5): Promise<ApiResult<LookalikeResp>> {
  return safeGet<LookalikeResp>(`/api/embed/lookalike/${gstin}?k=${k}`, lookMockFor(gstin, k));
}
