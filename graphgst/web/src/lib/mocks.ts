// Mock dataset — used when the FastAPI backend is unreachable.
// Every number in this file is labelled DEMO. The frontend surfaces DEMO on the
// environment badge whenever any of these values reaches the UI.
//
// Composition:
//   - 3 detected rings with real 6-signal scores that discriminate against 2
//     noise rings whose scores are deliberately low.
//   - 12 distinct GSTINs across the rings and vendor table.
//   - 8 audit trails (one per invoice covering ring 1 fully, plus first two
//     invoices from rings 2 and 3) with 8 narrative hops each.
//   - Graph payload derived from the rings so Cytoscape has a real substrate.

import type {
  AuditTrail,
  DashboardSummary,
  GraphEdge,
  GraphNode,
  GraphPayload,
  Ring,
  Vendor
} from '../types/domain';

// ---- Utility: derive per_edge from a small counterfactual model ---------
// score_drop is highest for the "longest chord" (median-amount edge in a
// short cycle). This is only for DEMO fixture — the backend computes the
// real value in rings/counterfactual.py.

function derivePerEdge(score: number, edges: Ring['edges']): Ring['per_edge'] {
  const n = edges.length;
  const drops = edges.map((e, i) => {
    // pseudo-scored by amount rank + position in cycle
    const rank = 0.15 + 0.55 * ((n - i) / n);
    const amountBias = Math.min(0.35, e.amount / 40_00_000);
    return Math.min(0.42, rank * 0.6 + amountBias * 0.4);
  });
  const maxDrop = Math.max(...drops);
  const norm = drops.map((d) => d * (0.32 / maxDrop));
  return edges.map((e, i) => ({
    invoice_id: e.invoice_id,
    src: e.src,
    dst: e.dst,
    score_after: Math.max(0, +(score - norm[i]).toFixed(3)),
    score_drop: +norm[i].toFixed(3)
  }));
}

// ---- 12 GSTINs across three real rings + shared assets -----------------

export const MOCK_GSTINS: ReadonlyArray<{ id: string; name: string; state: string; pan: string; incorp_date: string; }> = [
  { id: '27ABCDE1234F1Z5', name: 'Meridian Traders',      state: 'MH', pan: 'ABCDE1234F', incorp_date: '2019-06-14' },
  { id: '27BCDEF2345G2Z6', name: 'Halo Distributors',     state: 'MH', pan: 'BCDEF2345G', incorp_date: '2020-01-22' },
  { id: '27CDEFG3456H3Z7', name: 'Amber Trade Co',        state: 'MH', pan: 'CDEFG3456H', incorp_date: '2018-11-03' },
  { id: '27DEFGH4567I4Z8', name: 'Sable Enterprises',     state: 'MH', pan: 'DEFGH4567I', incorp_date: '2021-04-09' },
  { id: '07EFGHI5678J5Z9', name: 'Delta Logistics',       state: 'DL', pan: 'EFGHI5678J', incorp_date: '2017-08-30' },
  { id: '07FGHIJ6789K6Z0', name: 'Prakash Holdings',      state: 'DL', pan: 'FGHIJ6789K', incorp_date: '2016-02-12' },
  { id: '07GHIJK7890L7Z1', name: 'Iron Ledger Corp',      state: 'DL', pan: 'GHIJK7890L', incorp_date: '2018-05-27' },
  { id: '07HIJKL8901M8Z2', name: 'Nomad Metals',          state: 'DL', pan: 'HIJKL8901M', incorp_date: '2020-10-16' },
  { id: '07IJKLM9012N9Z3', name: 'Ridgeline Traders',     state: 'DL', pan: 'IJKLM9012N', incorp_date: '2021-12-01' },
  { id: '29JKLMN0123O0Z4', name: 'Kaveri Steel Works',    state: 'KA', pan: 'JKLMN0123O', incorp_date: '2015-07-19' },
  { id: '29KLMNO1234P1Z5', name: 'Bharat Alloys',         state: 'KA', pan: 'KLMNO1234P', incorp_date: '2019-09-05' },
  { id: '29LMNOP2345Q2Z6', name: 'Southern Ferrous',      state: 'KA', pan: 'LMNOP2345Q', incorp_date: '2020-03-28' }
];

// ---- Ring 1: RING-2024-A417 — 4 members, tight closure ------------------
const R1_EDGES: Ring['edges'] = [
  { src: '27ABCDE1234F1Z5', dst: '27BCDEF2345G2Z6', invoice_id: 'INV-A417-001', date: '2024-03-04', amount: 12_45_000, gst_amount: 2_24_100, vehicle_id: 'MH12-KA-7788', hsn: '7208', pin_prefix: '4001' },
  { src: '27BCDEF2345G2Z6', dst: '27CDEFG3456H3Z7', invoice_id: 'INV-A417-002', date: '2024-03-05', amount: 12_60_000, gst_amount: 2_26_800, vehicle_id: 'MH12-KA-7788', hsn: '7208', pin_prefix: '4001' },
  { src: '27CDEFG3456H3Z7', dst: '27DEFGH4567I4Z8', invoice_id: 'INV-A417-003', date: '2024-03-07', amount: 12_30_000, gst_amount: 2_21_400, vehicle_id: 'MH12-KA-7788', hsn: '7208', pin_prefix: '4001' },
  { src: '27DEFGH4567I4Z8', dst: '27ABCDE1234F1Z5', invoice_id: 'INV-A417-004', date: '2024-03-08', amount: 12_55_000, gst_amount: 2_25_900, vehicle_id: 'MH12-KA-7788', hsn: '7208', pin_prefix: '4001' }
];

