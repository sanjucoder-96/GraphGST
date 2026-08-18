import { Search } from 'lucide-react';
import { useStore } from '../../lib/store';
import { KBD } from '../ui/KBD';
import styles from './TopBar.module.css';

interface Props { latency: number; }

export function TopBar({ latency }: Props) {
  const env = useStore(s => s.env);
  const setPaletteOpen = useStore(s => s.setCommandPaletteOpen);

  return (
    <div className={styles.bar}>
      <div className={styles.title}>
        GRAPH GST <span className={styles.sub}>Investigator Console v6</span>
      </div>
      <div className={styles.spacer} />
      {/* Single search / command-palette entry — one keystroke, one control. */}
      <button
        type="button"
        className={styles.search}
        onClick={() => setPaletteOpen(true)}
        aria-label="Open command palette (⌘K)"
      >
        <Search size={12} strokeWidth={1.75} />
        <span style={{ fontSize: 'var(--fs-micro)' }}>Search GSTINs, invoices, rings, commands</span>
        <span className={styles.hint}>
          <KBD>/</KBD>
          <KBD>⌘K</KBD>
        </span>
      </button>
      <span className={styles.latency}>{latency} ms</span>
      <span className={`${styles.env} ${env === 'LIVE' ? styles.envLive : styles.envDemo}`}>
        <span className={styles.dot} />
        {env}
      </span>
    </div>
  );
}
