import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { Copy, X } from 'lucide-react';
import { getCase, getRing, postAgentQuery } from '../../lib/api';
import { GraphCanvas } from '../../components/GraphCanvas/GraphCanvas';
import { EvidencePanel } from '../../components/EvidencePanel/EvidencePanel';
import { TimelineScrubber } from '../../components/TimelineScrubber/TimelineScrubber';
import { RelatedVendors } from '../../components/RelatedVendors/RelatedVendors';
import { Button } from '../../components/ui/Button';
import { RiskMeter } from '../../components/ui/Risk';
import { StatusControl } from '../../components/ui/StatusControl';
import { useStore } from '../../lib/store';
import { useShortcuts } from '../../lib/keyboard';
import type {
  AuditHop, AuditTrail, GraphPayload, Ring, Signals, Vendor
} from '../../types/domain';
import type {
  InvestigationCase, MatchEventOut, RingSummary
} from '../../types/case';
import styles from './Investigation.module.css';

type Tab = 'overview' | 'evidence' | 'counterfactual';

interface Props {
  mode: 'entity' | 'ring';
}

const BLOCKING = new Set([
  'MISSING_GSTR1', 'MISSING_GSTR3B', 'MISSING_TAX_PAYMENT',
  'CANCELLED_SUPPLIER', 'DUPLICATE',
]);

// ── Adapters: the canonical Case → the existing component prop shapes ─────
// The Investigation page now has ONE data source (GET /api/cases/{id}); these
// pure adapters reshape it into the Ring / Vendor / GraphPayload / AuditTrail[]
// the (unchanged) components already consume, so the UI renders identically.
const signals = (s: Record<string, number> | undefined): Signals => ({
  C: s?.C ?? 0, V: s?.V ?? 0, T: s?.T ?? 0, R: s?.R ?? 0, N: s?.N ?? 0, H: s?.H ?? 0,
});

