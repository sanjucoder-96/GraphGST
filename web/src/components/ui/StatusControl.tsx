import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Check, Lock } from 'lucide-react';
import { patchCaseStatus, adminEnabled } from '../../lib/api';
import { useStore } from '../../lib/store';
import { STATUS_META, STATUS_ORDER, StatusPill } from './Status';
import type { InvestigationStatus } from '../../types/case';
import styles from './StatusControl.module.css';

/* Editable investigation-status control. Writes the real PATCH
   /api/cases/{id} (admin-gated) — the pill reflects persisted Neo4j state,
   not local React state. In deployment mode (no bundled admin token) it
   renders read-only. */
export function StatusControl({ gstin, status }: {
  gstin: string; status: InvestigationStatus;
}) {
  const qc = useQueryClient();
  const pushToast = useStore(s => s.pushToast);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<InvestigationStatus | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const editable = adminEnabled();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [open]);

  if (!editable) {
    return (
      <div className={styles.readonly} title="Status is read-only in deployment mode">
        <StatusPill status={status} />
        <Lock size={11} strokeWidth={2} className={styles.lock} />
      </div>
    );
  }

  async function choose(next: InvestigationStatus) {
    setOpen(false);
    if (next === status) return;
    setBusy(next);
    const res = await patchCaseStatus(gstin, next);
    setBusy(null);
    if (res.ok) {
      // Re-read persisted state — the pill must reflect Neo4j, not optimism.
      qc.invalidateQueries({ queryKey: ['case', gstin] });
      qc.invalidateQueries({ queryKey: ['caseList'] });
      pushToast({ kind: 'ok', title: 'Status updated', body: `${STATUS_META[status].label} → ${STATUS_META[next].label} · persisted` });
    } else {
      const why = res.code === 'disabled' ? 'admin token not configured'
        : res.code === 401 ? 'unauthorized (bad admin token)'
        : res.code === 'network' ? 'backend unreachable' : `HTTP ${res.code}`;
      pushToast({ kind: 'warn', title: 'Status not saved', body: why });
    }
  }

  return (
    <div className={styles.wrap} ref={ref}>
      <button className={styles.trigger} onClick={() => setOpen(o => !o)} aria-haspopup="listbox" aria-expanded={open}>
        <StatusPill status={busy ?? status} />
        <ChevronDown size={13} strokeWidth={2} className={`${styles.chev} ${open ? styles.chevOpen : ''}`} />
      </button>
      {open && (
        <div className={styles.menu} role="listbox">
          <div className={styles.menuLabel}>Set investigation status</div>
          {STATUS_ORDER.map(s => (
            <button key={s} className={styles.item} role="option" aria-selected={s === status} onClick={() => choose(s)}>
              <StatusPill status={s} size="sm" />
              {s === status && <Check size={13} strokeWidth={2.5} className={styles.check} />}
            </button>
          ))}
          <div className={styles.menuFoot} data-mono>PATCH /api/cases/{gstin.slice(0, 8)}…</div>
        </div>
      )}
    </div>
  );
}
