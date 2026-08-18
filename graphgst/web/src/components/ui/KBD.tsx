import type { ReactNode } from 'react';

interface Props { children: ReactNode; }

// Compact keyboard-hint chip. Used inline in menus, palette hints, tooltips.
export function KBD({ children }: Props) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 18,
        height: 16,
        padding: '0 4px',
        fontFamily: 'var(--font-mono)',
        fontSize: 'var(--fs-chrome)',
        lineHeight: '12px',
        color: 'var(--text-muted)',
        background: 'var(--card)',
        border: '1px solid var(--border-solid)',
        borderRadius: 2,
        letterSpacing: 0
      }}
    >
      {children}
    </span>
  );
}
