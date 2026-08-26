import { Search, Bell, SlidersHorizontal } from 'lucide-react';
import { useStore } from '../../lib/store';
import { KBD } from '../ui/KBD';
import styles from './TopBar.module.css';

interface Props { latency: number; }

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
