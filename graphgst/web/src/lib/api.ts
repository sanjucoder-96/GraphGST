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
  Ring,
  Vendor
} from '../types/domain';
import {
  MOCK_AUDIT_TRAILS,
  MOCK_DASHBOARD,
  MOCK_GRAPH,
  MOCK_RINGS,
  MOCK_VENDORS
} from './mocks';

export const API_BASE = 'http://localhost:8000';
const TIMEOUT_MS = 2500;
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
export function getVendorRisk(): Promise<ApiResult<Vendor[]>> {
  return safeGet<Vendor[]>('/api/vendors/risk', MOCK_VENDORS);
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
