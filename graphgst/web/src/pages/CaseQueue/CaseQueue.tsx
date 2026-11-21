import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, ArrowRight, Layers } from 'lucide-react';
import { getCaseList, postDetect } from '../../lib/api';
import { RiskMeter } from '../../components/ui/Risk';
import { StatusPill } from '../../components/ui/Status';
import { Button } from '../../components/ui/Button';
import { useStore } from '../../lib/store';
import { useShortcuts } from '../../lib/keyboard';
import type { Band, CaseListItem, InvestigationStatus } from '../../types/case';
import styles from './CaseQueue.module.css';

type SortKey = 'score' | 'exposure' | 'network';

const BAND_FILTER: [string, string][] = [
  ['', 'All'], ['CRITICAL', 'Critical'], ['HIGH', 'High'], ['MED', 'Elevated'], ['LOW', 'Watch'],
];
const STATUS_FILTER: [string, string][] = [
  ['', 'All'], ['open', 'Open'], ['investigating', 'Investigating'],
  ['escalated', 'Escalated'], ['resolved', 'Resolved'], ['dismissed', 'Dismissed'],
];

const BAND_META: Record<Band, { label: string; cls: string }> = {
  CRITICAL: { label: 'Critical', cls: 'crit' },
  HIGH: { label: 'High', cls: 'high' },
  MED: { label: 'Elevated', cls: 'med' },
  LOW: { label: 'Watch', cls: 'low' },
};