const RING_1: Ring = {
  ring_id: 'RING-2024-A417',
  members: ['27ABCDE1234F1Z5', '27BCDEF2345G2Z6', '27CDEFG3456H3Z7', '27DEFGH4567I4Z8'],
  invoices: R1_EDGES.map(e => e.invoice_id),
  edges: R1_EDGES,
  per_edge: [], // filled below
  hops: 4,
  date_span_days: 5,
  total_gst: R1_EDGES.reduce((s, e) => s + e.gst_amount, 0),
  score: 0.812,
  signals:      { C: 0.92, V: 0.83, T: 0.88, R: 0.71, N: 0.66, H: 0.79 },
  contribution: { C: 0.19, V: 0.14, T: 0.18, R: 0.14, N: 0.13, H: 0.22 },
  share:        { C: 0.23, V: 0.17, T: 0.22, R: 0.13, N: 0.11, H: 0.14 },
  break_edge: {
    src: '27BCDEF2345G2Z6', dst: '27CDEFG3456H3Z7', invoice_id: 'INV-A417-002',
    score_after: 0.492, score_drop: 0.320,
    rationale: 'Median-amount chord across the cycle. Removing this edge severs the closure loop.'
  },
  size: 4,
  scenario: 'circular_itc_chain',
  first_seen: '2024-03-09T09:12:00Z',
  xai_confidence: 0.87,
  status: 'open',
  assignee: 'audit-4',
  exposure_inr: 8_98_200,
  severity: 'high',
  primary_evidence: 'Shared vehicle MH12-KA-7788 across 4 legs · 5-day span',
  reason_chips: ['same-vehicle', 'value-parity', 'PIN cluster 4001', 'closure hop=4'],
  sparkline: [0.42, 0.48, 0.55, 0.61, 0.66, 0.72, 0.79, 0.81]
};
RING_1.per_edge = derivePerEdge(RING_1.score, RING_1.edges);

// ---- Ring 2: RING-2024-B209 — 5 members, longer chain -------------------
const R2_EDGES: Ring['edges'] = [
  { src: '07EFGHI5678J5Z9', dst: '07FGHIJ6789K6Z0', invoice_id: 'INV-B209-001', date: '2024-04-11', amount: 8_20_000, gst_amount: 1_47_600, vehicle_id: 'DL01-BB-5501', hsn: '3901', pin_prefix: '1100' },
  { src: '07FGHIJ6789K6Z0', dst: '07GHIJK7890L7Z1', invoice_id: 'INV-B209-002', date: '2024-04-12', amount: 8_25_000, gst_amount: 1_48_500, vehicle_id: 'DL01-BB-5501', hsn: '3901', pin_prefix: '1100' },
  { src: '07GHIJK7890L7Z1', dst: '07HIJKL8901M8Z2', invoice_id: 'INV-B209-003', date: '2024-04-14', amount: 8_10_000, gst_amount: 1_45_800, vehicle_id: 'DL01-CC-6612', hsn: '3901', pin_prefix: '1100' },
  { src: '07HIJKL8901M8Z2', dst: '07IJKLM9012N9Z3', invoice_id: 'INV-B209-004', date: '2024-04-16', amount: 8_35_000, gst_amount: 1_50_300, vehicle_id: 'DL01-CC-6612', hsn: '3901', pin_prefix: '1100' },
  { src: '07IJKLM9012N9Z3', dst: '07EFGHI5678J5Z9', invoice_id: 'INV-B209-005', date: '2024-04-18', amount: 8_15_000, gst_amount: 1_46_700, vehicle_id: 'DL01-BB-5501', hsn: '3901', pin_prefix: '1100' }
];

const RING_2: Ring = {
  ring_id: 'RING-2024-B209',
  members: ['07EFGHI5678J5Z9', '07FGHIJ6789K6Z0', '07GHIJK7890L7Z1', '07HIJKL8901M8Z2', '07IJKLM9012N9Z3'],
  invoices: R2_EDGES.map(e => e.invoice_id),
  edges: R2_EDGES,
  per_edge: [],
  hops: 5,
  date_span_days: 8,
  total_gst: R2_EDGES.reduce((s, e) => s + e.gst_amount, 0),
  score: 0.766,
  signals:      { C: 0.88, V: 0.90, T: 0.75, R: 0.68, N: 0.72, H: 0.70 },
  contribution: { C: 0.18, V: 0.16, T: 0.15, R: 0.13, N: 0.14, H: 0.15 },
  share:        { C: 0.20, V: 0.19, T: 0.18, R: 0.13, N: 0.15, H: 0.15 },
  break_edge: {
    src: '07GHIJK7890L7Z1', dst: '07HIJKL8901M8Z2', invoice_id: 'INV-B209-003',
    score_after: 0.481, score_drop: 0.285,
    rationale: 'Vehicle handover leg. Break here disconnects the two sub-chains that made the loop close.'
  },
  size: 5,
  scenario: 'polymer_layered_ring',
  first_seen: '2024-04-19T14:30:00Z',
  xai_confidence: 0.82,
  status: 'open',
  assignee: 'audit-2',
  exposure_inr: 7_38_900,
  severity: 'high',
  primary_evidence: 'Two rented vehicles alternating across 5 legs · same PIN 1100',
  reason_chips: ['vehicle-alternation', 'value-parity', 'HSN=3901', 'shared director'],
  sparkline: [0.36, 0.42, 0.48, 0.55, 0.61, 0.66, 0.73, 0.77]
};
RING_2.per_edge = derivePerEdge(RING_2.score, RING_2.edges);

