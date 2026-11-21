import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, Play, RefreshCw, FlaskConical, ShieldCheck, AlertTriangle } from 'lucide-react';
import { API_BASE, getDashboardSummary, getDatasetCurrent, postDetect } from '../../lib/api';
import { Button } from '../../components/ui/Button';
import { useStore } from '../../lib/store';
import styles from './DataHealth.module.css';

/* Data Sources — backend + fixture provenance. Every value cites where it
   came from; fixtures are labelled demo. No fabricated numbers. */

/* Data Provenance — the graph currently loaded (GET /api/dataset/current).
   The console must never present real/public data as synthetic, nor synthetic
   as real; this panel makes the distinction explicit and traceable. */
function DataProvenance() {
  const q = useQuery({ queryKey: ['dataset', 'current'] as const, queryFn: getDatasetCurrent, staleTime: 30_000 });
  const d = q.data?.data;
  if (!d) return null;
  const isPublic = d.kind === 'PUBLIC_DATASET';
  const fmt = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString('en-IN'));
  const kv: [string, string][] = [
    ['Source', d.source || '—'],
    ['Dataset version', d.dataset_id || d.name || '—'],
    ['Date range', d.date_min && d.date_min !== '—' ? `${d.date_min} → ${d.date_max}` : 'none (no dates)'],
    ['Records', fmt(d.transactions)],
    ['Entities', fmt(d.entities)],
    ['License', d.license || '—'],
    ['Last imported', d.ingested_at ? d.ingested_at.slice(0, 19).replace('T', ' ') : '—'],
    ['Anonymization', d.anonymized ? 'anonymized (pseudonyms)' : 'none'],
  ];
  return (
    <section className={styles.prov}>
      <div className={styles.provHead}>
        <span className={`${styles.provKind} ${isPublic ? styles.provPublic : styles.provDemo}`}>
          {isPublic ? <Database size={13} strokeWidth={2} /> : <FlaskConical size={13} strokeWidth={2} />}
          {isPublic ? 'Public dataset — research validation' : 'Synthetic demo'}
        </span>
        <span className={styles.provName} data-mono>{d.name}</span>
        <span className={styles.provReal} title="Real taxpayer data?">
          <ShieldCheck size={12} strokeWidth={2} />
          {d.is_real_taxpayer_data ? 'REAL TAXPAYER DATA' : 'not real taxpayer data'}
        </span>
      </div>
      <div className={styles.provGrid}>
        {kv.map(([k, v]) => (
          <div key={k} className={styles.provCell}>
            <div className={styles.provKey}>{k}</div>
            <div className={styles.provVal} data-mono>{v}</div>
          </div>
        ))}
      </div>
      {d.notes && <div className={styles.provNotes}>{d.notes}</div>}
      {d.warnings && d.warnings.length > 0 && (
        <ul className={styles.provWarn}>
          {d.warnings.map((w, i) => (
            <li key={i}><AlertTriangle size={11} strokeWidth={2} /> {w}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

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

      <DataProvenance />

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