// Human labels for the dominant signal / scenario codes.
const CODE_LABEL: Record<string, string> = {
  CIRCULAR_TRADING: 'Circular trading',
  MISSING_GSTR1: 'Missing GSTR-1',
  AMOUNT_MISMATCH: 'Amount mismatch',
  CANCELLED_SUPPLIER: 'Cancelled supplier',
  NORMAL: 'Nominal',
};
function labelFor(code: string): string {
  return CODE_LABEL[code] ?? code.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase());
}
// Classification derives from the actual dominant risk driver, not the
// synthetic generator scenario — so a CRITICAL cancelled entity never reads
// "Nominal". Prefer the event-type in the server's primary_signal; then
// ring involvement; then the scenario as a last resort.
function classify(c: CaseListItem): string {
  const m = (c.primary_signal ?? '').match(/([A-Z][A-Z0-9_]{3,})\s+event/);
  if (m) return labelFor(m[1]);
  if (c.ring_count > 0) return 'Circular trading';
  return labelFor(c.scenario ?? '');
}
function inr(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)}L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`;
  return `₹${v.toFixed(0)}`;
}

export function CaseQueuePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const pushToast = useStore(s => s.pushToast);
  const qc = useQueryClient();

  const band = params.get('band') ?? '';
  const status = params.get('status') ?? '';
  const sort = (params.get('sort') as SortKey | null) ?? 'score';
  const q = params.get('q') ?? '';

  const query = useQuery({
    queryKey: ['caseList'] as const,
    queryFn: () => getCaseList({ limit: 200 }),
    staleTime: 30_000,
  });

  useEffect(() => {
    if (query.data?.fromMock) {
      pushToast({ kind: 'warn', title: 'Backend unreachable', body: 'Serving demo fixtures' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.data?.fromMock]);

  const list = query.data?.data;
  const all: CaseListItem[] = list?.cases ?? [];
  const loading = query.isLoading || (!query.data && query.isFetching);

  const rows = useMemo(() => {
    const filtered = all.filter(c => {
      if (band && c.band !== band) return false;
      if (status && c.investigation_status !== status) return false;
      if (q) {
        const hay = `${c.gstin_id} ${c.name ?? ''} ${c.primary_signal ?? ''} ${c.scenario ?? ''}`.toLowerCase();
        if (!hay.includes(q.toLowerCase())) return false;
      }
      return true;
    });
    filtered.sort((a, b) => {
      if (sort === 'exposure') return b.exposure_inr - a.exposure_inr;
      if (sort === 'network') return b.ring_count - a.ring_count;
      return b.risk_score - a.risk_score;
    });
    return filtered;
  }, [all, band, status, q, sort]);

  const [cursor, setCursor] = useState(0);
  useEffect(() => { if (cursor >= rows.length) setCursor(0); }, [rows, cursor]);

  useShortcuts({
    'j': () => setCursor(c => Math.min(rows.length - 1, c + 1)),
    'k': () => setCursor(c => Math.max(0, c - 1)),
    'enter': () => { const row = rows[cursor]; if (row) openRow(row); },
  });

  function openRow(c: CaseListItem): void {
    if (c.ring_count > 0 && c.ring_ids[0]) navigate(`/ring/${c.ring_ids[0]}?tab=overview&node=${c.gstin_id}`);
    else navigate(`/entity/${c.gstin_id}?tab=overview`);
  }
  function updateParam(k: string, val: string | null): void {
    const next = new URLSearchParams(params);
    if (val == null || val === '') next.delete(k); else next.set(k, val);
    setParams(next, { replace: true });
  }
  const onDetect = async () => {
    pushToast({ kind: 'info', title: 'Detection running', body: 'POST /api/rings/detect' });
    const res = await postDetect();
    qc.invalidateQueries({ queryKey: ['rings'] });
    pushToast({ kind: res.fromMock ? 'warn' : 'ok', title: res.fromMock ? 'Detection fell back to demo' : `Detection returned ${res.data.length} rings`, body: `${res.latency_ms}ms` });
  };

  // Summary readouts. band_counts is the full-DB distribution; exposure &
  // networks are summed over the loaded (top-ranked) cases and labelled so.
  const bandCounts = list?.band_counts ?? {};
  const totalScored = list?.materialization?.n_scored ?? all.length;
  const totalExposure = all.reduce((s, c) => s + c.exposure_inr, 0);
  const networks = new Set(all.flatMap(c => c.ring_ids)).size;
  const stale = list?.materialization?.stale ?? false;
  const scoredAt = list?.materialization?.materialized_at;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.headText}>
          <div className={styles.eyebrow}>Investigation queue</div>
          <h1 className={styles.title}>Cases</h1>
        </div>
        <div className={styles.headMeta}>
          <span className={styles.scored} data-mono title="Risk last materialized">
            {stale ? <span className={styles.staleTag}>stale</span> : <span className={styles.freshDot} />}
            scored {scoredAt ? new Date(scoredAt).toISOString().slice(0, 16).replace('T', ' ') : '—'}
          </span>
          <Button variant="primary" onClick={onDetect}><Play size={13} strokeWidth={2} /> Run detection</Button>
        </div>
      </header>

      {/* Instrument readout strip — hairline-separated, not floating cards */}
      <section className={styles.readout} aria-label="Portfolio summary">
        <div className={styles.roItem}>
          <div className={styles.roLabel}>Entities scored</div>
          <div className={styles.roValue} data-mono>{totalScored.toLocaleString('en-IN')}</div>
        </div>
        <div className={styles.roDivider} />
        <div className={`${styles.roItem} ${styles.roWide}`}>
          <div className={styles.roLabel}>Risk distribution</div>
          <BandBar counts={bandCounts} active={band} onPick={(b) => updateParam('band', band === b ? '' : b)} />
        </div>
        <div className={styles.roDivider} />
        <div className={styles.roItem}>
          <div className={styles.roLabel}>Exposure under review</div>
          <div className={styles.roValue} data-mono>{inr(totalExposure)}</div>
          <div className={styles.roFoot}>top {all.length} ranked</div>
        </div>
        <div className={styles.roDivider} />
        <div className={styles.roItem}>
          <div className={styles.roLabel}>Ring networks</div>
          <div className={styles.roValue} data-mono>{networks}</div>
          <div className={styles.roFoot}>distinct</div>
        </div>
      </section>

      {/* Filter bar */}
      <div className={styles.filters}>
        <Segmented label="Band" value={band} onChange={(v) => updateParam('band', v)} options={BAND_FILTER} />
        <Segmented label="Status" value={status} onChange={(v) => updateParam('status', v)} options={STATUS_FILTER} />
        <div className={styles.filterSpacer} />
        <span className={styles.resultCount} data-mono>{rows.length} of {all.length}</span>
        <Segmented label="Sort" value={sort} onChange={(v) => updateParam('sort', v || 'score')} options={[['score', 'Risk'], ['exposure', 'Exposure'], ['network', 'Network']]} />
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.colRank}>#</th>
              <th className={styles.colRisk}>Risk</th>
              <th className={styles.colEntity}>Entity</th>
              <th className={styles.colClass}>Classification</th>
              <th className={styles.colSignal}>Primary signal</th>
              <th className={styles.colNum}>Exposure</th>
              <th className={styles.colNet}>Network</th>
              <th className={styles.colStatus}>Status</th>
              <th className={styles.colGo} />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 10 }).map((_, i) => <SkeletonRow key={i} />)
            ) : rows.length === 0 ? (
              <tr><td colSpan={9}>
                <div className={styles.empty}>
                  <Layers size={22} strokeWidth={1.5} />
                  <div className={styles.emptyTitle}>No cases match these filters</div>
                  <button className={styles.emptyBtn} onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</button>
                </div>
              </td></tr>
            ) : rows.map((c, i) => (
              <tr
                key={c.gstin_id}
                className={i === cursor ? styles.selected : ''}
                onClick={() => setCursor(i)}
                onDoubleClick={() => openRow(c)}
              >
                <td className={styles.colRank}><span className={styles.rank} data-mono>{i + 1}</span></td>
                <td className={styles.colRisk}><RiskMeter score={c.risk_score} band={c.band} size="sm" /></td>
                <td className={styles.colEntity}>
                  <div className={styles.entityTop}>
                    <span className={styles.entityName}>{c.name || c.gstin_id}</span>
                    {c.status === 'CANCELLED' && <span className={styles.cancelled}>cancelled</span>}
                  </div>
                  <div className={styles.entityMeta}>
                    <span className={styles.gstin} data-mono>{c.gstin_id}</span>
                  </div>
                </td>
                <td className={styles.colClass}>
                  <span className={`${styles.classTag} ${styles[`sc_${c.band}`]}`}>{classify(c)}</span>
                </td>
                <td className={styles.colSignal}>
                  <span className={styles.signal} title={c.primary_signal ?? c.top_reasons[0] ?? ''}>
                    {c.primary_signal || c.top_reasons[0] || '—'}
                  </span>
                </td>
                <td className={styles.colNum}>
                  <span className={styles.exp} data-mono>{c.exposure_inr > 0 ? inr(c.exposure_inr) : '—'}</span>
                </td>
                <td className={styles.colNet}>
                  {c.ring_count > 0
                    ? <span className={styles.net} data-mono><Layers size={11} strokeWidth={2} />{c.ring_count}</span>
                    : <span className={styles.netNone}>—</span>}
                </td>
                <td className={styles.colStatus}><StatusPill status={c.investigation_status as InvestigationStatus} size="sm" /></td>
                <td className={styles.colGo}>
                  <button className={styles.go} onClick={(e) => { e.stopPropagation(); openRow(c); }} aria-label={`Open ${c.name}`}>
                    <ArrowRight size={14} strokeWidth={2} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BandBar({ counts, active, onPick }: {
  counts: Record<string, number>; active: string; onPick: (b: string) => void;
}) {
  const order: Band[] = ['CRITICAL', 'HIGH', 'MED', 'LOW'];
  return (
    <div className={styles.bandBar}>
      <div className={styles.bandTrack}>
        {order.map(b => {
          const n = counts[b] ?? 0;
          if (n === 0) return null;
          const dim = active && active !== b;
          return (
            <button
              key={b}
              className={`${styles.bandSeg} ${styles[`bs_${b}`]} ${dim ? styles.bandDim : ''} ${active === b ? styles.bandActive : ''}`}
              style={{ flexGrow: n }}
              onClick={() => onPick(b)}
              title={`${BAND_META[b].label}: ${n}`}
            />
          );
        })}
      </div>
      <div className={styles.bandLegend}>
        {order.map(b => (
          <button key={b} className={`${styles.legendItem} ${styles[`bs_${b}`]} ${active === b ? styles.legendActive : ''}`} onClick={() => onPick(b)}>
            <span className={styles.legendDot} />
            <span className={styles.legendLabel}>{BAND_META[b].label}</span>
            <span className={styles.legendNum} data-mono>{counts[b] ?? 0}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function SkeletonRow() {
  return (
    <tr className={styles.skelRow}>
      <td className={styles.colRank}><span className={styles.skel} style={{ width: 14 }} /></td>
      <td className={styles.colRisk}><span className={styles.skel} style={{ width: 46 }} /></td>
      <td className={styles.colEntity}><span className={styles.skel} style={{ width: 150 }} /><span className={styles.skel} style={{ width: 100, marginTop: 5 }} /></td>
      <td className={styles.colClass}><span className={styles.skel} style={{ width: 88 }} /></td>
      <td className={styles.colSignal}><span className={styles.skel} style={{ width: '80%' }} /></td>
      <td className={styles.colNum}><span className={styles.skel} style={{ width: 54 }} /></td>
      <td className={styles.colNet}><span className={styles.skel} style={{ width: 24 }} /></td>
      <td className={styles.colStatus}><span className={styles.skel} style={{ width: 64 }} /></td>
      <td className={styles.colGo} />
    </tr>
  );
}

function Segmented({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: [string, string][];
}) {
  return (
    <div className={styles.seg}>
      <span className={styles.segLabel}>{label}</span>
      <div className={styles.segTrack}>
        {options.map(([val, lbl]) => (
          <button
            key={val}
            className={`${styles.segBtn} ${value === val ? styles.segActive : ''}`}
            onClick={() => onChange(val)}
          >{lbl}</button>
        ))}
      </div>
    </div>
  );
}