// ---- Ring 3: RING-2024-C083 — 3 members, tight temporal window ---------
const R3_EDGES: Ring['edges'] = [
  { src: '29JKLMN0123O0Z4', dst: '29KLMNO1234P1Z5', invoice_id: 'INV-C083-001', date: '2024-05-02', amount: 24_00_000, gst_amount: 4_32_000, vehicle_id: 'KA05-DD-9902', hsn: '7208', pin_prefix: '5600' },
  { src: '29KLMNO1234P1Z5', dst: '29LMNOP2345Q2Z6', invoice_id: 'INV-C083-002', date: '2024-05-03', amount: 24_08_000, gst_amount: 4_33_440, vehicle_id: 'KA05-DD-9902', hsn: '7208', pin_prefix: '5600' },
  { src: '29LMNOP2345Q2Z6', dst: '29JKLMN0123O0Z4', invoice_id: 'INV-C083-003', date: '2024-05-04', amount: 24_04_000, gst_amount: 4_32_720, vehicle_id: 'KA05-DD-9902', hsn: '7208', pin_prefix: '5600' }
];

const RING_3: Ring = {
  ring_id: 'RING-2024-C083',
  members: ['29JKLMN0123O0Z4', '29KLMNO1234P1Z5', '29LMNOP2345Q2Z6'],
  invoices: R3_EDGES.map(e => e.invoice_id),
  edges: R3_EDGES,
  per_edge: [],
  hops: 3,
  date_span_days: 3,
  total_gst: R3_EDGES.reduce((s, e) => s + e.gst_amount, 0),
  score: 0.790,
  signals:      { C: 0.95, V: 0.65, T: 0.92, R: 0.80, N: 0.55, H: 0.85 },
  contribution: { C: 0.21, V: 0.11, T: 0.20, R: 0.15, N: 0.11, H: 0.20 },
  share:        { C: 0.27, V: 0.14, T: 0.25, R: 0.13, N: 0.09, H: 0.12 },
  break_edge: {
    src: '29JKLMN0123O0Z4', dst: '29KLMNO1234P1Z5', invoice_id: 'INV-C083-001',
    score_after: 0.470, score_drop: 0.320,
    rationale: 'Only the opening leg carries a bill-to that matches. Removing it collapses the temporal proof.'
  },
  size: 3,
  scenario: 'flash_steel_triad',
  first_seen: '2024-05-05T06:44:00Z',
  xai_confidence: 0.90,
  status: 'reviewing',
  assignee: 'audit-4',
  exposure_inr: 12_98_160,
  severity: 'high',
  primary_evidence: '3-day round trip · single vehicle · ~₹24 L per leg',
  reason_chips: ['flash-cycle', 'single-vehicle', 'recurrence 4x', 'H prior=0.85'],
  sparkline: [0.31, 0.38, 0.46, 0.54, 0.62, 0.70, 0.76, 0.79]
};
RING_3.per_edge = derivePerEdge(RING_3.score, RING_3.edges);

// ---- Noise Ring 1: legitimate cross-state chain that happens to close ---
const N1_EDGES: Ring['edges'] = [
  { src: '27ABCDE1234F1Z5', dst: '07EFGHI5678J5Z9', invoice_id: 'INV-N014-001', date: '2024-02-11', amount: 3_20_000, gst_amount:   57_600, vehicle_id: null, hsn: '8501', pin_prefix: null },
  { src: '07EFGHI5678J5Z9', dst: '29JKLMN0123O0Z4', invoice_id: 'INV-N014-002', date: '2024-02-19', amount: 4_10_000, gst_amount:   73_800, vehicle_id: null, hsn: '8502', pin_prefix: null },
  { src: '29JKLMN0123O0Z4', dst: '27ABCDE1234F1Z5', invoice_id: 'INV-N014-003', date: '2024-02-28', amount: 2_80_000, gst_amount:   50_400, vehicle_id: null, hsn: '8503', pin_prefix: null }
];

const NOISE_1: Ring = {
  ring_id: 'RING-2024-N014',
  members: ['27ABCDE1234F1Z5', '07EFGHI5678J5Z9', '29JKLMN0123O0Z4'],
  invoices: N1_EDGES.map(e => e.invoice_id),
  edges: N1_EDGES,
  per_edge: [],
  hops: 3,
  date_span_days: 17,
  total_gst: N1_EDGES.reduce((s, e) => s + e.gst_amount, 0),
  score: 0.221,
  signals:      { C: 0.42, V: 0.18, T: 0.21, R: 0.15, N: 0.11, H: 0.25 },
  contribution: { C: 0.09, V: 0.03, T: 0.04, R: 0.02, N: 0.02, H: 0.06 },
  share:        { C: 0.34, V: 0.12, T: 0.14, R: 0.10, N: 0.07, H: 0.16 },
  break_edge: null,
  size: 3,
  scenario: 'cross_state_chain',
  first_seen: '2024-02-29T11:00:00Z',
  xai_confidence: 0.34,
  status: 'closed',
  exposure_inr: 1_81_800,
  severity: 'low',
  primary_evidence: 'Round trip inside 3 weeks but distinct HSNs and no shared vehicle',
  reason_chips: ['different HSNs', 'no vehicle overlap', '17-day span'],
  sparkline: [0.19, 0.20, 0.21, 0.21, 0.22, 0.22, 0.22, 0.22]
};
NOISE_1.per_edge = derivePerEdge(NOISE_1.score, NOISE_1.edges);

// ---- Noise Ring 2 -------------------------------------------------------
const N2_EDGES: Ring['edges'] = [
  { src: '27BCDEF2345G2Z6', dst: '07FGHIJ6789K6Z0', invoice_id: 'INV-N022-001', date: '2024-02-05', amount: 1_15_000, gst_amount: 20_700, vehicle_id: null, hsn: '9403', pin_prefix: null },
  { src: '07FGHIJ6789K6Z0', dst: '29KLMNO1234P1Z5', invoice_id: 'INV-N022-002', date: '2024-02-13', amount: 1_20_000, gst_amount: 21_600, vehicle_id: null, hsn: '9403', pin_prefix: null },
  { src: '29KLMNO1234P1Z5', dst: '27DEFGH4567I4Z8', invoice_id: 'INV-N022-003', date: '2024-02-24', amount:   95_000, gst_amount: 17_100, vehicle_id: null, hsn: '9404', pin_prefix: null },
  { src: '27DEFGH4567I4Z8', dst: '27BCDEF2345G2Z6', invoice_id: 'INV-N022-004', date: '2024-03-02', amount: 1_05_000, gst_amount: 18_900, vehicle_id: null, hsn: '9403', pin_prefix: null }
];

