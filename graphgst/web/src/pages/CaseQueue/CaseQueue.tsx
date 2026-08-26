import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, ArrowRight, TrendingUp, ShieldAlert, Wallet, Search } from 'lucide-react';
import { getCases, postDetect } from '../../lib/api';
import { RiskSparkline } from '../../components/RiskSparkline/RiskSparkline';
import { Button } from '../../components/ui/Button';
import { useStore } from '../../lib/store';
import { useShortcuts } from '../../lib/keyboard';
import type { Vendor } from '../../types/domain';
import styles from './CaseQueue.module.css';

type SortKey = 'score' | 'exposure' | 'age';

const SEV: Record<string, { label: string; cls: string }> = {
  high: { label: 'Critical',    cls: 'crit' },
  med:  { label: 'Elevated',    cls: 'elev' },
  low:  { label: 'Watch',       cls: 'watch' },
};

function riskClass(score: number): string {
  if (score >= 0.75) return 'crit';
  if (score >= 0.55) return 'high';
  if (score >= 0.30) return 'med';
  return 'low';
}

export function CaseQueuePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const pushToast = useStore(s => s.pushToast);
  const qc = useQueryClient();

  const severity = params.get('severity') ?? '';
  const type = params.get('type') ?? '';
  const scenario = params.get('scenario') ?? '';
  const sort = (params.get('sort') as SortKey | null) ?? 'score';
  const q = params.get('q') ?? '';

  const vendors = useQuery({ queryKey: ['cases', 'risk'] as const, queryFn: getCases, staleTime: 30_000 });

  useEffect(() => {
    if (vendors.data?.fromMock) {
      pushToast({ kind: 'warn', title: 'Backend unreachable', body: 'Serving demo fixtures' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vendors.data?.fromMock]);

  const all = vendors.data?.data ?? [];
  const rows = useMemo(() => {
    const filtered = all.filter(v => {
      if (severity && v.severity !== severity) return false;
      if (type && v.entity_type !== type) return false;
      if (scenario && v.scenario !== scenario) return false;
      if (q) {
        const s = (v.gstin + ' ' + v.name + ' ' + v.reasons.join(' ')).toLowerCase();
        if (!s.includes(q.toLowerCase())) return false;
      }
      return true;
    });
    filtered.sort((a, b) => {
      if (sort === 'exposure') return b.exposure_inr - a.exposure_inr;
      if (sort === 'age') return new Date(b.first_seen).getTime() - new Date(a.first_seen).getTime();
      return b.risk_score - a.risk_score;
    });
    return filtered;
  }, [all, severity, type, scenario, q, sort]);

  const [cursor, setCursor] = useState(0);
  useEffect(() => { if (cursor >= rows.length) setCursor(0); }, [rows, cursor]);

  useShortcuts({
    'j': () => setCursor(c => Math.min(rows.length - 1, c + 1)),
    'k': () => setCursor(c => Math.max(0, c - 1)),
    'enter': () => { const row = rows[cursor]; if (row) openRow(row); }
  });

  function openRow(v: Vendor): void {
    if (v.rings.length > 0) navigate(`/ring/${v.rings[0]}?tab=overview&node=${v.gstin}`);
    else navigate(`/entity/${v.gstin}?tab=overview`);
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
    qc.invalidateQueries({ queryKey: ['vendors'] });
    pushToast({ kind: res.fromMock ? 'warn' : 'ok', title: res.fromMock ? 'Detection fell back to demo' : `Detection returned ${res.data.length} rings`, body: `${res.latency_ms}ms` });
  };
  const ageDays = (iso: string) => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000));

  const totalExposure = all.reduce((s, r) => s + r.exposure_inr, 0);
  const critCount = all.filter(r => r.severity === 'high').length;
  const ringCount = new Set(all.flatMap(r => r.rings)).size;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.head}>
        <div className={styles.headText}>
          <h1 className={styles.title}>Cases</h1>
          <p className={styles.subtitle}>Entities ranked by composed risk across reconciliation, network, and temporal signals.</p>
        </div>
        <Button variant="primary" onClick={onDetect}><Play size={13} strokeWidth={2} /> Run detection</Button>
      </div>

      {/* Metric cards */}
      <div className={styles.metrics}>
        <MetricCard icon={<TrendingUp size={15} strokeWidth={1.75} />} label="Under review" value={all.length.toString()} accent="brand" foot={`${rows.length} match filters`} />
        <MetricCard icon={<ShieldAlert size={15} strokeWidth={1.75} />} label="Critical" value={critCount.toString()} accent="bad" foot="risk ≥ 0.75" />
        <MetricCard icon={<Wallet size={15} strokeWidth={1.75} />} label="ITC exposure" value={`₹${(totalExposure/100000).toFixed(1)}L`} accent="warn" foot={totalExposure.toLocaleString('en-IN')} mono />
        <MetricCard icon={<Search size={15} strokeWidth={1.75} />} label="Rings" value={ringCount.toString()} accent="cyan" foot="detected networks" />
      </div>

      {/* Filter bar */}
      <div className={styles.filters}>
        <Segmented label="Severity" value={severity} onChange={(v) => updateParam('severity', v)} options={[['','All'],['high','Critical'],['med','Elevated'],['low','Watch']]} />
        <Segmented label="Type" value={type} onChange={(v) => updateParam('type', v)} options={[['','All'],['vendor','Vendor'],['buyer','Buyer'],['transporter','Transporter']]} />
        <div className={styles.filterSpacer} />
        <Segmented label="Sort" value={sort} onChange={(v) => updateParam('sort', v || 'score')} options={[['score','Risk'],['exposure','Exposure'],['age','Age']]} />
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.colRisk}>Risk</th>
              <th className={styles.colEntity}>Entity</th>
              <th className={styles.colEvidence}>Primary signal</th>
              <th className={styles.colReasons}>Reasons</th>
              <th className={styles.colExp}>Exposure</th>
              <th className={styles.colAge}>Age</th>
              <th className={styles.colSev}>Status</th>
              <th className={styles.colGo} />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={8}>
                <div className={styles.empty}>
                  <Search size={22} strokeWidth={1.5} />
                  <div className={styles.emptyTitle}>No cases match these filters</div>
                  <button className={styles.emptyBtn} onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</button>
                </div>
              </td></tr>
            ) : rows.map((v, i) => (
              <tr
                key={v.gstin}
                className={i === cursor ? styles.selected : ''}
                onClick={() => setCursor(i)}
                onDoubleClick={() => openRow(v)}
              >
                <td className={styles.colRisk}>
                  <div className={styles.riskCell}>
                    <span className={`${styles.riskScore} ${styles[riskClass(v.risk_score)]}`}>{v.risk_score.toFixed(3)}</span>
                    <span className={styles.spark}><RiskSparkline data={v.sparkline} /></span>
                  </div>
                </td>
                <td className={styles.colEntity}>
                  <div className={styles.entityName}>{v.name}</div>
                  <div className={styles.entityMeta}>
                    <span className={styles.gstin} data-mono>{v.gstin}</span>
                    <span className={styles.state}>{v.state}</span>
                  </div>
                </td>
                <td className={styles.colEvidence}>
                  {v.rings.length > 0
                    ? <span className={styles.ringTag} data-mono>{v.rings[0]}</span>
                    : <span className={styles.signalText}>{v.reasons[0] ?? '—'}</span>}
                </td>
                <td className={styles.colReasons}>
                  <div className={styles.chips}>
                    {v.reasons.slice(0, 2).map(r => <span key={r} className={styles.chip}>{r}</span>)}
                    {v.reasons.length > 2 && <span className={styles.chipMore}>+{v.reasons.length - 2}</span>}
                  </div>
                </td>
                <td className={styles.colExp}>
                  <span className={styles.expVal} data-mono>₹{(v.exposure_inr/100000).toFixed(2)}L</span>
                </td>
                <td className={styles.colAge}>
                  <span className={styles.ageVal} data-mono>{ageDays(v.first_seen)}d</span>
                </td>
                <td className={styles.colSev}>
                  <span className={`${styles.sev} ${styles[SEV[v.severity]?.cls ?? 'watch']}`}>
                    <span className={styles.sevDot} />{SEV[v.severity]?.label ?? v.severity}
                  </span>
                </td>
                <td className={styles.colGo}>
                  <button className={styles.go} onClick={(e) => { e.stopPropagation(); openRow(v); }} aria-label={`Open ${v.name}`}>
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

function MetricCard({ icon, label, value, accent, foot, mono }: {
  icon: React.ReactNode; label: string; value: string; accent: string; foot: string; mono?: boolean;
}) {
  return (
    <div className={styles.metric}>
      <div className={styles.metricTop}>
        <span className={`${styles.metricIcon} ${styles[`ac_${accent}`]}`}>{icon}</span>
        <span className={styles.metricLabel}>{label}</span>
      </div>
      <div className={`${styles.metricValue} ${mono ? styles.metricValueMono : ''}`}>{value}</div>
      <div className={styles.metricFoot} data-mono>{foot}</div>
    </div>
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
