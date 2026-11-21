import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Clipboard, ExternalLink } from 'lucide-react';
import type { AuditTrail, Ring, SignalKey, Vendor } from '../../types/domain';
import { Pill } from '../ui/Pill';
import { Button } from '../ui/Button';
import { SignalGauge } from './SignalGauge';
import { ReasonChip } from './ReasonChip';
import { BreakSimulator } from '../BreakSimulator/BreakSimulator';
import { useStore } from '../../lib/store';
import styles from './EvidencePanel.module.css';

type Tab = 'overview' | 'evidence' | 'counterfactual';

interface Props {
  ring: Ring | null;
  vendor?: Vendor | null;
  auditTrails: AuditTrail[];
  focusedInvoiceId?: string | null;
  activeTab?: Tab;
  onTabChange?: (t: Tab) => void;
  onCutInvoice?: (invoiceId: string | null) => void;
  onSignalFilter?: (k: SignalKey | null) => void;
  onCitedNode?: (id: string) => void;
}

export function EvidencePanel({ ring, vendor, auditTrails, focusedInvoiceId, activeTab: propTab, onTabChange, onCutInvoice, onSignalFilter, onCitedNode }: Props) {
  const [localTab, setLocalTab] = useState<Tab>('overview');
  const tab = propTab ?? localTab;
  const setTab = (t: Tab) => { setLocalTab(t); onTabChange?.(t); };
  const [activeSignal, setActiveSignal] = useState<SignalKey | null>(null);
  const pushToast = useStore(s => s.pushToast);

  const focusedAudit = useMemo<AuditTrail | null>(() => {
    if (focusedInvoiceId) {
      const hit = auditTrails.find(a => a.invoice_id === focusedInvoiceId);
      if (hit) return hit;
    }
    return auditTrails[0] ?? null;
  }, [focusedInvoiceId, auditTrails]);

  const scoreLabel = ring ? ring.score.toFixed(3) : vendor ? vendor.risk_score.toFixed(3) : '—';
  // Amber "urgent" dot only when the score crosses the documented threshold.
  const scoreValue = ring ? ring.score : vendor ? vendor.risk_score : 0;
  const scoreUrgent = scoreValue >= 0.75;
  const verdict = ring
    ? `${ring.members.length} members · ${ring.hops ?? ring.edges.length} hops · closed within ${ring.date_span_days} days`
    : vendor
      ? `${vendor.entity_type.toUpperCase()} · ${vendor.state} · exposure ₹${vendor.exposure_inr.toLocaleString('en-IN')}`
      : 'Select an entity or ring';

  return (
    <div className={styles.panel}>
      <div className={styles.tabs}>
        <button className={`${styles.tab} ${tab === 'overview'       ? styles.active : ''}`} onClick={() => setTab('overview')}>Overview <span style={{opacity:0.4, marginLeft:6}}>1</span></button>
        <button className={`${styles.tab} ${tab === 'evidence'       ? styles.active : ''}`} onClick={() => setTab('evidence')}>Evidence <span style={{opacity:0.4, marginLeft:6}}>2</span></button>
        <button className={`${styles.tab} ${tab === 'counterfactual' ? styles.active : ''}`} onClick={() => setTab('counterfactual')}>Counterfactual <span style={{opacity:0.4, marginLeft:6}}>3</span></button>
      </div>

      <div className={styles.content}>
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
          >
            {tab === 'overview' && (
              <div>
                <div className={styles.headerRow}>
                  <span className={styles.title} data-mono>{ring ? ring.ring_id : vendor?.gstin ?? '—'}</span>
                  <span className={styles.subtitle}>{ring ? 'RING' : vendor ? 'ENTITY' : ''}</span>
                  {ring?.status && (
                    <Pill tone={ring.status === 'open' ? 'bad' : ring.status === 'reviewing' ? 'warn' : 'ok'} dot>
                      {ring.status}
                    </Pill>
                  )}
                  {vendor?.severity && (
                    <Pill tone={vendor.severity === 'high' ? 'bad' : vendor.severity === 'med' ? 'warn' : 'info'} dot>
                      {vendor.severity}
                    </Pill>
                  )}
                </div>

                <div className={styles.scoreRow}>
                  <span className={styles.score}>
                    {scoreUrgent && <span className={styles.scoreUrgentDot} aria-hidden />}
                    <span>{scoreLabel}</span>
                  </span>
                  <span className={styles.verdict}>{verdict}</span>
                </div>

                {ring && (
                  <>
                    <div className={styles.section}>
                      <div className={styles.sectionHeader}><span>6-Signal Explainer</span><span>{ring.xai_confidence != null ? `xai_confidence ${ring.xai_confidence.toFixed(2)}` : ''}</span></div>
                      <div className={styles.gaugeRow}>
                        {(() => {
                          const keys: SignalKey[] = ['C','V','T','R','N','H'];
                          const maxKey = keys.reduce((best, k) => (ring.signals[k] > ring.signals[best] ? k : best), keys[0]);
                          return keys.map(k => (
                            <SignalGauge
                              key={k}
                              k={k}
                              value={ring.signals[k]}
                              active={activeSignal === k}
                              isMax={k === maxKey}
                              onClick={() => { const nk = activeSignal === k ? null : k; setActiveSignal(nk); onSignalFilter?.(nk); }}
                            />
                          ));
                        })()}
                      </div>
                    </div>

                    <div className={styles.section}>
                      <div className={styles.sectionHeader}><span>Reason Chips</span><span>click to highlight</span></div>
                      <div className={styles.chips}>
                        {(ring.reason_chips ?? []).map(r => (
                          <ReasonChip key={r} label={r} onClick={() => pushToast({ kind: 'info', title: 'Subgraph highlighted', body: r })} />
                        ))}
                      </div>
                    </div>

                    <div className={styles.section}>
                      <div className={styles.sectionHeader}><span>Quick Facts</span></div>
                      <dl className={styles.facts}>
                        <dt>Members</dt><dd data-mono>{ring.members.length}</dd>
                        <dt>Edges</dt><dd data-mono>{ring.edges.length}</dd>
                        <dt>GST Total</dt><dd data-mono>₹{ring.total_gst.toLocaleString('en-IN')}</dd>
                        <dt>Exposure</dt><dd data-mono>₹{(ring.exposure_inr ?? 0).toLocaleString('en-IN')}</dd>
                        <dt>Span</dt><dd data-mono>{ring.date_span_days} d</dd>
                        <dt>Scenario</dt><dd>{ring.scenario ?? '—'}</dd>
                        <dt>First Seen</dt><dd data-mono>{ring.first_seen ?? '—'}</dd>
                        <dt>Assignee</dt><dd>{ring.assignee ?? '—'}</dd>
                      </dl>
                    </div>
                  </>
                )}

                {vendor && !ring && (
                  <>
                    <div className={styles.section}>
                      <div className={styles.sectionHeader}><span>Reasons</span></div>
                      <div className={styles.chips}>
                        {vendor.reasons.map(r => <ReasonChip key={r} label={r} />)}
                      </div>
                    </div>
                    <div className={styles.section}>
                      <div className={styles.sectionHeader}><span>Quick Facts</span></div>
                      <dl className={styles.facts}>
                        <dt>GSTIN</dt><dd data-mono>{vendor.gstin}</dd>
                        <dt>Name</dt><dd>{vendor.name}</dd>
                        <dt>State</dt><dd>{vendor.state}</dd>
                        <dt>PAN</dt><dd data-mono>{vendor.pan}</dd>
                        <dt>Incorp</dt><dd data-mono>{vendor.incorp_date}</dd>
                        <dt>Rings</dt><dd data-mono>{vendor.rings.length ? vendor.rings.join(', ') : '—'}</dd>
                        <dt>Anomaly</dt><dd data-mono>{vendor.anomaly_score.toFixed(3)}</dd>
                        <dt>Exposure</dt><dd data-mono>₹{vendor.exposure_inr.toLocaleString('en-IN')}</dd>
                      </dl>
                    </div>
                  </>
                )}
              </div>
            )}

            {tab === 'evidence' && (
              <div>
                <div className={styles.rowGroup}>
                  <div className={styles.rowGroupHeader}><span>Audit Trail — {focusedAudit?.invoice_id ?? '—'}</span><span>{focusedAudit?.itc_status ?? ''}</span></div>
                  <div className={styles.hopList}>
                    {(focusedAudit?.hops ?? []).map(h => (
                      <div key={h.hop} className={styles.hop}>
                        <div className={`${styles.n} ${styles[h.status]}`}>{h.hop}</div>
                        <div className={styles.lbl}>{h.label} <small>{h.node_type} · {h.node_id}</small></div>
                        <div className={styles.detail}>{h.detail}</div>
                        <div className={styles.narrative}>{h.narrative}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {ring && (
                  <>
                    <div className={styles.rowGroup}>
                      <div className={styles.rowGroupHeader}><span>Per-Edge Reconciliation</span><span>{ring.edges.length} rows</span></div>
                      {ring.edges.map((e, i) => (
                        <div key={i} className={styles.evRow}>
                          <div className={styles.primary}>
                            <span data-mono>{e.invoice_id}</span> · <span data-mono>{e.src.slice(0,6)}→{e.dst.slice(0,6)}</span>
                            <br />
                            <small>₹{e.amount.toLocaleString('en-IN')} · GST ₹{e.gst_amount.toLocaleString('en-IN')} · {e.date}{e.vehicle_id ? ' · veh ' + e.vehicle_id : ''}</small>
                          </div>
                          <button className={styles.cite} type="button" onClick={() => { navigator.clipboard.writeText(`${location.origin}/ring/${ring.ring_id}?node=${e.invoice_id}`).catch(() => {}); pushToast({ kind: 'ok', title: 'Cite link copied', body: e.invoice_id }); onCitedNode?.(e.invoice_id); }}>
                            <Clipboard size={11} strokeWidth={1.5} /> cite
                          </button>
                        </div>
                      ))}
                    </div>

                    <div className={styles.rowGroup}>
                      <div className={styles.rowGroupHeader}><span>Shared Assets</span><span>vehicle · PIN · HSN</span></div>
                      {sharedAssets(ring).map(a => (
                        <div key={a.key} className={styles.evRow}>
                          <div className={styles.primary}>{a.label} <small>{a.detail}</small></div>
                          <button className={styles.cite} type="button" onClick={() => { pushToast({ kind: 'info', title: 'Highlighted in graph', body: a.label }); }}>
                            <ExternalLink size={11} strokeWidth={1.5} /> show
                          </button>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {tab === 'counterfactual' && (
              <div>
                {ring ? (
                  <BreakSimulator ring={ring} onPreview={onCutInvoice} />
                ) : (
                  <div style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-micro)' }}>
                    Select a ring to run the counterfactual.
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {ring && (
        <div style={{
          borderTop: '1px solid var(--border-solid)',
          padding: '8px 12px',
          display: 'flex', gap: 8, alignItems: 'center'
        }}>
          <Button variant="ghost" size="sm" onClick={() => setTab('counterfactual')}>Break</Button>
          <Button variant="ghost" size="sm" onClick={() => setTab('evidence')}>Cite</Button>
          <Button variant="ghost" size="sm">Assign</Button>
          <div style={{ flex: 1 }} />
          <Button variant="primary" size="sm" onClick={() => pushToast({ kind: 'info', title: 'Draft SCN', body: 'Agent circular_fraud requested' })}>Draft SCN</Button>
        </div>
      )}
    </div>
  );
}

function sharedAssets(ring: Ring): { key: string; label: string; detail: string; }[] {
  const vehicles = new Map<string, number>();
  const hsns = new Map<string, number>();
  const pins = new Map<string, number>();
  for (const e of ring.edges) {
    if (e.vehicle_id) vehicles.set(e.vehicle_id, (vehicles.get(e.vehicle_id) ?? 0) + 1);
    if (e.hsn)         hsns.set(e.hsn, (hsns.get(e.hsn) ?? 0) + 1);
    if (e.pin_prefix)  pins.set(e.pin_prefix, (pins.get(e.pin_prefix) ?? 0) + 1);
  }
  const out: { key: string; label: string; detail: string; }[] = [];
  for (const [v, n] of vehicles) if (n >= 2) out.push({ key: 'veh-' + v, label: 'Vehicle re-use', detail: `${v} × ${n} legs` });
  for (const [h, n] of hsns)     if (n >= 2) out.push({ key: 'hsn-' + h, label: 'HSN concentration', detail: `${h} × ${n} legs` });
  for (const [p, n] of pins)     if (n >= 2) out.push({ key: 'pin-' + p, label: 'PIN cluster', detail: `${p} × ${n} legs` });
  if (out.length === 0) out.push({ key: 'none', label: 'No shared assets', detail: 'clean at this level' });
  return out;
}