const NOISE_2: Ring = {
  ring_id: 'RING-2024-N022',
  members: ['27BCDEF2345G2Z6', '07FGHIJ6789K6Z0', '29KLMNO1234P1Z5', '27DEFGH4567I4Z8'],
  invoices: N2_EDGES.map(e => e.invoice_id),
  edges: N2_EDGES,
  per_edge: [],
  hops: 4,
  date_span_days: 25,
  total_gst: N2_EDGES.reduce((s, e) => s + e.gst_amount, 0),
  score: 0.281,
  signals:      { C: 0.55, V: 0.25, T: 0.30, R: 0.20, N: 0.15, H: 0.35 },
  contribution: { C: 0.11, V: 0.04, T: 0.06, R: 0.03, N: 0.03, H: 0.09 },
  share:        { C: 0.32, V: 0.14, T: 0.17, R: 0.11, N: 0.08, H: 0.18 },
  break_edge: null,
  size: 4,
  scenario: 'wide_span_low_value',
  first_seen: '2024-03-03T08:20:00Z',
  xai_confidence: 0.29,
  status: 'closed',
  exposure_inr:   78_300,
  severity: 'low',
  primary_evidence: '25-day loop with sub-lakh invoices and mixed HSNs',
  reason_chips: ['small values', 'wide temporal span', 'mixed HSNs'],
  sparkline: [0.22, 0.24, 0.26, 0.27, 0.28, 0.28, 0.28, 0.28]
};
NOISE_2.per_edge = derivePerEdge(NOISE_2.score, NOISE_2.edges);

// ---- Assembled ring list (score-sorted, real rings first) ---------------
export const MOCK_RINGS: Ring[] = [RING_1, RING_3, RING_2, NOISE_2, NOISE_1];

// ---- Vendors ------------------------------------------------------------

