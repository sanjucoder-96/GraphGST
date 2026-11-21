import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getLookalike } from '../../lib/api';
import styles from './RelatedVendors.module.css';

interface Props {
  gstin: string;                   // the seed to query lookalikes for
  ringMembers?: readonly string[]; // if present, emphasise ring co-members in brand
  k?: number;                       // top-K neighbours (default 5)
  compact?: boolean;                 // small variant for the evidence panel
}

/**
 * Related Vendors — the graph-ML lookalike strip.
 *
 * Given a seed GSTIN, calls `GET /api/embed/lookalike/{seed}?k=K` and shows
 * top-K cosine-similar entities. When a `ringMembers` set is provided, any
 * neighbour that's also a ring member gets the one signal color (amber) so
 * the presenter can point at "the embedding found the ring by graph
 * behaviour alone — no ring detection needed."
 */
export function RelatedVendors({ gstin, ringMembers, k = 5, compact = false }: Props) {
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ['embed', 'lookalike', gstin, k] as const,
    queryFn: () => getLookalike(gstin, k),
    enabled: Boolean(gstin),
    staleTime: 60_000,
  });
  const memberSet = new Set(ringMembers ?? []);
  const data = q.data?.data;

  if (!gstin || q.isLoading) {
    return (
      <div className={`${styles.wrap} ${compact ? styles.compact : ''}`}>
        <header className={styles.header}>
          <span className={styles.eyebrow}>RELATED VENDORS · GRAPH-ML LOOKALIKE</span>
          <span className={styles.hint}>loading…</span>
        </header>
      </div>
    );
  }

  if (!data || data.neighbours.length === 0) {
    return (
      <div className={`${styles.wrap} ${compact ? styles.compact : ''}`}>
        <header className={styles.header}>
          <span className={styles.eyebrow}>RELATED VENDORS · GRAPH-ML LOOKALIKE</span>
          <span className={styles.hint}>no neighbours indexed for {gstin}</span>
        </header>
      </div>
    );
  }

  const hits = data.neighbours.filter(n => memberSet.has(n.gstin_id)).length;

  return (
    <div className={`${styles.wrap} ${compact ? styles.compact : ''}`}>
      <header className={styles.header}>
        <span className={styles.eyebrow}>Network similarity · graph embedding</span>
        <span className={styles.hint}>
          <span data-mono>{gstin}</span>
          <span>·</span>
          <span>top {data.neighbours.length} by cosine</span>
          {ringMembers && hits > 0 && (
            <span className={styles.hitBadge}>
              {hits}/{data.neighbours.length} ring co-member{hits === 1 ? '' : 's'}
            </span>
          )}
        </span>
      </header>
      <ul className={styles.list}>
        {data.neighbours.map((n, i) => {
          const isMember = memberSet.has(n.gstin_id);
          return (
            <li
              key={n.gstin_id}
              className={`${styles.row} ${isMember ? styles.member : ''}`}
              onClick={() => navigate(`/entity/${n.gstin_id}`)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/entity/${n.gstin_id}`); }}
              title={`Open investigation for ${n.gstin_id}`}
            >
              <span className={styles.dot} aria-hidden>
                {`K-${(i + 1).toString().padStart(2, '0')}`}
              </span>
              <span className={styles.gstin}>{n.gstin_id}</span>
              <span className={styles.sim}>{n.similarity.toFixed(3)}</span>
              <span className={styles.bar} aria-hidden>
                <span className={styles.barFill} style={{ width: `${Math.round(n.similarity * 100)}%` }} />
              </span>
              <span className={styles.chevron} aria-hidden>→</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
