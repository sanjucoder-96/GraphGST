import type { SignalKey } from '../../types/domain';

interface Props {
  k: SignalKey;
  value: number;      // 0..1
  onClick?: () => void;
  active?: boolean;
  isMax?: boolean;    // brand emphasis on the dominant signal
}

const LABEL: Record<SignalKey, string> = {
  C: 'Closure',
  V: 'Value parity',
  T: 'Temporal',
  R: 'Recurrence',
  N: 'Network',
  H: 'Prior history'
};

/* One row of the risk decomposition. Full-width horizontal meter:
   label · track · value. The dominant signal is emphasised in brand;
   others use a neutral fill. Clicking filters the graph to that signal's
   evidence (handled by the parent). */
export function SignalGauge({ k, value, onClick, active, isMax }: Props) {
  const clamped = Math.max(0, Math.min(1, value));
  const pct = Math.round(clamped * 100);
  const fill = isMax ? 'var(--brand)' : 'var(--text-3)';

  return (
    <button
      type="button"
      onClick={onClick}
      title={`${LABEL[k]}: ${pct}%`}
      style={{
        display: 'grid',
        gridTemplateColumns: '96px 1fr 40px',
        alignItems: 'center',
        gap: 12,
        padding: '5px 8px',
        margin: '0 -8px',
        background: active ? 'var(--brand-dim)' : 'transparent',
        border: 0,
        borderRadius: 6,
        cursor: onClick ? 'pointer' : 'default',
        width: 'calc(100% + 16px)',
        transition: 'background 120ms cubic-bezier(0.16,1,0.3,1)'
      }}
    >
      <span style={{
        fontSize: 'var(--fs-sm)',
        color: isMax ? 'var(--text-0)' : 'var(--text-2)',
        fontWeight: isMax ? 500 : 450,
        textAlign: 'left',
        letterSpacing: '-0.01em'
      }}>{LABEL[k]}</span>

      <span style={{
        position: 'relative',
        height: 6,
        borderRadius: 3,
        background: 'var(--bg-4)',
        overflow: 'hidden',
        display: 'block'
      }}>
        <span style={{
          position: 'absolute',
          inset: 0,
          width: `${pct}%`,
          background: fill,
          borderRadius: 3,
          boxShadow: isMax ? '0 0 8px var(--brand-glow)' : 'none',
          transition: 'width 320ms cubic-bezier(0.16,1,0.3,1)'
        }} />
      </span>

      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 'var(--fs-num-sm)',
        color: isMax ? 'var(--brand-2)' : 'var(--text-2)',
        fontVariantNumeric: 'tabular-nums',
        textAlign: 'right',
        letterSpacing: '-0.03em'
      }}>{value.toFixed(2)}</span>
    </button>
  );
}