export const MOCK_VENDORS: Vendor[] = [
  {
    gstin: '27ABCDE1234F1Z5', name: 'Meridian Traders',   state: 'MH', pan: 'ABCDE1234F', incorp_date: '2019-06-14',
    risk_score: 0.81, anomaly_score: 0.68, rings: ['RING-2024-A417'], exposure_inr: 8_98_200,
    first_seen: '2024-03-09T09:12:00Z', last_seen: '2024-05-11T14:22:00Z',
    reasons: ['ring member RING-2024-A417', 'vehicle re-use MH12-KA-7788', 'PIN cluster 4001'],
    sparkline: [0.42, 0.48, 0.55, 0.61, 0.66, 0.72, 0.79, 0.81],
    severity: 'high', scenario: 'circular_itc_chain', entity_type: 'vendor', assignee: 'audit-4'
  },
  {
    gstin: '27BCDEF2345G2Z6', name: 'Halo Distributors',  state: 'MH', pan: 'BCDEF2345G', incorp_date: '2020-01-22',
    risk_score: 0.77, anomaly_score: 0.61, rings: ['RING-2024-A417'], exposure_inr: 2_26_800,
    first_seen: '2024-03-09T09:12:00Z', last_seen: '2024-05-11T14:22:00Z',
    reasons: ['recommended break-edge holder', 'value parity 0.98'],
    sparkline: [0.41, 0.47, 0.52, 0.58, 0.63, 0.69, 0.74, 0.77],
    severity: 'high', scenario: 'circular_itc_chain', entity_type: 'vendor'
  },
  {
    gstin: '27CDEFG3456H3Z7', name: 'Amber Trade Co',     state: 'MH', pan: 'CDEFG3456H', incorp_date: '2018-11-03',
    risk_score: 0.74, anomaly_score: 0.54, rings: ['RING-2024-A417'], exposure_inr: 2_21_400,
    first_seen: '2024-03-09T09:12:00Z', last_seen: '2024-05-11T14:22:00Z',
    reasons: ['ring member', 'PAN clustered with 3 others'],
    sparkline: [0.36, 0.42, 0.48, 0.55, 0.61, 0.66, 0.70, 0.74],
    severity: 'high', scenario: 'circular_itc_chain', entity_type: 'buyer'
  },
  {
    gstin: '29JKLMN0123O0Z4', name: 'Kaveri Steel Works', state: 'KA', pan: 'JKLMN0123O', incorp_date: '2015-07-19',
    risk_score: 0.79, anomaly_score: 0.72, rings: ['RING-2024-C083'], exposure_inr: 12_98_160,
    first_seen: '2024-05-05T06:44:00Z', last_seen: '2024-05-11T09:15:00Z',
    reasons: ['flash 3-day loop', 'recurrence 4 prior sightings'],
    sparkline: [0.31, 0.38, 0.46, 0.54, 0.62, 0.70, 0.76, 0.79],
    severity: 'high', scenario: 'flash_steel_triad', entity_type: 'vendor', assignee: 'audit-4'
  },
  {
    gstin: '07EFGHI5678J5Z9', name: 'Delta Logistics',    state: 'DL', pan: 'EFGHI5678J', incorp_date: '2017-08-30',
    risk_score: 0.68, anomaly_score: 0.51, rings: ['RING-2024-B209'], exposure_inr: 2_94_300,
    first_seen: '2024-04-19T14:30:00Z', last_seen: '2024-05-11T14:22:00Z',
    reasons: ['ring member', 'director overlap with RIDG', 'vehicle DL01-BB-5501 twice'],
    sparkline: [0.36, 0.42, 0.48, 0.55, 0.60, 0.63, 0.65, 0.68],
    severity: 'med', scenario: 'polymer_layered_ring', entity_type: 'transporter', assignee: 'audit-2'
  },
  {
    gstin: '07FGHIJ6789K6Z0', name: 'Prakash Holdings',   state: 'DL', pan: 'FGHIJ6789K', incorp_date: '2016-02-12',
    risk_score: 0.63, anomaly_score: 0.44, rings: ['RING-2024-B209'], exposure_inr: 1_48_500,
    first_seen: '2024-04-19T14:30:00Z', last_seen: '2024-05-11T14:22:00Z',
    reasons: ['ring member', 'HSN 3901 concentration'],
    sparkline: [0.34, 0.39, 0.44, 0.49, 0.53, 0.57, 0.60, 0.63],
    severity: 'med', scenario: 'polymer_layered_ring', entity_type: 'vendor'
  },
  {
    gstin: '07GHIJK7890L7Z1', name: 'Iron Ledger Corp',   state: 'DL', pan: 'GHIJK7890L', incorp_date: '2018-05-27',
    risk_score: 0.61, anomaly_score: 0.42, rings: ['RING-2024-B209'], exposure_inr: 1_45_800,
    first_seen: '2024-04-19T14:30:00Z', last_seen: '2024-05-11T14:22:00Z',
    reasons: ['ring member', 'recommended break holder'],
    sparkline: [0.32, 0.36, 0.41, 0.46, 0.50, 0.54, 0.58, 0.61],
    severity: 'med', scenario: 'polymer_layered_ring', entity_type: 'vendor'
  },
  {
    gstin: '29KLMNO1234P1Z5', name: 'Bharat Alloys',      state: 'KA', pan: 'KLMNO1234P', incorp_date: '2019-09-05',
    risk_score: 0.72, anomaly_score: 0.58, rings: ['RING-2024-C083'], exposure_inr: 4_33_440,
    first_seen: '2024-05-05T06:44:00Z', last_seen: '2024-05-11T09:15:00Z',
    reasons: ['flash cycle', 'same vehicle KA05-DD-9902'],
    sparkline: [0.31, 0.36, 0.42, 0.49, 0.55, 0.61, 0.68, 0.72],
    severity: 'high', scenario: 'flash_steel_triad', entity_type: 'buyer'
  },
  {
    gstin: '29LMNOP2345Q2Z6', name: 'Southern Ferrous',   state: 'KA', pan: 'LMNOP2345Q', incorp_date: '2020-03-28',
    risk_score: 0.70, anomaly_score: 0.55, rings: ['RING-2024-C083'], exposure_inr: 4_32_720,
    first_seen: '2024-05-05T06:44:00Z', last_seen: '2024-05-11T09:15:00Z',
    reasons: ['flash cycle', 'H prior 0.85'],
    sparkline: [0.29, 0.34, 0.40, 0.46, 0.52, 0.58, 0.64, 0.70],
    severity: 'high', scenario: 'flash_steel_triad', entity_type: 'vendor'
  },
  {
    gstin: '07HIJKL8901M8Z2', name: 'Nomad Metals',       state: 'DL', pan: 'HIJKL8901M', incorp_date: '2020-10-16',
    risk_score: 0.42, anomaly_score: 0.27, rings: [], exposure_inr: 1_50_300,
    first_seen: '2024-04-16T10:00:00Z', last_seen: '2024-04-19T10:00:00Z',
    reasons: ['isolated leg in ring 2', 'no prior sightings'],
    sparkline: [0.28, 0.30, 0.32, 0.34, 0.36, 0.38, 0.40, 0.42],
    severity: 'med', scenario: 'watchlist', entity_type: 'vendor'
  },
  {
    gstin: '27DEFGH4567I4Z8', name: 'Sable Enterprises',  state: 'MH', pan: 'DEFGH4567I', incorp_date: '2021-04-09',
    risk_score: 0.66, anomaly_score: 0.49, rings: ['RING-2024-A417', 'RING-2024-N022'], exposure_inr: 2_25_900,
    first_seen: '2024-03-09T09:12:00Z', last_seen: '2024-05-11T14:22:00Z',
    reasons: ['closes the ring', 'PAN cluster of 4'],
    sparkline: [0.32, 0.38, 0.44, 0.50, 0.55, 0.60, 0.63, 0.66],
    severity: 'med', scenario: 'circular_itc_chain', entity_type: 'buyer'
  },
  {
    gstin: '07IJKLM9012N9Z3', name: 'Ridgeline Traders',  state: 'DL', pan: 'IJKLM9012N', incorp_date: '2021-12-01',
    risk_score: 0.38, anomaly_score: 0.22, rings: [], exposure_inr:   45_000,
    first_seen: '2024-04-18T12:00:00Z', last_seen: '2024-04-19T10:00:00Z',
    reasons: ['single-invoice contact', 'no ring membership'],
    sparkline: [0.22, 0.24, 0.26, 0.28, 0.30, 0.32, 0.35, 0.38],
    severity: 'low', scenario: 'watchlist', entity_type: 'buyer'
  }
];

// ---- Audit trails (8) — one per invoice --------------------------------

function hop(
  h: number, t: string, id: string, label: string,
  status: 'ok' | 'warn' | 'fail' | 'info',
  detail: string, narrative: string
) {
  return { hop: h, node_type: t, node_id: id, label, ok: status === 'ok', status, detail, narrative };
}

