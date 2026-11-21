import { NavLink } from 'react-router-dom';
import { LayoutGrid, GitBranch, Building2, ClipboardCheck, Database, BarChart3, HelpCircle, Command } from 'lucide-react';
import { useStore } from '../../lib/store';
import styles from './LeftRail.module.css';

interface Item { to: string; label: string; hint: string; icon: JSX.Element; }

/* Primary navigation for the intelligence workspace. Terminology a
   technical/financial investigator understands — no case-file language. */
const groups: { title: string; items: Item[] }[] = [
  {
    title: 'Investigate',
    items: [
      { to: '/',            label: 'Cases',        hint: 'G C', icon: <LayoutGrid   size={17} strokeWidth={1.75} /> },
      { to: '/rings',       label: 'Rings',        hint: 'G R', icon: <GitBranch    size={17} strokeWidth={1.75} /> },
      { to: '/vendors',     label: 'Vendors',      hint: 'G V', icon: <Building2    size={17} strokeWidth={1.75} /> },
    ],
  },
  {
    title: 'System',
    items: [
      { to: '/data-health', label: 'Data Sources', hint: 'G D', icon: <Database     size={17} strokeWidth={1.75} /> },
      { to: '/model-card',  label: 'Model Card',   hint: 'G M', icon: <BarChart3    size={17} strokeWidth={1.75} /> },
      { to: '/docs',        label: 'Docs',         hint: '',    icon: <ClipboardCheck size={17} strokeWidth={1.75} /> },
    ],
  },
];

export function LeftRail() {
  const openShortcuts = useStore(s => s.setShortcutsOpen);
  const openPalette = useStore(s => s.setCommandPaletteOpen);

  return (
    <nav className={styles.rail} aria-label="Primary">
      <button
        type="button"
        className={styles.brand}
        onClick={() => openPalette(true)}
        title="Command menu (⌘K)"
      >
        <span className={styles.mark}>
          <span className={styles.markGlyph} />
        </span>
        <span className={styles.brandName}>Graph<span className={styles.brandAccent}>GST</span></span>
      </button>

      <div className={styles.nav}>
        {groups.map((g) => (
          <div key={g.title} className={styles.group}>
            <div className={styles.groupTitle}>{g.title}</div>
            {g.items.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                className={({ isActive }) => `${styles.item} ${isActive ? styles.active : ''}`}
                title={it.label}
                end={it.to === '/'}
              >
                <span className={styles.icon}>{it.icon}</span>
                <span className={styles.itemLabel}>{it.label}</span>
                {it.hint && <span className={styles.itemHint} data-mono>{it.hint}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </div>

      <div className={styles.foot}>
        <button type="button" className={styles.footBtn} onClick={() => openPalette(true)} title="Command menu (⌘K)">
          <Command size={15} strokeWidth={1.75} />
          <span>Command</span>
          <span className={styles.kbd} data-mono>⌘K</span>
        </button>
        <button type="button" className={styles.footBtn} onClick={() => openShortcuts(true)} title="Keyboard shortcuts (?)">
          <HelpCircle size={15} strokeWidth={1.75} />
          <span>Shortcuts</span>
          <span className={styles.kbd} data-mono>?</span>
        </button>
      </div>
    </nav>
  );
}
