import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect } from 'react';
import { X } from 'lucide-react';
import { useStore } from '../../lib/store';
import { KBD } from '../ui/KBD';
import styles from './ShortcutsOverlay.module.css';

// Keyboard-shortcuts help overlay. Uses the same 140ms motion vocabulary
// and portal skeleton as the command palette — replaces the native
// window.alert() so we do not surface OS chrome inside the console.

interface Row { keys: string[]; label: string; group?: string; }

const ROWS: Row[] = [
  { group: 'Global',    keys: ['⌘', 'K'],       label: 'Open command palette' },
  { group: 'Global',    keys: ['/'],            label: 'Open search palette' },
  { group: 'Global',    keys: ['Esc'],          label: 'Close overlay · clear selection' },
  { group: 'Navigate',  keys: ['g', 'q'],       label: 'Cases' },
  { group: 'Navigate',  keys: ['g', 'r'],       label: 'Rings' },
  { group: 'Navigate',  keys: ['g', 'v'],       label: 'Vendors' },
  { group: 'Navigate',  keys: ['g', 'h'],       label: 'Data Health' },
  { group: 'Queue',     keys: ['j'],            label: 'Row down' },
  { group: 'Queue',     keys: ['k'],            label: 'Row up' },
  { group: 'Queue',     keys: ['↵'],            label: 'Open row' },
  { group: 'Graph',     keys: ['+', '−'],       label: 'Zoom · zoom out' },
  { group: 'Graph',     keys: ['0'],            label: 'Fit to view' },
  { group: 'Graph',     keys: ['⇧', 'F'],       label: 'Fit selection' },
  { group: 'Graph',     keys: ['⇧', 'E'],       label: 'Expand neighbors' },
  { group: 'Graph',     keys: ['⇧', 'I'],       label: 'Isolate subgraph' },
  { group: 'Graph',     keys: ['⇧', 'H'],       label: 'Hide selection' },
  { group: 'Graph',     keys: ['⇧', 'M'],       label: 'Mark for report' },
  { group: 'Graph',     keys: ['⌘', 'C'],       label: 'Copy id' },
  { group: 'Timeline',  keys: ['Space'],        label: 'Play · pause' },
  { group: 'Timeline',  keys: ['←', '→'],       label: 'Step ±1 tick' },
  { group: 'Timeline',  keys: ['⇧', '←/→'],     label: 'Step ±7 ticks' },
  { group: 'Timeline',  keys: ['Home', 'End'],  label: 'First · last tick' },
  { group: 'Panel',     keys: ['1', '2', '3'],  label: 'Overview · Evidence · Counterfactual' },
  { group: 'Panel',     keys: ['[', ']'],       label: 'Prev · next ring' }
];

export function ShortcutsOverlay() {
  const open = useStore(s => s.shortcutsOpen);
  const setOpen = useStore(s => s.setShortcutsOpen);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); setOpen(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, setOpen]);

  const grouped: Record<string, Row[]> = {};
  for (const r of ROWS) {
    const g = r.group ?? 'Other';
    (grouped[g] ??= []).push(r);
  }

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="sh-backdrop"
          className={styles.backdrop}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            key="sh-panel"
            className={styles.panel}
            initial={{ y: 8, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 8, opacity: 0 }}
            transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-label="Keyboard shortcuts"
          >
            <div className={styles.header}>
              <span>Keyboard shortcuts</span>
              <button type="button" onClick={() => setOpen(false)} title="Close (Esc)" aria-label="Close">
                <X size={12} strokeWidth={1.5} />
              </button>
            </div>
            <div className={styles.grid}>
              {Object.entries(grouped).map(([group, rows]) => (
                <section key={group} className={styles.group}>
                  <h3>{group}</h3>
                  <ul>
                    {rows.map((r) => (
                      <li key={r.label}>
                        <span className={styles.keys}>
                          {r.keys.map((k, i) => (<KBD key={i}>{k}</KBD>))}
                        </span>
                        <span className={styles.label}>{r.label}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
            <div className={styles.footer}>
              <span><KBD>Esc</KBD> close</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
