import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useStore } from '../../lib/store';

// Toasts appear and dismiss WITHOUT animation. The design rationale
// enumerates four sanctioned motion moments — toast isn't one of them.
// A coloured 2px left border encodes kind; dismissal is on click or after 6s
// via the auto-expire timer set at push time in the store.

export function ToastStack() {
  const toasts = useStore(s => s.toasts);
  const dismiss = useStore(s => s.dismissToast);

  const colorFor = (k: string): string => {
    switch (k) {
      case 'ok':   return 'var(--ok)';
      case 'warn': return 'var(--signal)';
      case 'bad':  return 'var(--bad)';
      default:     return 'var(--info)';
    }
  };

  return createPortal(
    <div
      style={{
        position: 'fixed',
        right: 16,
        bottom: 32,
        display: 'flex',
        flexDirection: 'column-reverse',
        gap: 8,
        zIndex: 50,
        maxWidth: 340
      }}
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          style={{
            background: 'var(--card)',
            border: '1px solid var(--border-solid-2)',
            borderLeft: `2px solid ${colorFor(t.kind)}`,
            borderRadius: 3,
            padding: '8px 10px',
            boxShadow: 'var(--shadow-modal)',
            minWidth: 280
          }}
          onClick={() => dismiss(t.id)}
          role="status"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 'var(--fs-strong)', color: 'var(--text-strong)' }}>{t.title}</div>
              {t.body ? (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-chrome)', color: 'var(--text-dim)', marginTop: 2 }}>{t.body}</div>
              ) : null}
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); dismiss(t.id); }}
              style={{ background: 'transparent', border: 0, color: 'var(--text-dim)', cursor: 'pointer' }}
              aria-label="Dismiss"
            >
              <X size={12} strokeWidth={1.5} />
            </button>
          </div>
        </div>
      ))}
    </div>,
    document.body
  );
}
