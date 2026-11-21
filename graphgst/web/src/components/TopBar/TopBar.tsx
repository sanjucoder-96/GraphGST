import { Search, Bell, SlidersHorizontal, FlaskConical, Database } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useStore } from '../../lib/store';
import { getDatasetCurrent } from '../../lib/api';
import { KBD } from '../ui/KBD';
import styles from './TopBar.module.css';

interface Props { latency: number; }

/* Dataset provenance banner — the console must never present real/public data
   as synthetic, nor synthetic as real. Reads GET /api/dataset/current. */
function DatasetBadge() {
  const q = useQuery({
    queryKey: ['dataset', 'current'] as const,
    queryFn: getDatasetCurrent,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  const d = q.data?.data;
  const isPublic = d?.kind === 'PUBLIC_DATASET';
  const title = isPublic
    ? `PUBLIC DATASET — ${d?.name}\nSource: ${d?.source}\nLicense: ${d?.license}\n${d?.notes ?? ''}`
    : 'SYNTHETIC DEMO — deterministic generated data (seed 42). Not real taxpayer data.';
  return (
    <span className={`${styles.dataset} ${isPublic ? styles.dsPublic : styles.dsDemo}`} title={title}>
      {isPublic ? <Database size={12} strokeWidth={2} /> : <FlaskConical size={12} strokeWidth={2} />}
      {isPublic ? 'Public dataset' : 'Synthetic demo'}
      {isPublic && d?.name && <span className={styles.dsName} data-mono>{d.name}</span>}
    </span>
  );
}

export function TopBar({ latency }: Props) {
  const env = useStore(s => s.env);
  const setPaletteOpen = useStore(s => s.setCommandPaletteOpen);

  return (
    <div className={styles.bar}>
      {/* Global search — the primary top-bar control */}
      <button
        type="button"
        className={styles.search}
        onClick={() => setPaletteOpen(true)}
        aria-label="Search"
      >
        <Search size={15} strokeWidth={1.75} />
        <span className={styles.searchLabel}>Search entities, invoices, rings…</span>
        <span className={styles.hint}>
          <KBD>⌘</KBD><KBD>K</KBD>
        </span>
      </button>

      <div className={styles.spacer} />

      <DatasetBadge />

      <button type="button" className={styles.iconBtn} title="Filters" aria-label="Filters">
        <SlidersHorizontal size={16} strokeWidth={1.75} />
      </button>
      <button type="button" className={styles.iconBtn} title="Alerts" aria-label="Alerts">
        <Bell size={16} strokeWidth={1.75} />
        <span className={styles.badge}>3</span>
      </button>

      <div className={styles.divider} />

      <div className={styles.status}>
        <span className={styles.latency} data-mono>{latency}ms</span>
        <span className={`${styles.env} ${env === 'LIVE' ? styles.envLive : styles.envDemo}`}>
          <span className={styles.dot} />
          {env}
        </span>
      </div>
    </div>
  );
}
