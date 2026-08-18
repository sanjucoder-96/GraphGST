import { useQuery, useQueryClient } from '@tanstack/react-query';
import { API_BASE, getDashboardSummary, postDetect } from '../../lib/api';
import { Pill } from '../../components/ui/Pill';
import { Button } from '../../components/ui/Button';
import { useStore } from '../../lib/store';

export function DataHealthPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['dashboard', 'summary'] as const, queryFn: getDashboardSummary, staleTime: 15_000 });
  const env = useStore(s => s.env);
  const neo4jOk = useStore(s => s.neo4jOk);
  const pushToast = useStore(s => s.pushToast);

  const rows: { k: string; v: string; tone?: 'ok' | 'warn' | 'bad' | 'info' | 'signal' }[] = [
    { k: 'ENV',                v: env, tone: env === 'LIVE' ? 'ok' : 'info' },
    { k: 'NEO4J',              v: neo4jOk ? 'connected' : 'unreachable', tone: neo4jOk ? 'ok' : 'bad' },
    { k: 'API BASE',           v: API_BASE },
    { k: 'RINGS OPEN',         v: String(q.data?.data.rings_open ?? '—') },
    { k: 'VENDORS HIGH',       v: String(q.data?.data.vendors_high ?? '—') },
    { k: 'EXPOSURE ₹',         v: (q.data?.data.exposure_total ?? 0).toLocaleString('en-IN') },
    { k: 'LAST DETECTION',     v: q.data?.data.last_detection_at ?? '—' },
    { k: 'RESPONSE LATENCY',   v: `${q.data?.latency_ms ?? '—'} ms` },
    { k: 'FROM MOCK',          v: q.data?.fromMock ? 'yes' : 'no', tone: q.data?.fromMock ? 'warn' : 'ok' }
  ];

  const detect = async () => {
    pushToast({ kind: 'info', title: 'Detection started', body: 'POST /api/rings/detect' });
    const res = await postDetect();
    qc.invalidateQueries();
    pushToast({ kind: res.fromMock ? 'warn' : 'ok', title: res.fromMock ? 'Fell back to DEMO' : `Detection returned ${res.data.length} rings`, body: `${res.latency_ms} ms` });
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <h2 style={{ fontSize: 'var(--fs-h)', color: 'var(--text-strong)', fontWeight: 500 }}>Data Health</h2>
        <span style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-chrome)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Backend + fixtures</span>
      </div>
      <div style={{ marginTop: 16, border: '1px solid var(--border-solid)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr auto', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid var(--border-solid)', padding: '6px 12px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-chrome)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          <span>Metric</span><span>Value</span><span>Tone</span>
        </div>
        {rows.map((r) => (
          <div key={r.k} style={{ display: 'grid', gridTemplateColumns: '180px 1fr auto', padding: '6px 12px', borderBottom: '1px solid var(--border-solid)', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-chrome)', letterSpacing: '0.06em' }}>{r.k}</span>
            <span style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-body)' }}>{r.v}</span>
            <span>{r.tone && <Pill tone={r.tone} solid>{r.tone}</Pill>}</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
        <Button variant="primary" size="sm" onClick={detect}>Run detection now</Button>
        <Button variant="ghost" size="sm" onClick={() => { qc.invalidateQueries(); pushToast({ kind: 'info', title: 'Cache cleared' }); }}>Reload DEMO fixture</Button>
      </div>
      <p style={{ marginTop: 24, color: 'var(--text-dim)', fontSize: 'var(--fs-micro)', maxWidth: 640 }}>
        Every value on this page comes either from <span data-mono>GET /api/dashboard/summary</span> or, when the backend is offline, from <span data-mono>src/lib/mocks.ts</span>. There are no synthetic latency or confidence numbers on this page.
      </p>
    </div>
  );
}
