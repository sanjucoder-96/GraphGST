import { createPortal } from 'react-dom';
import { X, CheckCircle2, AlertTriangle, Info, XCircle } from 'lucide-react';
import { useStore } from '../../lib/store';

/* Modern toast — icon + title + optional mono body. Coloured accent by
   kind. Dismiss on click or after 6s (timer set at push time). */

export function ToastStack() {
  const toasts = useStore(s => s.toasts);
  const dismiss = useStore(s => s.dismissToast);

  const meta = (k: string) => {
    switch (k) {
      case 'ok':   return { color: 'var(--ok)',   icon: <CheckCircle2 size={15} strokeWidth={2} /> };
      case 'warn': return { color: 'var(--warn)', icon: <AlertTriangle size={15} strokeWidth={2} /> };
      case 'bad':  return { color: 'var(--bad)',  icon: <XCircle size={15} strokeWidth={2} /> };
      default:     return { color: 'var(--brand-2)', icon: <Info size={15} strokeWidth={2} /> };
    }
  };

  return createPortal(
    <div
      style={{
        position: 'fixed',
        right: 20,
        bottom: 40,
        display: 'flex',
        flexDirection: 'column-reverse',
        gap: 10,
        zIndex: 50,
        maxWidth: 380
      }}
    >
      {toasts.map((t) => {
        const m = meta(t.kind);
        return (
          <div
            key={t.id}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              background: 'var(--bg-3)',
              border: '1px solid var(--line-2)',
              borderRadius: 'var(--r-lg)',
              padding: '12px 14px',
              boxShadow: 'var(--shadow-lg)',
              minWidth: 300
            }}
            onClick={() => dismiss(t.id)}
            role="status"
          >
            <span style={{ color: m.color, marginTop: 1, flexShrink: 0 }}>{m.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 'var(--fs-base)',
                fontWeight: 500,
                color: 'var(--text-0)',
                letterSpacing: '-0.01em'
              }}>{t.title}</div>
              {t.body ? (
                <div style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--fs-2xs)',
                  color: 'var(--text-3)',
                  marginTop: 3
                }}>{t.body}</div>
              ) : null}
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); dismiss(t.id); }}
              style={{ background: 'transparent', border: 0, color: 'var(--text-3)', cursor: 'pointer', padding: 2, flexShrink: 0 }}
              aria-label="Dismiss"
            >
              <X size={13} strokeWidth={2} />
            </button>
          </div>
        );
      })}
    </div>,
    document.body
  );
}
