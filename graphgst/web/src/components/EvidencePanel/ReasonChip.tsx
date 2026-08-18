interface Props {
  label: string;
  active?: boolean;
  onClick?: () => void;
}

export function ReasonChip({ label, active, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        height: 18,
        padding: '0 6px',
        borderRadius: 2,
        border: '1px solid',
        borderColor: active ? 'var(--signal-lo)' : 'var(--border-solid-2)',
        background: active ? 'var(--signal-veil)' : 'var(--card)',
        color: active ? 'var(--signal)' : 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        letterSpacing: '0.04em',
        cursor: onClick ? 'pointer' : 'default'
      }}
    >
      {label}
    </button>
  );
}
