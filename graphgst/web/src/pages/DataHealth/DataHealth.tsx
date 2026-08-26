import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, Play, RefreshCw } from 'lucide-react';
import { API_BASE, getDashboardSummary, postDetect } from '../../lib/api';
import { Button } from '../../components/ui/Button';
import { useStore } from '../../lib/store';
import styles from './DataHealth.module.css';

/* Data Sources — backend + fixture provenance. Every value cites where it
   came from; fixtures are labelled demo. No fabricated numbers. */

export function DataHealthPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['dashboard', 'summary'] as const, queryFn: getDashboardSummary, staleTime: 15_000 });
  const env = useStore(s => s.env);
  const neo4jOk = useStore(s => s.neo4jOk);
  const pushToast = useStore(s => s.pushToast);

  type Tone = 'ok' | 'warn' | 'bad' | 'info' | undefined;
  const rows: { k: string; v: string; source: string; tone?: Tone }[] = [
    { k: 'Environment',          v: env,                                             source: 'store.env', tone: env === 'LIVE' ? 'ok' : 'info' },
    { k: 'Neo4j',                v: neo4jOk ? 'connected' : 'unreachable',            source: '/api/dashboard/summary → .neo4j', tone: neo4jOk ? 'ok' : 'bad' },
    { k: 'API base',             v: API_BASE,                                         source: 'src/lib/api.ts · API_BASE' },
    { k: 'Rings open',           v: String(q.data?.data.rings_open ?? '—'),           source: 'GET /api/dashboard/summary' },
    { k: 'Vendors flagged high', v: String(q.data?.data.vendors_high ?? '—'),         source: 'GET /api/dashboard/summary' },
    { k: 'ITC exposure',         v: '₹' + (q.data?.data.exposure_total ?? 0).toLocaleString('en-IN'), source: 'GET /api/dashboard/summary' },
    { k: 'Last detection',       v: q.data?.data.last_detection_at ?? '—',            source: 'GET /api/dashboard/summary' },
    { k: 'Response latency',     v: `${q.data?.latency_ms ?? '—'} ms`,                source: 'roundtrip timer' },
    { k: 'Serving fixture',      v: q.data?.fromMock ? 'yes — demo fixture' : 'no — live backend', source: 'src/lib/api.ts · fromMock', tone: q.data?.fromMock ? 'warn' : 'ok' }
  ];

  const detect = async () => {
    pushToast({ kind: 'info', title: 'Detection running', body: 'POST /api/rings/detect' });
    const res = await postDetect();
    qc.invalidateQueries();
    pushToast({ kind: res.fromMock ? 'warn' : 'ok', title: res.fromMock ? 'Fell back to demo' : `Detection returned ${res.data.length} rings`, body: `${res.latency_ms}ms` });
  };

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div>
          <div className={styles.eyebrow}>Data Sources</div>
          <h1 className={styles.title}>Provenance & health</h1>
          <p className={styles.sub}>
            Each value cites its source. Values from
            <span data-mono> src/lib/mocks.ts </span>
            are labelled demo. There are no fabricated numbers on this page.
          </p>
        </div>
        <span className={styles.headIcon}><Database size={18} strokeWidth={1.75} /></span>
      </header>

      <div className={styles.table}>
        <div className={styles.thead}>
          <span>Attribute</span><span>Value / Source</span><span>State</span>
        </div>
        {rows.map((r) => (
          <div key={r.k} className={styles.row}>
            <span className={styles.k}>{r.k}</span>
            <div className={styles.vwrap}>
              <div className={styles.v} data-mono>{r.v}</div>
              <div className={styles.source}>{r.source}</div>
            </div>
            <span className={styles.tcell}>
              {r.tone && <span className={`${styles.tone} ${styles[r.tone]}`}><span className={styles.toneDot} />{r.tone}</span>}
            </span>
          </div>
        ))}
      </div>

      <div className={styles.actions}>
        <Button variant="primary" size="sm" onClick={detect}><Play size={13} strokeWidth={2} /> Run detection</Button>
        <Button variant="ghost" size="sm" onClick={() => { qc.invalidateQueries(); pushToast({ kind: 'info', title: 'Cache cleared' }); }}><RefreshCw size={13} strokeWidth={2} /> Reload fixture</Button>
      </div>
    </div>
  );
}