export const MOCK_AUDIT_TRAILS: AuditTrail[] = [
  {
    invoice_id: 'INV-A417-001',
    overall_status: 'DUPLICATE',
    audit_summary: 'Sender GSTR-1 matches, but the recipient claim date sits 41 days after issue, and the invoice appears in a closed ring cycle.',
    itc_status: 'BLOCKED',
    failed_checkpoints: ['temporal_gap', 'ring_membership'],
    hops: [
      hop(1, 'Invoice',      'INV-A417-001',      'Invoice issued',            'ok',   'issued 2024-03-04',                       'The invoice was recorded on GSTR-1 by Meridian Traders on the same day it was issued.'),
      hop(2, 'GSTIN',        '27ABCDE1234F1Z5',   'Sender filed',              'ok',   'GSTR-1 filed 2024-03-10',                 'Sender filed within the month. No mismatch on outward supply.'),
      hop(3, 'GSTIN',        '27BCDEF2345G2Z6',   'Recipient claim',           'warn', 'claim 2024-04-14 (Δ41 days)',             'Recipient waited 41 days to claim ITC, well outside a typical 7-day window.'),
      hop(4, 'Vehicle',      'MH12-KA-7788',      'Vehicle logged',            'warn', 'same vehicle across 4 legs',              'The same vehicle number appears on every hop of this cycle.'),
      hop(5, 'PIN',          '400001',            'Origin PIN',                'info', 'PIN cluster 4001, 3 shared members',      'Origin PIN clusters with two other invoices in the same ring.'),
      hop(6, 'Ring',         'RING-2024-A417',    'Ring closure check',        'fail', 'part of closed cycle (hops=4, C=0.92)',   'Belongs to a 4-hop closed cycle with a C-score of 0.92.'),
      hop(7, 'Anomaly',      'ISOFOREST',         'Anomaly score',             'warn', 'anomaly=0.68',                            'Isolation forest anomaly score is elevated for both counterparties.'),
      hop(8, 'ITC',          'ITC-INV-A417-001',  'ITC decision',              'fail', 'blocked pending SCN',                     'ITC is blocked; case queued for show-cause notice generation.')
    ]
  },
  {
    invoice_id: 'INV-A417-002',
    overall_status: 'MISMATCH',
    audit_summary: 'Recommended break-edge for RING-2024-A417. GSTR-2A vs 3B mismatch of ₹4,200.',
    itc_status: 'CONDITIONAL',
    failed_checkpoints: ['value_mismatch', 'ring_membership'],
    hops: [
      hop(1, 'Invoice', 'INV-A417-002',      'Invoice issued',          'ok',   'issued 2024-03-05',                 'Filed on the day of issue.'),
      hop(2, 'GSTIN',   '27BCDEF2345G2Z6',   'Sender filed',            'ok',   'GSTR-1 filed 2024-03-10',           'No filing gap on sender side.'),
      hop(3, 'GSTIN',   '27CDEFG3456H3Z7',   'Recipient claim',         'ok',   'claim 2024-03-15',                  'Claim timing is normal.'),
      hop(4, 'Value',   'GSTR-2A/3B',        'Value reconciliation',    'fail', '2A: ₹2,26,800 vs 3B: ₹2,22,600',    'Recipient booked ₹4,200 less than the sender reported.'),
      hop(5, 'Vehicle', 'MH12-KA-7788',      'Vehicle logged',          'warn', 'shared across cycle',               'Same vehicle repeats on every leg.'),
      hop(6, 'Ring',    'RING-2024-A417',    'Ring closure check',      'fail', 'break-edge candidate',              'This is the model’s recommended break-edge for the ring.'),
      hop(7, 'Anomaly', 'ISOFOREST',         'Anomaly score',           'warn', 'anomaly=0.61',                      'Elevated anomaly on the counterparty.'),
      hop(8, 'ITC',     'ITC-INV-A417-002',  'ITC decision',            'warn', 'conditional pending value fix',     'ITC allowed once the ₹4,200 delta is reconciled.')
    ]
  },
  {
    invoice_id: 'INV-A417-003',
    overall_status: 'MATCH',
    audit_summary: 'Clean paperwork but the invoice sits inside the closed cycle. Reconciliation matches; ring membership is the sole failure.',
    itc_status: 'BLOCKED',
    failed_checkpoints: ['ring_membership'],
    hops: [
      hop(1, 'Invoice', 'INV-A417-003',      'Invoice issued',     'ok', 'issued 2024-03-07',                 'Filed on day of issue.'),
      hop(2, 'GSTIN',   '27CDEFG3456H3Z7',   'Sender filed',       'ok', 'GSTR-1 filed 2024-03-10',           'No filing gap.'),
      hop(3, 'GSTIN',   '27DEFGH4567I4Z8',   'Recipient claim',    'ok', 'claim 2024-03-13',                  'Normal claim timing.'),
      hop(4, 'Value',   'GSTR-2A/3B',        'Value reconciliation','ok','2A=3B=₹2,21,400',                   'Values reconcile exactly.'),
      hop(5, 'Vehicle', 'MH12-KA-7788',      'Vehicle logged',     'warn','same vehicle repeats',             'Same vehicle number as prior legs.'),
      hop(6, 'Ring',    'RING-2024-A417',    'Ring closure check', 'fail','part of closed cycle',             'Ring membership: hops=4, C=0.92.'),
      hop(7, 'Anomaly', 'ISOFOREST',         'Anomaly score',      'info','anomaly=0.44',                     'Modest anomaly signal on this leg alone.'),
      hop(8, 'ITC',     'ITC-INV-A417-003',  'ITC decision',       'fail','blocked (ring)',                   'Blocked solely on ring closure.')
    ]
  },
  {
    invoice_id: 'INV-A417-004',
    overall_status: 'DUPLICATE',
    audit_summary: 'Closes the loop back to the origin GSTIN. Duplicate vehicle/PIN cluster with 3 prior legs.',
    itc_status: 'BLOCKED',
    failed_checkpoints: ['ring_membership', 'vehicle_reuse'],
    hops: [
      hop(1, 'Invoice', 'INV-A417-004',      'Invoice issued',     'ok',   'issued 2024-03-08',                 'Filed on day of issue.'),
      hop(2, 'GSTIN',   '27DEFGH4567I4Z8',   'Sender filed',       'ok',   'GSTR-1 filed 2024-03-10',           'No filing gap.'),
      hop(3, 'GSTIN',   '27ABCDE1234F1Z5',   'Recipient claim',    'warn', 'claim 2024-03-24 (Δ16 days)',       '16-day gap on claim.'),
      hop(4, 'Value',   'GSTR-2A/3B',        'Value reconciliation','ok',  '2A=3B=₹2,25,900',                   'Values reconcile.'),
      hop(5, 'Vehicle', 'MH12-KA-7788',      'Vehicle logged',     'fail', 'appears on 4 consecutive legs',     'Vehicle reuse is the strongest single tell.'),
      hop(6, 'Ring',    'RING-2024-A417',    'Ring closure check', 'fail', 'closes the cycle',                  'This is the closing edge back to origin.'),
      hop(7, 'Anomaly', 'ISOFOREST',         'Anomaly score',      'warn', 'anomaly=0.65',                      'Elevated anomaly.'),
      hop(8, 'ITC',     'ITC-INV-A417-004',  'ITC decision',       'fail', 'blocked pending SCN',               'Blocked; SCN drafted.')
    ]
  },
  {
    invoice_id: 'INV-B209-001',
    overall_status: 'MATCH',
    audit_summary: 'Values clean, timing clean. Ring membership + rotating vehicle drives the flag.',
    itc_status: 'CONDITIONAL',
    failed_checkpoints: ['ring_membership'],
    hops: [
      hop(1, 'Invoice', 'INV-B209-001',      'Invoice issued',       'ok', 'issued 2024-04-11',            'Filed same day.'),
      hop(2, 'GSTIN',   '07EFGHI5678J5Z9',   'Sender filed',         'ok', 'GSTR-1 filed 2024-04-15',      'No filing gap.'),
      hop(3, 'GSTIN',   '07FGHIJ6789K6Z0',   'Recipient claim',      'ok', 'claim 2024-04-18',             'Normal claim timing.'),
      hop(4, 'Value',   'GSTR-2A/3B',        'Value reconciliation', 'ok', '2A=3B=₹1,47,600',              'Values reconcile.'),
      hop(5, 'Vehicle', 'DL01-BB-5501',      'Vehicle logged',       'warn','rotates with DL01-CC-6612',   'Two rented vehicles alternate across 5 legs.'),
      hop(6, 'Ring',    'RING-2024-B209',    'Ring closure check',   'fail','part of closed cycle',        'Ring closure: hops=5, C=0.88.'),
      hop(7, 'Anomaly', 'ISOFOREST',         'Anomaly score',        'info','anomaly=0.44',                'Modest anomaly.'),
      hop(8, 'ITC',     'ITC-INV-B209-001',  'ITC decision',         'warn','conditional pending review',  'Conditional pending investigator review.')
    ]
  },
  {
    invoice_id: 'INV-B209-002',
    overall_status: 'MISMATCH',
    audit_summary: 'GSTR-3B claim of ₹1,49,000 vs 2A ₹1,48,500 — small but repeat mismatch.',
    itc_status: 'CONDITIONAL',
    failed_checkpoints: ['value_mismatch', 'ring_membership'],
    hops: [
      hop(1, 'Invoice', 'INV-B209-002',      'Invoice issued',       'ok',   'issued 2024-04-12',           'Filed same day.'),
      hop(2, 'GSTIN',   '07FGHIJ6789K6Z0',   'Sender filed',         'ok',   'GSTR-1 filed 2024-04-15',     'No filing gap.'),
      hop(3, 'GSTIN',   '07GHIJK7890L7Z1',   'Recipient claim',      'ok',   'claim 2024-04-19',            'Normal claim timing.'),
      hop(4, 'Value',   'GSTR-2A/3B',        'Value reconciliation', 'fail', '2A: ₹1,48,500 vs 3B: ₹1,49,000','Repeat ₹500 mismatch pattern.'),
      hop(5, 'Vehicle', 'DL01-BB-5501',      'Vehicle logged',       'warn', 'shared with 3 legs',          'Vehicle re-use.'),
      hop(6, 'Ring',    'RING-2024-B209',    'Ring closure check',   'fail', 'part of closed cycle',        'Ring closure.'),
      hop(7, 'Anomaly', 'ISOFOREST',         'Anomaly score',        'warn', 'anomaly=0.53',                'Elevated anomaly.'),
      hop(8, 'ITC',     'ITC-INV-B209-002',  'ITC decision',         'warn', 'conditional pending value fix','ITC conditional.')
    ]
  },
  {
    invoice_id: 'INV-C083-001',
    overall_status: 'DUPLICATE',
    audit_summary: 'Flash 3-day loop with a single vehicle across all legs. Recommended break-edge.',
    itc_status: 'BLOCKED',
    failed_checkpoints: ['temporal_flash', 'vehicle_reuse', 'ring_membership'],
    hops: [
      hop(1, 'Invoice', 'INV-C083-001',      'Invoice issued',       'ok',   'issued 2024-05-02',           'Filed same day.'),
      hop(2, 'GSTIN',   '29JKLMN0123O0Z4',   'Sender filed',         'ok',   'GSTR-1 filed 2024-05-06',     'No filing gap.'),
      hop(3, 'GSTIN',   '29KLMNO1234P1Z5',   'Recipient claim',      'ok',   'claim 2024-05-06',            'Normal claim timing.'),
      hop(4, 'Value',   'GSTR-2A/3B',        'Value reconciliation', 'ok',   '2A=3B=₹4,32,000',             'Values reconcile.'),
      hop(5, 'Vehicle', 'KA05-DD-9902',      'Vehicle logged',       'fail', 'same vehicle on all 3 legs',  'Only one vehicle used across the entire flash cycle.'),
      hop(6, 'Ring',    'RING-2024-C083',    'Ring closure check',   'fail', 'flash cycle, T=0.92',         'Ring closes in 3 days.'),
      hop(7, 'Anomaly', 'ISOFOREST',         'Anomaly score',        'fail', 'anomaly=0.72',                'High anomaly score.'),
      hop(8, 'ITC',     'ITC-INV-C083-001',  'ITC decision',         'fail', 'blocked pending SCN',         'Blocked; SCN drafted.')
    ]
  },
  {
    invoice_id: 'INV-C083-002',
    overall_status: 'DUPLICATE',
    audit_summary: 'Second leg of the flash cycle. Same value pattern (~₹24 L), same vehicle.',
    itc_status: 'BLOCKED',
    failed_checkpoints: ['temporal_flash', 'vehicle_reuse', 'ring_membership'],
    hops: [
      hop(1, 'Invoice', 'INV-C083-002',      'Invoice issued',       'ok',   'issued 2024-05-03',           'Filed same day.'),
      hop(2, 'GSTIN',   '29KLMNO1234P1Z5',   'Sender filed',         'ok',   'GSTR-1 filed 2024-05-06',     'No filing gap.'),
      hop(3, 'GSTIN',   '29LMNOP2345Q2Z6',   'Recipient claim',      'ok',   'claim 2024-05-07',            'Normal claim timing.'),
      hop(4, 'Value',   'GSTR-2A/3B',        'Value reconciliation', 'ok',   '2A=3B=₹4,33,440',             'Values reconcile.'),
      hop(5, 'Vehicle', 'KA05-DD-9902',      'Vehicle logged',       'fail', 'shared across cycle',         'Same vehicle recurs.'),
      hop(6, 'Ring',    'RING-2024-C083',    'Ring closure check',   'fail', 'flash cycle',                 'Ring closure.'),
      hop(7, 'Anomaly', 'ISOFOREST',         'Anomaly score',        'fail', 'anomaly=0.70',                'High anomaly score.'),
      hop(8, 'ITC',     'ITC-INV-C083-002',  'ITC decision',         'fail', 'blocked pending SCN',         'Blocked; SCN drafted.')
    ]
  }
];

