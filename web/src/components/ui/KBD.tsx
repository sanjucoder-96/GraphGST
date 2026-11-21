import type { ReactNode } from 'react';

interface Props { children: ReactNode; }

/* Keyboard hint chip. */
export function KBD({ children }: Props) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 18,
        height: 18,
        padding: '0 5px',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        fontWeight: 500,
        lineHeight: 1,
        color: 'var(--text-2)',
        background: 'var(--bg-3)',
        border: '1px solid var(--line-2)',
        borderRadius: 'var(--r-xs)',
        letterSpacing: 0
      }}
    >
      {children}
    </span>
  );
}
