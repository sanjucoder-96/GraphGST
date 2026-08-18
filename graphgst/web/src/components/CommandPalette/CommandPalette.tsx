import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useStore } from '../../lib/store';
import { KBD } from '../ui/KBD';
import { postDetect } from '../../lib/api';
import { MOCK_GSTINS, MOCK_RINGS } from '../../lib/mocks';
import styles from './CommandPalette.module.css';

type Item =
  | { kind: 'nav'; label: string; hint?: string; run: () => void }
  | { kind: 'action'; label: string; hint?: string; run: () => void }
  | { kind: 'ring'; label: string; hint?: string; ring_id: string; run: () => void }
  | { kind: 'gstin'; label: string; hint?: string; gstin: string; run: () => void };

function score(item: Item, q: string): number {
  if (!q) return 1;
  const label = item.label.toLowerCase();
  const query = q.toLowerCase();
  if (label.startsWith(query)) return 3;
  if (label.includes(query))   return 2;
  // fuzzy: all chars in order
  let i = 0;
  for (const c of label) { if (c === query[i]) i += 1; if (i === query.length) return 1; }
  return 0;
}

export function CommandPalette() {
  const open = useStore(s => s.commandPaletteOpen);
  const setOpen = useStore(s => s.setCommandPaletteOpen);
  const pushToast = useStore(s => s.pushToast);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) {
      setQ('');
      setCursor(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const items: Item[] = useMemo(() => {
    const list: Item[] = [];

    list.push({ kind: 'nav',    label: 'Go to Cases',   hint: 'g q',  run: () => { navigate('/'); setOpen(false); } });
    list.push({ kind: 'nav',    label: 'Go to Vendors', hint: 'g v',  run: () => { navigate('/vendors'); setOpen(false); } });
    list.push({ kind: 'nav',    label: 'Go to Data Health', hint: 'g h', run: () => { navigate('/data-health'); setOpen(false); } });

    list.push({ kind: 'action', label: 'Detect rings now', hint: 'POST /api/rings/detect', run: async () => {
      pushToast({ kind: 'info', title: 'Detection started', body: 'POST /api/rings/detect' });
      const res = await postDetect();
      qc.invalidateQueries({ queryKey: ['rings'] });
      pushToast({
        kind: res.fromMock ? 'warn' : 'ok',
        title: res.fromMock ? 'Detection fell back to DEMO' : `Detection returned ${res.data.length} rings`,
        body: `${res.latency_ms} ms`
      });
      setOpen(false);
    } });
    list.push({ kind: 'action', label: 'Reload DEMO fixture', run: () => {
      qc.invalidateQueries();
      pushToast({ kind: 'info', title: 'Cache invalidated', body: 'All keys will refetch.' });
      setOpen(false);
    } });
    list.push({ kind: 'action', label: 'Open docs', run: () => { navigate('/docs'); setOpen(false); } });

    for (const r of MOCK_RINGS) {
      list.push({ kind: 'ring', label: r.ring_id, hint: `score ${r.score.toFixed(3)} · ${r.members.length} members`, ring_id: r.ring_id, run: () => { navigate(`/ring/${r.ring_id}`); setOpen(false); } });
    }
    for (const g of MOCK_GSTINS) {
      list.push({ kind: 'gstin', label: g.id, hint: g.name, gstin: g.id, run: () => { navigate(`/entity/${g.id}`); setOpen(false); } });
    }
    return list;
  }, [navigate, setOpen, pushToast, qc]);

  const filtered = useMemo(() => {
    const scored = items.map((it) => ({ it, s: score(it, q) })).filter(x => x.s > 0);
    scored.sort((a, b) => b.s - a.s);
    return scored.slice(0, 24).map(x => x.it);
  }, [items, q]);

  useEffect(() => { if (cursor >= filtered.length) setCursor(0); }, [filtered, cursor]);

  const sectioned = useMemo(() => {
    const groups: Record<string, Item[]> = { Navigation: [], Actions: [], Rings: [], GSTINs: [] };
    for (const it of filtered) {
      if (it.kind === 'nav')    groups.Navigation.push(it);
      else if (it.kind === 'action') groups.Actions.push(it);
      else if (it.kind === 'ring')   groups.Rings.push(it);
      else if (it.kind === 'gstin')  groups.GSTINs.push(it);
    }
    return groups;
  }, [filtered]);

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(filtered.length - 1, c + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(0, c - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); filtered[cursor]?.run(); }
    else if (e.key === 'Escape') { e.preventDefault(); setOpen(false); }
  };

  const flatIndex = (kind: Item['kind'], idxInGroup: number): number => {
    let count = 0;
    for (const group of Object.values(sectioned)) {
      for (const it of group) {
        if (it.kind === kind && idxInGroup-- === 0) return count;
        count += 1;
      }
    }
    return -1;
  };

  // AnimatePresence stays mounted; the child inside it enters and exits.
  // That lets the declared 140ms exit animations play instead of the panel
  // vanishing instantly on close.
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="cp-backdrop"
          className={styles.backdrop}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            key="cp-panel"
            className={styles.panel}
            initial={{ y: -8, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -8, opacity: 0 }}
            transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.inputRow}>
              <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-chrome)' }}>{'>'}</span>
              <input
                ref={inputRef}
                className={styles.input}
                placeholder="Type a command, GSTIN, invoice, or ring id…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onKey}
              />
              <span className={styles.hint}><KBD>Esc</KBD></span>
            </div>
            <div className={styles.list}>
              {Object.entries(sectioned).map(([label, list]) => list.length === 0 ? null : (
                <div key={label}>
                  <div className={styles.section}>{label}</div>
                  {list.map((it, i) => {
                    const flat = flatIndex(it.kind, i);
                    const isActive = flat === cursor;
                    return (
                      <div
                        key={it.label + i}
                        className={`${styles.row} ${isActive ? styles.active : ''}`}
                        onClick={it.run}
                        onMouseEnter={() => setCursor(flat)}
                      >
                        <span className={styles.k} data-mono>{it.label}</span>
                        {it.hint ? <span className={styles.desc}>{it.hint}</span> : null}
                      </div>
                    );
                  })}
                </div>
              ))}
              {filtered.length === 0 && (
                <div style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: 'var(--fs-micro)' }}>No matches.</div>
              )}
            </div>
            <div className={styles.footer}>
              <span><KBD>↑</KBD><KBD>↓</KBD> navigate</span>
              <span><KBD>↵</KBD> run</span>
              <span><KBD>Esc</KBD> close</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
