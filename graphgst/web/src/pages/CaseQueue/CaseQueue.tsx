import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { PlayCircle } from 'lucide-react';
import { getVendorRisk, getRings, postDetect } from '../../lib/api';
import { RiskSparkline } from '../../components/RiskSparkline/RiskSparkline';
import { Pill } from '../../components/ui/Pill';
import { Button } from '../../components/ui/Button';
import { ReasonChip } from '../../components/EvidencePanel/ReasonChip';
import { useStore } from '../../lib/store';
import { useShortcuts } from '../../lib/keyboard';
import type { Vendor } from '../../types/domain';
import styles from './CaseQueue.module.css';

type SortKey = 'score' | 'exposure' | 'age';

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

  const vendors = useQuery({
    queryKey: ['vendors', 'risk'] as const,
    queryFn: getVendorRisk,
    staleTime: 30_000
  });
  const rings = useQuery({
    queryKey: ['rings', 'list'] as const,
    queryFn: getRings,
    staleTime: 30_000
  });

  useEffect(() => {
    if (vendors.data?.fromMock || rings.data?.fromMock) {
      pushToast({ kind: 'warn', title: 'Backend unreachable', body: 'Serving DEMO fixtures.' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vendors.data?.fromMock, rings.data?.fromMock]);

  const rows = useMemo(() => {
    const list = vendors.data?.data ?? [];
    const filtered = list.filter(v => {
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
  }, [vendors.data, severity, type, scenario, q, sort]);

  const [cursor, setCursor] = useState(0);
  useEffect(() => { if (cursor >= rows.length) setCursor(0); }, [rows, cursor]);

  useShortcuts({
    'j': () => setCursor(c => Math.min(rows.length - 1, c + 1)),
    'k': () => setCursor(c => Math.max(0, c - 1)),
    'enter': () => { const row = rows[cursor]; if (!row) return; openRow(row); }
  });

  function openRow(v: Vendor): void {
    if (v.rings.length > 0) navigate(`/ring/${v.rings[0]}?tab=overview&node=${v.gstin}`);
    else navigate(`/entity/${v.gstin}?tab=overview`);
  }

  function updateParam(k: string, val: string | null): void {
    const next = new URLSearchParams(params);
    if (val == null || val === '') next.delete(k);
    else next.set(k, val);
    setParams(next, { replace: true });
  }

  const onDetect = async () => {
    pushToast({ kind: 'info', title: 'Detection started', body: 'POST /api/rings/detect' });
    const res = await postDetect();
    qc.invalidateQueries({ queryKey: ['rings'] });
    qc.invalidateQueries({ queryKey: ['vendors'] });
    pushToast({
      kind: res.fromMock ? 'warn' : 'ok',
      title: res.fromMock ? 'Detection fell back to DEMO' : `Detection returned ${res.data.length} rings`,
      body: `${res.latency_ms} ms`
    });
  };

  const ageDays = (iso: string): number => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000));

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <span style={{ color: 'var(--text-strong)', fontSize: 'var(--fs-strong)', fontWeight: 500 }}>Case Queue</span>
        <div className={styles.filters}>
          <select className={styles.select} value={severity} onChange={(e) => updateParam('severity', e.target.value || null)}>
            <option value="">Severity</option>
            <option value="high">High</option>
            <option value="med">Medium</option>
            <option value="low">Low</option>
          </select>
          <select className={styles.select} value={type} onChange={(e) => updateParam('type', e.target.value || null)}>
            <option value="">Type</option>
            <option value="vendor">Vendor</option>
            <option value="buyer">Buyer</option>
            <option value="transporter">Transporter</option>
          </select>
          <select className={styles.select} value={scenario} onChange={(e) => updateParam('scenario', e.target.value || null)}>
            <option value="">Scenario</option>
            <option value="circular_itc_chain">Circular ITC chain</option>
            <option value="polymer_layered_ring">Polymer layered ring</option>
            <option value="flash_steel_triad">Flash steel triad</option>
            <option value="watchlist">Watchlist</option>
          </select>
          <select className={styles.select} value={sort} onChange={(e) => updateParam('sort', e.target.value)}>
            <option value="score">Sort · Risk</option>
            <option value="exposure">Sort · Exposure</option>
            <option value="age">Sort · Age</option>
          </select>
        </div>
        <div className={styles.spacer} />
        <span className={styles.count} data-mono>{rows.length} / {vendors.data?.data.length ?? 0}</span>
        <Button variant="primary" size="sm" onClick={onDetect}>
          <PlayCircle size={12} strokeWidth={1.5} /> Detect
        </Button>
      </div>

      <div className={styles.wrap}>
        {rows.length === 0 ? (
          <div className={styles.emptyBox}>0 rows match the current filters. <button onClick={() => setParams(new URLSearchParams(), { replace: true })} style={{ color: 'var(--signal)', background:'transparent', border: 0, cursor: 'pointer' }}>Clear filters</button></div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Risk</th>
                <th>Trend</th>
                <th>Entity</th>
                <th>GSTIN</th>
                <th>Primary evidence</th>
                <th className={styles.right}>Exposure ₹</th>
                <th className={styles.right}>First seen</th>
                <th>Reasons</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v, i) => (
                <tr
                  key={v.gstin}
                  className={i === cursor ? styles.selected : ''}
                  onClick={() => setCursor(i)}
                  onDoubleClick={() => openRow(v)}
                >
                  <td className={`${styles.mono} ${styles.strong}`}>{v.risk_score.toFixed(3)}</td>
                  <td><RiskSparkline data={v.sparkline} /></td>
                  <td>{v.name} <span style={{color:'var(--text-dim)', fontSize:'var(--fs-micro)'}}> {v.state}</span></td>
                  <td className={styles.mono}>{v.gstin}</td>
                  <td className={styles.dim}>{v.rings.length ? `ring member: ${v.rings[0]}` : v.reasons[0] ?? '—'}</td>
                  <td className={`${styles.mono} ${styles.right}`}>{v.exposure_inr.toLocaleString('en-IN')}</td>
                  <td className={`${styles.mono} ${styles.right}`}>{ageDays(v.first_seen)}d ago</td>
                  <td>
                    <div className={styles.chipCell}>
                      {v.reasons.slice(0, 3).map(r => (<ReasonChip key={r} label={r} />))}
                    </div>
                  </td>
                  <td>
                    <Pill tone={v.severity === 'high' ? 'bad' : v.severity === 'med' ? 'warn' : 'info'} dot>{v.severity}</Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
