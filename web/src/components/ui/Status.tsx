import styles from './Status.module.css';
import type { InvestigationStatus } from '../../types/case';

export const STATUS_META: Record<InvestigationStatus, { label: string; cls: string }> = {
  open:          { label: 'Open',          cls: 'open' },
  investigating: { label: 'Investigating', cls: 'investigating' },
  escalated:     { label: 'Escalated',     cls: 'escalated' },
  resolved:      { label: 'Resolved',      cls: 'resolved' },
  dismissed:     { label: 'Dismissed',     cls: 'dismissed' },
};

export const STATUS_ORDER: InvestigationStatus[] =
  ['open', 'investigating', 'escalated', 'resolved', 'dismissed'];

/* Read-only status pill. Semantic color: active work is indigo, escalation
   is red, resolution green, dismissal muted. */
export function StatusPill({ status, size = 'md' }: {
  status: InvestigationStatus; size?: 'sm' | 'md';
}) {
  const m = STATUS_META[status] ?? STATUS_META.open;
  return (
    <span className={`${styles.pill} ${styles[m.cls]} ${styles[size]}`}>
      <span className={styles.dot} />
      {m.label}
    </span>
  );
}
