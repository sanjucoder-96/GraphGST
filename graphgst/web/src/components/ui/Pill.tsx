import type { ReactNode } from 'react';
import styles from './Pill.module.css';

export type PillTone = 'info' | 'ok' | 'warn' | 'bad' | 'signal' | 'neutral';

interface Props {
  tone?: PillTone;
  solid?: boolean;
  dot?: boolean;
  children: ReactNode;
  title?: string;
}

export function Pill({ tone = 'neutral', solid = false, dot = false, children, title }: Props) {
  const cls = [
    styles.pill,
    tone === 'info'   ? styles.info   : '',
    tone === 'ok'     ? styles.ok     : '',
    tone === 'warn'   ? styles.warn   : '',
    tone === 'bad'    ? styles.bad    : '',
    tone === 'signal' ? styles.signal : '',
    solid ? styles.solid : ''
  ].filter(Boolean).join(' ');
  return (
    <span className={cls} title={title}>
      {dot ? <span className={styles.dot} /> : null}
      {children}
    </span>
  );
}
