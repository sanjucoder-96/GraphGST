import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { Copy, X } from 'lucide-react';
import { getAuditTrail, getGraphFull, getRing, getVendorRisk, postAgentQuery } from '../../lib/api';
import { GraphCanvas } from '../../components/GraphCanvas/GraphCanvas';
import { EvidencePanel } from '../../components/EvidencePanel/EvidencePanel';
import { TimelineScrubber } from '../../components/TimelineScrubber/TimelineScrubber';
import { Pill } from '../../components/ui/Pill';
import { Button } from '../../components/ui/Button';
import { MOCK_AUDIT_TRAILS, MOCK_RINGS } from '../../lib/mocks';
import { useStore } from '../../lib/store';
import { useShortcuts } from '../../lib/keyboard';
import type { AuditTrail, GraphPayload, Ring } from '../../types/domain';
import styles from './Investigation.module.css';

type Tab = 'overview' | 'evidence' | 'counterfactual';

interface Props {
  mode: 'entity' | 'ring';
}

export function InvestigationPage({ mode }: Props) {
  const params = useParams<{ gstin?: string; ring_id?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const pushToast = useStore(s => s.pushToast);

  const ringIdFromUrl = params.ring_id ?? null;
  const gstinFromUrl = params.gstin ?? null;
  const nodeFromUrl = searchParams.get('node');
  const tabFromUrl = (searchParams.get('tab') as Tab | null) ?? 'overview';
  const dateFromUrl = searchParams.get('t');
  const cutFromUrl = searchParams.get('break');

  // Resolve which ring to fetch. On entity route, pick the first ring that
  // includes the GSTIN as a demo affordance.
  const guessRingId = useMemo(() => {
    if (mode === 'ring') return ringIdFromUrl;
    if (mode === 'entity' && gstinFromUrl) {
      const hit = MOCK_RINGS.find(r => r.members.includes(gstinFromUrl));
      return hit?.ring_id ?? MOCK_RINGS[0]?.ring_id ?? null;
    }
    return null;
  }, [mode, ringIdFromUrl, gstinFromUrl]);

  const graphQ = useQuery({ queryKey: ['graph', 'full'] as const, queryFn: getGraphFull, staleTime: 30_000 });
  const vendorsQ = useQuery({ queryKey: ['vendors', 'risk'] as const, queryFn: getVendorRisk, staleTime: 30_000 });
  const ringQ = useQuery({
    queryKey: ['rings', 'detail', guessRingId] as const,
    queryFn: () => guessRingId ? getRing(guessRingId) : Promise.resolve(null),
    enabled: !!guessRingId,
    staleTime: 60_000
  });

  const ring: Ring | null = ringQ.data ? (ringQ.data as { data: Ring }).data : null;
  const vendor = vendorsQ.data?.data.find(v => v.gstin === (gstinFromUrl ?? nodeFromUrl)) ?? null;

  const focusedInvoiceId = useMemo<string | null>(() => {
    if (!ring) return null;
    if (cutFromUrl) return cutFromUrl;
    if (nodeFromUrl && ring.edges.some(e => e.invoice_id === nodeFromUrl)) return nodeFromUrl;
    return ring.edges[0]?.invoice_id ?? null;
  }, [ring, nodeFromUrl, cutFromUrl]);

  // Fetch audit trails for the ring's invoices (using single query with Promise.all)
  const auditTrailsQ = useQuery<AuditTrail[]>({
    queryKey: ['audit', 'ring', ring?.ring_id ?? 'none'] as const,
    queryFn: async () => {
      if (!ring) return [];
      const results = await Promise.all(ring.edges.map(e => getAuditTrail(e.invoice_id)));
      return results.map(r => r.data);
    },
    enabled: !!ring,
    staleTime: 60_000
  });
  const auditTrailsResolved: AuditTrail[] = auditTrailsQ.data ?? (ring ? MOCK_AUDIT_TRAILS.filter(a => ring.edges.some(e => e.invoice_id === a.invoice_id)) : []);

  // Scoped graph — either everything, or filtered to the ring for a cleaner view
  const scopedGraph: GraphPayload | null = useMemo(() => {
    const g = graphQ.data?.data;
    if (!g) return null;
    if (!ring) return g;
    const keep = new Set<string>([ring.ring_id, ...ring.members, ...ring.edges.map(e => e.invoice_id)]);
    for (const e of ring.edges) if (e.vehicle_id) keep.add('VEH::' + e.vehicle_id);
    const nodes = g.nodes.filter(n => keep.has(n.data.id));
    const edges = g.edges.filter(e => keep.has(e.data.source) && keep.has(e.data.target));
    return { nodes, edges };
  }, [graphQ.data, ring]);

  const [cutInvoice, setCutInvoice] = useState<string | null>(cutFromUrl ?? null);
  const [timelineDate, setTimelineDate] = useState<string | null>(dateFromUrl);

  // URL → state sync. Back/forward navigation, deep-links pasted while the
  // page is already mounted, and other route-driven updates hydrate the
  // graph and evidence panel from the current searchParams.
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

  useShortcuts({
    '1': () => setTab('overview'),
    '2': () => setTab('evidence'),
    '3': () => setTab('counterfactual'),
    ']': () => {
      const idx = MOCK_RINGS.findIndex(r => r.ring_id === ring?.ring_id);
      const nxt = MOCK_RINGS[(idx + 1) % MOCK_RINGS.length];
      if (nxt) navigate(`/ring/${nxt.ring_id}`);
    },
    '[': () => {
      const idx = MOCK_RINGS.findIndex(r => r.ring_id === ring?.ring_id);
      const prv = MOCK_RINGS[(idx - 1 + MOCK_RINGS.length) % MOCK_RINGS.length];
      if (prv) navigate(`/ring/${prv.ring_id}`);
    }
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
        <span className={styles.title}>
          {ring ? ring.ring_id : gstinFromUrl ?? 'Investigation'}
        </span>
        <span className={styles.subtitle}>{mode === 'ring' ? 'Ring investigation' : 'Entity investigation'}</span>
        {ring && (
          <>
            <Pill tone="neutral"><span data-mono>score {ring.score.toFixed(3)}</span></Pill>
            <Pill tone="neutral"><span data-mono>{ring.members.length} members</span></Pill>
            <Pill tone="neutral"><span data-mono>{ring.date_span_days}d span</span></Pill>
          </>
        )}
        <div style={{ flex: 1 }} />
        {ring && <Button variant="primary" size="sm" onClick={draftSCN}>Draft SCN</Button>}
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
