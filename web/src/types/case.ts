// Canonical investigation "Case" contract — mirrors backend graphgst/schemas.py.
// The Case API returns everything the investigation workspace needs in ONE
// response, so the UI never reassembles a case from 6-10 unrelated calls.
// See docs/INVESTIGATION_MODEL.md.

export type Band = 'LOW' | 'MED' | 'HIGH' | 'CRITICAL';
// Mirrors backend schemas.InvestigationStatus. The canonical status
// lifecycle persisted via PATCH /api/cases/{id}.
export type InvestigationStatus =
  | 'open' | 'investigating' | 'escalated' | 'resolved' | 'dismissed';

export interface CaseReason {
  name: string;
  weight: number;
  detail: string;
  evidence: Record<string, unknown>;
  scorer?: string | null;
  contribution?: number | null;
}

export interface RiskScore {
  score: number;          // canonical 0-1
  score_100: number;      // 0-100 mirror
  band: Band;
  contributions: Record<string, number>;
  reasons: CaseReason[];
  scorers_fired: string[];
  scorers_run: string[];
  materialized: boolean;  // true = read from a materialized node; false = composed live
  scored_at?: string | null;
}

export interface EntityRef {
  gstin_id: string;
  name?: string | null;
  state_code?: string | null;
  status?: string | null;
  scenario?: string | null;
}

export interface RingEdge {
  src: string;
  dst: string;
  invoice_id: string;
  date?: string | null;
  amount: number;
  gst_amount: number;
  vehicle_id?: string | null;
  hsn?: string | null;
}

export interface RingSummary {
  ring_id: string;
  score: number;
  band?: Band | null;
  members: string[];
  member_count: number;
  invoices: string[];
  invoice_count: number;
  hops: number;
  date_span_days: number;
  total_gst: number;
  signals: Record<string, number>;
  contribution: Record<string, number>;
  share: Record<string, number>;
  break_edge?: Record<string, unknown> | null;
  temporal?: Record<string, unknown> | null;
  velocity_inr_per_day?: number | null;
  edges: RingEdge[];
}

export interface MatchEventOut {
  event_id: string;
  outcome: string;
  severity: string;
  delta?: number | null;
  at?: string | null;
  invoice_id?: string | null;
  supplier_gstin?: string | null;
  buyer_gstin?: string | null;
  role?: 'supplier' | 'buyer' | null;
  reasons: CaseReason[];
}

export interface RelatedVendor {
  gstin_id: string;
  name?: string | null;
  similarity: number;
  risk_score?: number | null;
  band?: Band | null;
  shares_ring: boolean;
}

export interface ExposureBreakdown {
  total_inr: number;
  by_outcome: Record<string, number>;
  invoice_count: number;
}

export interface CaseTimelineEvent {
  date: string;
  kind: string;
  label: string;
  ref?: string | null;
  amount?: number | null;
  gst?: number | null;
}

export interface MaterializationInfo {
  materialized_at?: string | null;
  stale: boolean;
  fingerprint: Record<string, number>;
  current_fingerprint: Record<string, number>;
  n_scored: number;
  composer_version?: string | null;
}

export interface CaseSubgraph {
  nodes: Array<{ data: Record<string, unknown> }>;
  edges: Array<{ data: Record<string, unknown> }>;
}

export interface CaseListItem {
  case_id: string;
  gstin_id: string;
  name?: string | null;
  state_code?: string | null;
  status?: string | null;
  scenario?: string | null;
  risk_score: number;
  band: Band;
  exposure_inr: number;
  ring_ids: string[];
  ring_count: number;
  top_reasons: string[];
  primary_signal?: string | null;
  investigation_status: InvestigationStatus;
}

export interface CaseList {
  count: number;
  band_counts: Record<string, number>;
  materialization: MaterializationInfo;
  cases: CaseListItem[];
}

export interface InvestigationCase {
  case_id: string;
  entity: EntityRef;
  risk: RiskScore;
  exposure: ExposureBreakdown;
  rings: RingSummary[];
  reconciliation: MatchEventOut[];
  related_vendors: RelatedVendor[];
  timeline: CaseTimelineEvent[];
  subgraph?: CaseSubgraph | null;
  investigation_status: InvestigationStatus;
  latest_activity?: string | null;
  generated_at?: string | null;
  materialization: MaterializationInfo;
}
