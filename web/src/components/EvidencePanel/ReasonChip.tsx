interface Props {
  label: string;
  active?: boolean;
  exhibit?: string;
  onClick?: () => void;
}

/* Reason chip — click to cross-highlight its evidence in the graph. */
export function ReasonChip({ label, active, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 10px',
        borderRadius: 'var(--r-full)',
        border: '1px solid',
        borderColor: active ? 'var(--brand-line)' : 'var(--line-2)',
        background: active ? 'var(--brand-dim)' : 'var(--bg-3)',
        color: active ? 'var(--brand-2)' : 'var(--text-1)',
        fontSize: 'var(--fs-xs)',
        fontWeight: 450,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'border-color 120ms cubic-bezier(0.16,1,0.3,1), color 120ms cubic-bezier(0.16,1,0.3,1), background 120ms cubic-bezier(0.16,1,0.3,1)'
      }}
    >
      <span style={{
        width: 5, height: 5, borderRadius: '50%',
        background: active ? 'var(--brand)' : 'var(--text-3)',
        flexShrink: 0
      }} />
      {label}
    </button>
  );
}
