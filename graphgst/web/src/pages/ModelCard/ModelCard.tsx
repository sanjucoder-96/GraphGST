import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, AlertTriangle, MinusCircle, Info, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import styles from './ModelCard.module.css';
import { getModelCard } from '../../lib/api';
import type { ModelCard, ModelCardStatus } from '../../types/domain';

function fmt(n: number | null | undefined, unit: string): string {
  if (n === null || n === undefined) return '—';
  if (unit === 'ratio' || unit === 'auc') return n.toFixed(3);
  return String(n);
}

function statusIcon(status: ModelCardStatus) {
  const sz = 14;
  const sw = 1.5;
  switch (status) {
    case 'IMPROVED':  return <ArrowUpRight size={sz} strokeWidth={sw} />;
    case 'UNCHANGED': return <MinusCircle size={sz} strokeWidth={sw} />;
    case 'REGRESSED': return <AlertTriangle size={sz} strokeWidth={sw} />;
    case 'NEW':       return <Info size={sz} strokeWidth={sw} />;
    case 'MISSING':   return <AlertTriangle size={sz} strokeWidth={sw} />;
    default:          return <Info size={sz} strokeWidth={sw} />;
  }
}

export function ModelCardPage() {
  const q = useQuery<ModelCard>({
    queryKey: ['benchmarks-model-card'],
    queryFn: async () => (await getModelCard()).data,
  });

  const data = q.data;

  if (q.isLoading) {
    return <div className={styles.wrap}><div className={styles.state}>Loading…</div></div>;
  }
  if (q.isError || !data) {
    return <div className={styles.wrap}><div className={styles.state}>No benchmarks available</div></div>;
  }

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>Model Card · Benchmarks</div>
          <h1 className={styles.title}>Measured performance</h1>
          <p className={styles.sub}>
            Every headline metric this system reports, produced by
            <span data-mono> python -m benchmarks.run_all </span>
            against a deterministic 500-GSTIN synthetic dataset with ground
            truth. Each metric is gated against a committed baseline.
          </p>
        </div>
        <div className={styles.meta}>
          <div className={styles.metaRow}>
            <span className={styles.metaKey}>Generated</span>
            <span data-mono>{data.generated_at?.slice(0, 19).replace('T', ' ') ?? '—'}</span>
          </div>
          <div className={styles.metaRow}>
            <span className={styles.metaKey}>Commit</span>
            <span data-mono>{(data.git_commit ?? '—').slice(0, 8)}</span>
          </div>
          <div className={styles.metaRow}>
            <span className={styles.metaKey}>Tolerance</span>
            <span data-mono>±{data.tolerance_abs?.toFixed(3) ?? '—'}</span>
          </div>
          <div className={styles.metaRow}>
            <span className={styles.metaKey}>Overall</span>
            <span data-mono className={data.overall_pass ? styles.pass : styles.fail}>
              {data.overall_pass ? 'PASS' : (data.overall_pass === false ? 'FAIL' : '—')}
            </span>
          </div>
        </div>
      </header>

      <section className={styles.grid}>
        {data.cards.map((c) => (
          <article key={c.metric} className={`${styles.card} ${c.status === 'REGRESSED' ? styles.regressed : ''}`}>
            <div className={styles.cardTop}>
              <span className={styles.module}>{c.module.toUpperCase()}</span>
              <span className={`${styles.statusPill} ${styles[c.status.toLowerCase()] ?? ''}`}>
                {statusIcon(c.status)}
                {c.status}
              </span>
            </div>
            <div className={styles.headline}>{c.headline}</div>
            <div className={styles.valueRow}>
              <span className={styles.value} data-mono>{fmt(c.value, c.unit)}</span>
              <span className={styles.baseline}>
                <span className={styles.baselineKey}>vs baseline</span>
                <span data-mono>{fmt(c.baseline, c.unit)}</span>
                {c.delta !== null && (
                  <span className={styles.delta} data-mono>
                    {c.delta > 0 ? <ArrowUpRight size={11} strokeWidth={1.5} /> : c.delta < 0 ? <ArrowDownRight size={11} strokeWidth={1.5} /> : null}
                    {c.delta === 0 ? '±0.000' : (c.delta > 0 ? '+' : '') + c.delta.toFixed(3)}
                  </span>
                )}
              </span>
            </div>
            {c.notes ? <div className={styles.notes}>{c.notes}</div> : null}
            <div className={styles.metric} data-mono>{c.metric}</div>
          </article>
        ))}
      </section>

      {data.overall_pass === true && (
        <footer className={styles.footer}>
          <CheckCircle2 size={14} strokeWidth={1.5} />
          <span>All {data.cards.length} gated metrics within ±{data.tolerance_abs?.toFixed(3)} of baseline.</span>
        </footer>
      )}
    </div>
  );
}
