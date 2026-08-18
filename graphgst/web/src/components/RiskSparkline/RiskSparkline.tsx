interface Props {
  data: number[];
  width?: number;
  height?: number;
  min?: number;
  max?: number;
}

export function RiskSparkline({ data, width = 64, height = 16, min = 0, max = 1 }: Props) {
  if (!data || data.length === 0) return <svg width={width} height={height} />;
  const n = data.length;
  const dx = (width - 2) / Math.max(1, n - 1);
  const y = (v: number): number => {
    const t = (v - min) / Math.max(1e-9, max - min);
    return height - t * (height - 2) - 1;
  };
  let d = `M 1 ${y(data[0]!).toFixed(2)}`;
  for (let i = 1; i < n; i += 1) d += ` L ${(1 + i * dx).toFixed(2)} ${y(data[i]!).toFixed(2)}`;
  const last = data[n - 1] ?? 0;
  const stroke = last >= 0.65 ? 'var(--signal)' : last >= 0.4 ? 'var(--warn)' : 'var(--info)';
  const endX = 1 + (n - 1) * dx;
  const endY = y(last);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.2} />
      <circle cx={endX} cy={endY} r={1.5} fill={stroke} />
    </svg>
  );
}