// ---- Dashboard ----------------------------------------------------------

export const MOCK_DASHBOARD: DashboardSummary = {
  neo4j: false,
  rings_open: 3,
  vendors_high: 6,
  exposure_total: MOCK_RINGS.reduce((s, r) => s + (r.exposure_inr ?? 0), 0),
  last_detection_at: '2024-05-11T14:22:00Z',
  latency_ms: 87
};

// ---- Graph payload (Cytoscape-shaped) ----------------------------------
// Built from the three real rings so the canvas has a real substrate when
// the backend graph endpoint is offline.

function buildGraphFromRings(rings: ReadonlyArray<Ring>): GraphPayload {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const seenNodes = new Set<string>();
  const seenEdges = new Set<string>();

  const gstinName = (g: string): string => {
    const m = MOCK_GSTINS.find(x => x.id === g);
    return m ? m.name : g;
  };

  for (const ring of rings) {
    // Ring node itself
    const ringId = ring.ring_id;
    if (!seenNodes.has(ringId)) {
      nodes.push({ data: { id: ringId, label: ringId, type: 'ring', ring_id: ringId } });
      seenNodes.add(ringId);
    }

    for (const member of ring.members) {
      if (!seenNodes.has(member)) {
        nodes.push({
          data: {
            id: member,
            label: gstinName(member),
            type: 'gstin',
            gstin_short: member.slice(0, 4) + '…' + member.slice(-3),
            risk: MOCK_VENDORS.find(v => v.gstin === member)?.risk_score ?? 0.3
          }
        });
        seenNodes.add(member);
      }
      const memEdgeId = `${ringId}::mem::${member}`;
      if (!seenEdges.has(memEdgeId)) {
        edges.push({ data: { id: memEdgeId, source: ringId, target: member, kind: 'MEMBER' } });
        seenEdges.add(memEdgeId);
      }
    }

    for (const e of ring.edges) {
      const invId = e.invoice_id;
      if (!seenNodes.has(invId)) {
        nodes.push({ data: { id: invId, label: invId, type: 'invoice' } });
        seenNodes.add(invId);
      }
      const outId = `${e.src}::TO::${invId}`;
      const inId = `${invId}::TO::${e.dst}`;
      if (!seenEdges.has(outId)) {
        edges.push({ data: { id: outId, source: e.src, target: invId, amount: e.amount, date: e.date, invoice_id: invId, kind: 'ISSUED' } });
        seenEdges.add(outId);
      }
      if (!seenEdges.has(inId)) {
        edges.push({ data: { id: inId, source: invId, target: e.dst, amount: e.amount, date: e.date, invoice_id: invId, kind: 'BILLED_TO' } });
        seenEdges.add(inId);
      }

      if (e.vehicle_id) {
        const vid = `VEH::${e.vehicle_id}`;
        if (!seenNodes.has(vid)) {
          nodes.push({ data: { id: vid, label: e.vehicle_id, type: 'vehicle' } });
          seenNodes.add(vid);
        }
        const vinvId = `${vid}::CARRIED::${invId}`;
        if (!seenEdges.has(vinvId)) {
          edges.push({ data: { id: vinvId, source: vid, target: invId, kind: 'CARRIED' } });
          seenEdges.add(vinvId);
        }
      }
    }
  }
  return { nodes, edges };
}

export const MOCK_GRAPH: GraphPayload = buildGraphFromRings([RING_1, RING_2, RING_3]);