function inrShort(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)}L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`;
  return `₹${v.toFixed(0)}`;
}

function bandToSeverity(b?: string | null): 'high' | 'med' | 'low' {
  if (b === 'CRITICAL' || b === 'HIGH') return 'high';
  if (b === 'MED') return 'med';
  return 'low';
}

function toRing(rs: RingSummary | undefined, c: InvestigationCase): Ring | null {
  if (!rs) return null;
  const be = (rs.break_edge ?? null) as Record<string, unknown> | null;
  return {
    ring_id: rs.ring_id,
    members: rs.members,
    invoices: rs.invoices,
    edges: (rs.edges ?? []).map(e => ({
      src: e.src, dst: e.dst, invoice_id: e.invoice_id, date: e.date ?? '',
      amount: e.amount, gst_amount: e.gst_amount,
      vehicle_id: e.vehicle_id ?? null, hsn: e.hsn ?? null, pin_prefix: null,
    })),
    per_edge: [],   // counterfactual sweep isn't persisted; break_edge is the recommendation
    hops: rs.hops,
    date_span_days: rs.date_span_days,
    total_gst: rs.total_gst,
    score: rs.score,
    signals: signals(rs.signals),
    contribution: signals(rs.contribution),
    share: signals(rs.share),
    break_edge: be ? {
      src: String(be.src ?? ''), dst: String(be.dst ?? ''),
      invoice_id: String(be.invoice_id ?? ''),
      score_after: Number(be.score_after ?? 0), score_drop: Number(be.score_drop ?? 0),
    } : null,
    // real UI metadata sourced from the case (previously mock-only)
    scenario: c.entity.scenario ?? undefined,
    exposure_inr: c.exposure.total_inr,
    severity: bandToSeverity(rs.band ?? c.risk.band),
    reason_chips: c.risk.reasons.slice(0, 4).map(r => r.detail || r.name).filter(Boolean),
    xai_confidence: c.risk.score,
  };
}

function toVendor(c: InvestigationCase): Vendor {
  return {
    gstin: c.entity.gstin_id,
    name: c.entity.name ?? c.entity.gstin_id,
    state: c.entity.state_code ?? '',
    pan: c.entity.gstin_id.slice(2, 12),
    incorp_date: '',
    risk_score: c.risk.score,
    anomaly_score: 0,
    rings: c.rings.map(r => r.ring_id),
    exposure_inr: c.exposure.total_inr,
    first_seen: '',
    last_seen: c.latest_activity ?? '',
    reasons: c.risk.reasons.map(r => r.detail || r.name).filter(Boolean),
    sparkline: [],
    severity: bandToSeverity(c.risk.band),
    scenario: c.entity.scenario ?? '',
    entity_type: 'vendor',
  };
}

function toGraph(c: InvestigationCase): GraphPayload | null {
  if (!c.subgraph) return null;
  return {
    nodes: (c.subgraph.nodes ?? []) as GraphPayload['nodes'],
    edges: (c.subgraph.edges ?? []) as GraphPayload['edges'],
  };
}

function toAuditTrails(events: MatchEventOut[]): AuditTrail[] {
  const byInvoice = new Map<string, MatchEventOut[]>();
  for (const e of events) {
    const k = e.invoice_id ?? e.event_id;
    if (!byInvoice.has(k)) byInvoice.set(k, []);
    byInvoice.get(k)!.push(e);
  }
  const trails: AuditTrail[] = [];
  byInvoice.forEach((evs, invoice) => {
    const outcomes = evs.map(e => e.outcome);
    const blocked = outcomes.some(o => BLOCKING.has(o));
    const hops: AuditHop[] = [];
    let h = 1;
    for (const e of evs) {
      const status: AuditHop['status'] =
        BLOCKING.has(e.outcome) ? 'fail' : e.outcome === 'MATCHED' ? 'ok' : 'warn';
      const reasons = e.reasons ?? [];
      if (reasons.length === 0) {
        hops.push({
          hop: h++, node_type: 'MatchEvent', node_id: e.event_id, label: e.outcome,
          ok: status === 'ok', status, detail: e.outcome,
          narrative: `${e.outcome} (${e.severity})${e.role ? ' · ' + e.role : ''}`,
        });
      } else {
        for (const r of reasons) {
          const ev = (r.evidence ?? {}) as Record<string, unknown>;
          hops.push({
            hop: h++, node_type: String(ev.node_type ?? 'MatchEvent'),
            node_id: String(ev.node_id ?? e.event_id), label: e.outcome,
            ok: status === 'ok', status, detail: r.detail || r.name,
            narrative: r.detail || r.name,
          });
        }
      }
    }
    trails.push({
      invoice_id: invoice,
      overall_status: blocked ? 'MISSING'
        : outcomes.some(o => o.includes('MISMATCH')) ? 'MISMATCH'
        : outcomes.some(o => o.includes('DUPLICATE')) ? 'DUPLICATE' : 'OK',
      audit_summary: outcomes.join(', '),
      itc_status: blocked ? 'BLOCKED' : 'ELIGIBLE',
      failed_checkpoints: outcomes.filter(o => o !== 'MATCHED'),
      hops,
    });
  });
  return trails;
}

export function InvestigationPage({ mode }: Props) {
  const params = useParams<{ gstin?: string; ring_id?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const pushToast = useStore(s => s.pushToast);

  const gstinFromUrl = params.gstin ?? null;
  const nodeFromUrl = searchParams.get('node');
  const ringIdFromUrl = params.ring_id ?? searchParams.get('ring');
  const tabFromUrl = (searchParams.get('tab') as Tab | null) ?? 'overview';
  const dateFromUrl = searchParams.get('t');
  const cutFromUrl = searchParams.get('break');

  // ONE data source. The case entity is the gstin on the route, or the `node`
  // param that ring-mode links carry — no client-side entity→ring guessing,
  // no MOCK_RINGS. For a bare /ring/:id deep-link with no ?node= entity, resolve
  // a ring member from the persisted ring (getRing → members[0]); the case is
  // still assembled by getCase, this only supplies the entity id.
  const directGstin = gstinFromUrl ?? nodeFromUrl;
  const ringResolveQ = useQuery({
    queryKey: ['ring-resolve', ringIdFromUrl] as const,
    queryFn: () => (ringIdFromUrl ? getRing(ringIdFromUrl) : Promise.resolve(null)),
    enabled: mode === 'ring' && !directGstin && !!ringIdFromUrl,
    staleTime: 60_000,
  });
  const resolvedGstin =
    (ringResolveQ.data as { data?: { members?: string[] } } | null | undefined)
      ?.data?.members?.[0] ?? null;
  const caseGstin = directGstin ?? resolvedGstin;
  const caseQ = useQuery({
    queryKey: ['case', caseGstin] as const,
    queryFn: () => (caseGstin ? getCase(caseGstin) : Promise.resolve(null)),
    enabled: !!caseGstin,
    staleTime: 30_000,
  });
  const invCase: InvestigationCase | null =
    caseQ.data ? (caseQ.data as { data: InvestigationCase }).data : null;

  useEffect(() => {
    if (caseQ.data && (caseQ.data as { fromMock: boolean }).fromMock) {
      pushToast({ kind: 'warn', title: 'Backend unreachable', body: 'Serving demo fixtures' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseQ.data && (caseQ.data as { fromMock: boolean }).fromMock]);

  // Primary ring = the one named in the URL, else the entity's top-scoring ring.
  const primaryRingSummary = useMemo<RingSummary | undefined>(() => {
    if (!invCase) return undefined;
    if (ringIdFromUrl) {
      const hit = invCase.rings.find(r => r.ring_id === ringIdFromUrl);
      if (hit) return hit;
    }
    return invCase.rings[0];
  }, [invCase, ringIdFromUrl]);

  const ring = useMemo<Ring | null>(
    () => (invCase ? toRing(primaryRingSummary, invCase) : null),
    [invCase, primaryRingSummary]);
  const vendor = useMemo<Vendor | null>(
    () => (invCase ? toVendor(invCase) : null), [invCase]);
  const scopedGraph = useMemo<GraphPayload | null>(
    () => (invCase ? toGraph(invCase) : null), [invCase]);
  const auditTrailsResolved = useMemo<AuditTrail[]>(
    () => (invCase ? toAuditTrails(invCase.reconciliation) : []), [invCase]);

  const focusedInvoiceId = useMemo<string | null>(() => {
    if (!ring) return null;
    if (cutFromUrl) return cutFromUrl;
    if (nodeFromUrl && ring.edges.some(e => e.invoice_id === nodeFromUrl)) return nodeFromUrl;
    return ring.edges[0]?.invoice_id ?? null;
  }, [ring, nodeFromUrl, cutFromUrl]);

  const [cutInvoice, setCutInvoice] = useState<string | null>(cutFromUrl ?? null);
  const [timelineDate, setTimelineDate] = useState<string | null>(dateFromUrl);

  useEffect(() => {
    setCutInvoice((prev) => (prev === cutFromUrl ? prev : (cutFromUrl ?? null)));
  }, [cutFromUrl]);
  useEffect(() => {
    setTimelineDate((prev) => (prev === dateFromUrl ? prev : dateFromUrl));
  }, [dateFromUrl]);

  const setTab = (t: Tab) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', t);
    setSearchParams(next, { replace: true });
  };
  useEffect(() => {
    if (cutInvoice === (cutFromUrl ?? null)) return;
    const next = new URLSearchParams(searchParams);
    if (cutInvoice) next.set('break', cutInvoice);
    else next.delete('break');
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cutInvoice]);
  useEffect(() => {
    if (timelineDate === dateFromUrl) return;
    const next = new URLSearchParams(searchParams);
    if (timelineDate) next.set('t', timelineDate);
    else next.delete('t');
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timelineDate]);

  const cycleRing = (dir: 1 | -1) => {
    if (!invCase || invCase.rings.length === 0) return;
    const rs = invCase.rings;
    const idx = rs.findIndex(r => r.ring_id === primaryRingSummary?.ring_id);
    const nxt = rs[((idx + dir) % rs.length + rs.length) % rs.length];
    if (nxt) {
      const next = new URLSearchParams(searchParams);
      next.set('ring', nxt.ring_id);
      setSearchParams(next, { replace: true });
    }
  };

  useShortcuts({
    '1': () => setTab('overview'),
    '2': () => setTab('evidence'),
    '3': () => setTab('counterfactual'),
    ']': () => cycleRing(1),
    '[': () => cycleRing(-1),
  });

  const [scnPreview, setScnPreview] = useState<string | null>(null);

  const draftSCN = async () => {
    if (!ring) return;
    pushToast({ kind: 'info', title: 'Requesting SCN draft', body: `intent circular_fraud · ${ring.ring_id}` });
    const res = await postAgentQuery({ intent: 'circular_fraud', payload: { ring_id: ring.ring_id, members: ring.members } });
    if (res.fromMock || !res.data.text) {
      pushToast({ kind: 'warn', title: 'Agent intent circular_fraud not available', body: 'Using local template' });
      setScnPreview(localScnTemplate(ring));
    } else {
      setScnPreview(res.data.text);
    }
  };

  const copyScn = () => {
    if (!scnPreview) return;
    navigator.clipboard.writeText(scnPreview).catch(() => {});
    pushToast({ kind: 'ok', title: 'SCN draft copied' });
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.headerId}>
          <span className={styles.kicker}>{mode === 'ring' ? 'Ring investigation' : 'Entity investigation'}</span>
          <div className={styles.titleRow}>
            <h1 className={styles.headerTitle}>{invCase?.entity.name ?? gstinFromUrl ?? 'Investigation'}</h1>
            {invCase?.entity.status === 'CANCELLED' && <span className={styles.cancelledTag}>cancelled</span>}
          </div>
          <div className={styles.idRow}>
            <span className={styles.gstinChip} data-mono>{invCase?.entity.gstin_id ?? caseGstin ?? '—'}</span>
            {ring && <span className={styles.ringChip} data-mono>{ring.ring_id}</span>}
            {invCase && invCase.rings.length > 1 && (
              <span className={styles.ringNav}>
                <button onClick={() => cycleRing(-1)} title="Previous ring ([)">‹</button>
                <span data-mono>{(invCase.rings.findIndex(r => r.ring_id === primaryRingSummary?.ring_id) + 1)}/{invCase.rings.length}</span>
                <button onClick={() => cycleRing(1)} title="Next ring (])">›</button>
              </span>
            )}
          </div>
        </div>

        {invCase && (
          <div className={styles.summaryStrip}>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Composed risk</span>
              <RiskMeter score={invCase.risk.score} band={invCase.risk.band} size="lg" />
            </div>
            <div className={styles.statSep} />
            <div className={styles.stat}>
              <span className={styles.statLabel}>ITC exposure</span>
              <span className={styles.statValue} data-mono>{inrShort(invCase.exposure.total_inr)}</span>
              <span className={styles.statFoot} data-mono>{invCase.exposure.invoice_count} invoices</span>
            </div>
            <div className={styles.statSep} />
            <div className={styles.stat}>
              <span className={styles.statLabel}>Network</span>
              <span className={styles.statValue} data-mono>{ring ? `${ring.members.length}` : invCase.rings.length}</span>
              <span className={styles.statFoot} data-mono>{ring ? 'nodes in ring' : 'rings'}</span>
            </div>
            {ring && <>
              <div className={styles.statSep} />
              <div className={styles.stat}>
                <span className={styles.statLabel}>Window</span>
                <span className={styles.statValue} data-mono>{ring.date_span_days}d</span>
                <span className={styles.statFoot} data-mono>{ring.hops} hops</span>
              </div>
            </>}
          </div>
        )}

        <div className={styles.headerSpacer} />

        <div className={styles.headerActions}>
          {invCase && <StatusControl gstin={invCase.entity.gstin_id} status={invCase.investigation_status} />}
          {ring && <Button variant="primary" size="sm" onClick={draftSCN}>Draft notice</Button>}
        </div>
      </div>

      <div className={styles.left}>
        <div className={styles.canvasSlot}>
          <GraphCanvas
            data={scopedGraph}
            ring={ring}
            timelineDate={timelineDate}
            cutInvoiceId={cutInvoice}
          />
        </div>
        {mode === 'ring' && ring && (
          <div className={styles.timelineSlot}>
            <TimelineScrubber
              ring={ring}
              initialDate={timelineDate}
              onDateChange={setTimelineDate}
            />
          </div>
        )}
        {(ring || caseGstin) && (
          <div className={styles.relatedSlot}>
            <RelatedVendors
              gstin={(ring?.members[0]) ?? caseGstin ?? ''}
              ringMembers={ring?.members}
              k={5}
              compact
            />
          </div>
        )}
      </div>

      <div className={styles.right}>
        <EvidencePanel
          ring={ring}
          vendor={vendor}
          auditTrails={auditTrailsResolved}
          focusedInvoiceId={focusedInvoiceId}
          activeTab={tabFromUrl}
          onTabChange={setTab}
          onCutInvoice={setCutInvoice}
        />
      </div>

      <AnimatePresence>
        {scnPreview !== null && (
          <motion.aside
            key="scn-preview"
            className={styles.scnPreview}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 12 }}
            transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
            aria-label="SCN draft preview"
          >
            <div className={styles.scnHeader}>
              <span>SCN draft — {ring?.ring_id ?? ''}</span>
              <div className={styles.scnActions}>
                <button type="button" onClick={copyScn} title="Copy SCN to clipboard"><Copy size={12} strokeWidth={1.5} /> Copy</button>
                <button type="button" onClick={() => setScnPreview(null)} title="Close"><X size={12} strokeWidth={1.5} /></button>
              </div>
            </div>
            <pre className={styles.scnBody} data-mono>{scnPreview}</pre>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}

function localScnTemplate(ring: Ring): string {
  return [
    `SHOW-CAUSE NOTICE (draft)`,
    ``,
    `Ring: ${ring.ring_id}`,
    `Members: ${ring.members.join(', ')}`,
    `Total invoiced GST: ₹${ring.total_gst.toLocaleString('en-IN')}`,
    `Score: ${ring.score.toFixed(3)}  (C=${ring.signals.C.toFixed(2)} V=${ring.signals.V.toFixed(2)} T=${ring.signals.T.toFixed(2)} R=${ring.signals.R.toFixed(2)} N=${ring.signals.N.toFixed(2)} H=${ring.signals.H.toFixed(2)})`,
    ``,
    `Findings:`,
    ...ring.edges.map((e, i) => `  ${i + 1}. ${e.date}  ${e.invoice_id}  ${e.src} → ${e.dst}  ₹${e.amount.toLocaleString('en-IN')} (GST ₹${e.gst_amount.toLocaleString('en-IN')})${e.vehicle_id ? ' · veh ' + e.vehicle_id : ''}`),
    ``,
    `Recommended break-edge: ${ring.break_edge?.invoice_id ?? 'n/a'} (score after removal: ${ring.break_edge?.score_after.toFixed(3) ?? '—'})`,
    ``,
    `Local template — agent circular_fraud unavailable.`
  ].join('\n');
}
