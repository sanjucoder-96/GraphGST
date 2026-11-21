// Domain types shared across the app.
// Aligned with graphgst backend (rings/api.py, reconcile/, main.py).

export type SignalKey = 'C' | 'V' | 'T' | 'R' | 'N' | 'H';

export interface Signals {
  C: number; // Closure strength
  V: number; // Value similarity
  T: number; // Temporal compactness
  R: number; // Recurrence
  N: number; // Network signal
  H: number; // Historical prior
}

export interface RingEdge {
  src: string;
  dst: string;
  invoice_id: string;
  date: string;         // ISO YYYY-MM-DD
  amount: number;       // taxable value (INR)
  gst_amount: number;
  vehicle_id: string | null;
  hsn: string | null;
  pin_prefix: string | null;
}

export interface PerEdge {
  invoice_id: string;
  src: string;
  dst: string;
  score_after: number;  // counterfactual score if this edge removed
  score_drop: number;   // = score - score_after
}

export interface BreakEdge {
  src: string;
  dst: string;
  invoice_id: string;
  score_after: number;
  score_drop: number;
  rationale?: string;
}

export interface Ring {
  ring_id: string;
  members: string[];
  invoices?: string[];
  edges: RingEdge[];
  per_edge: PerEdge[];
  hops?: number;
  date_span_days: number;
  total_gst: number;
  score: number;
  signals: Signals;
  contribution: Signals;
  share: Signals;
  break_edge: BreakEdge | null;

  // demo / UI metadata (from mocks; ignored on live if missing)
  size?: number;
  scenario?: string;
  first_seen?: string;   // ISO
  xai_confidence?: number;
  status?: 'open' | 'reviewing' | 'closed';
  assignee?: string;
  exposure_inr?: number;
  severity?: 'high' | 'med' | 'low';
  primary_evidence?: string;
  reason_chips?: string[];
  sparkline?: number[];
}

// ---- Graph payload -------------------------------------------------------

export type NodeType = 'gstin' | 'invoice' | 'ring' | 'vehicle' | 'taxpayment';

export interface GraphNode {
  data: {
    id: string;
    label: string;
    type: NodeType;
    gstin_short?: string;
    risk?: number;
    ring_id?: string;
  };
}

export interface GraphEdge {
  data: {
    id: string;
    source: string;
    target: string;
    amount?: number;
    date?: string;
    invoice_id?: string;
    kind?: string;
  };
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---- Vendors -------------------------------------------------------------

export interface Vendor {
  gstin: string;
  name: string;
  state: string;
  pan: string;
  incorp_date: string;
  risk_score: number;
  anomaly_score: number;
  rings: string[];
  exposure_inr: number;
  first_seen: string;
  last_seen: string;
  reasons: string[];
  sparkline: number[];
  severity: 'high' | 'med' | 'low';
  scenario: string;
  entity_type: 'vendor' | 'buyer' | 'transporter';
  assignee?: string;
}

// ---- Audit trail ---------------------------------------------------------

export type HopStatus = 'ok' | 'warn' | 'fail' | 'info';

export interface AuditHop {
  hop: number;
  node_type: string;
  node_id: string;
  label: string;
  ok: boolean;
  status: HopStatus;
  detail: string;
  narrative: string;
}

export type OverallStatus = 'MATCH' | 'MISMATCH' | 'MISSING' | 'PARTIAL' | 'DUPLICATE' | 'OK';
export type ItcStatus = 'ELIGIBLE' | 'BLOCKED' | 'CONDITIONAL' | 'PENDING';

export interface AuditTrail {
  invoice_id: string;
  overall_status: OverallStatus;
  audit_summary: string;
  itc_status: ItcStatus;
  failed_checkpoints: string[];
  hops: AuditHop[];
}

// ---- Dashboard summary ---------------------------------------------------

export interface DashboardSummary {
  neo4j: boolean;
  rings_open: number;
  vendors_high: number;
  exposure_total: number;   // INR
  last_detection_at: string | null;
  latency_ms: number;
}

// ---- Agent response ------------------------------------------------------

export interface AgentResponse {
  intent: string;
  text: string | null;
  xai_confidence?: number;
  error?: string;
}

// ---- Lookalike (Phase 5 embeddings) --------------------------------------

export interface LookalikeNeighbour {
  gstin_id: string;
  similarity: number;
}

export interface LookalikeResp {
  gstin_id: string;
  k: number;
  neighbours: LookalikeNeighbour[];
}

// ---- Model card (Phase 7 benchmarks) -------------------------------------

export type ModelCardStatus =
  | 'IMPROVED' | 'UNCHANGED' | 'REGRESSED' | 'NEW' | 'MISSING' | 'INFO';

export interface ModelCardEntry {
  module: string;
  metric: string;
  headline: string;
  value: number | null;
  baseline: number | null;
  delta: number | null;
  status: ModelCardStatus;
  unit: string;
  notes: string;
}

export interface ModelCard {
  generated_at: string | null;
  git_commit: string | null;
  dataset_config: Record<string, unknown> | null;
  tolerance_abs: number | null;
  overall_pass: boolean | null;
  cards: ModelCardEntry[];
}

// ---- Toast ---------------------------------------------------------------

export interface ToastMsg {
  id: string;
  kind: 'info' | 'ok' | 'warn' | 'bad';
  title: string;
  body?: string;
  ts: number;
}
