import { NavLink } from 'react-router-dom';
import { FolderKanban, Radar, Users, Activity, FileText, HelpCircle } from 'lucide-react';
import { useStore } from '../../lib/store';
import styles from './LeftRail.module.css';

interface Item { to: string; label: string; hint: string; icon: JSX.Element; }

const items: Item[] = [
  { to: '/',            label: 'Cases',   hint: 'g q', icon: <FolderKanban size={20} strokeWidth={1.5} /> },
  { to: '/rings',       label: 'Rings',   hint: 'g r', icon: <Radar        size={20} strokeWidth={1.5} /> },
  { to: '/vendors',     label: 'Vendors', hint: 'g v', icon: <Users        size={20} strokeWidth={1.5} /> },
  { to: '/data-health', label: 'Health',  hint: 'g h', icon: <Activity     size={20} strokeWidth={1.5} /> },
  { to: '/docs',        label: 'Docs',    hint: '',    icon: <FileText     size={20} strokeWidth={1.5} /> }
];

export function LeftRail() {
  const openShortcuts = useStore(s => s.setShortcutsOpen);
  return (
    <nav className={styles.rail} aria-label="Primary">
      <div className={styles.brand}>GGST</div>
      {items.map((it) => (
        <NavLink
          key={it.to}
          to={it.to}
          className={({ isActive }) => `${styles.item} ${isActive ? styles.active : ''}`}
          title={`${it.label}${it.hint ? ` · ${it.hint}` : ''}`}
          end={it.to === '/'}
        >
          <span className={styles.icon}>{it.icon}</span>
          <span className={styles.hint}>{it.hint || it.label.slice(0, 3).toUpperCase()}</span>
        </NavLink>
      ))}
      <div className={styles.spacer} />
      <div className={styles.footerRow}>
        <button
          type="button"
          className={styles.item}
          style={{ background: 'transparent', border: 0 }}
          onClick={() => openShortcuts(true)}
          title="Shortcuts (?)"
          aria-label="Show keyboard shortcuts"
        >
          <HelpCircle size={18} strokeWidth={1.5} />
          <span className={styles.hint}>?</span>
        </button>
      </div>
    </nav>
  );
}
