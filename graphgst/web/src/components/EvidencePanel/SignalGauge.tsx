import type { SignalKey } from '../../types/domain';

interface Props {
  k: SignalKey;
  value: number;      // 0..1
  onClick?: () => void;
  active?: boolean;
  isMax?: boolean;    // amber notch reserved for the highest-value signal
}

const LABEL: Record<SignalKey, string> = {
  C: 'Closure',
  V: 'Value',
  T: 'Temporal',
  R: 'Recurrence',
  N: 'Network',
  H: 'Prior'
};

// Signal strength is encoded by BAR LENGTH, not hue. This keeps the six
// signals reading as a compact meter row instead of a rainbow of donuts,
// and stays inside the amber budget: the single highest-value signal in
// the row gets a 2px amber notch at its right edge — nothing else does.
export function SignalGauge({ k, value, onClick, active, isMax }: Props) {
  const clamped = Math.max(0, Math.min(1, value));
  const width = 44; // matches meter width in px
  const filled = Math.round(clamped * width);

  return (
    <button
      type="button"
      onClick={onClick}
      title={`${LABEL[k]}: ${(value * 100).toFixed(1)}%`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 4,
        padding: 6,
        background: active ? 'var(--card)' : 'transparent',
        border: '1px solid',
        borderColor: active ? 'var(--border-solid-2)' : 'transparent',
        borderRadius: 2,
        cursor: onClick ? 'pointer' : 'default',
        width: '100%'
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        width: '100%',
        gap: 6
      }}>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          fontWeight: 500,
          color: 'var(--text-strong)',
          letterSpacing: '0.04em'
        }}>{k}</span>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text-dim)',
          fontVariantNumeric: 'tabular-nums'
        }}>{value.toFixed(2)}</span>
      </div>
      <svg width={width + 2} height={14} viewBox={`0 0 ${width + 2} 14`} aria-hidden style={{ display: 'block' }}>
        {/* Track */}
        <rect x={0} y={6} width={width} height={2} rx={1} fill="rgba(255,255,255,0.10)" />
        {/* Meter */}
        <rect x={0} y={6} width={filled} height={2} rx={1} fill="var(--text-muted)" />
        {/* Amber notch — only for the highest-value signal in the row */}
        {isMax && (
          <rect x={Math.max(0, filled - 2)} y={2} width={2} height={10} fill="var(--signal)" />
        )}
      </svg>
    </button>
  );
}
