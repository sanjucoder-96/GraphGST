import { useMemo, useState } from 'react';
import type { PerEdge, Ring } from '../../types/domain';
import { Pill } from '../ui/Pill';
import { Button } from '../ui/Button';
import { useStore } from '../../lib/store';

interface Props {
  ring: Ring;
  onPreview?: (invoiceId: string | null) => void;
}

// Blend neutral → brand-blue by score_drop magnitude. Higher drop =
// more impactful cut = stronger brand emphasis. sRGB lerp, no dependency.
function edgeColor(drop: number): string {
  const t = Math.max(0, Math.min(1, drop / 0.35));
  const lo = [0x35, 0x43, 0x5a]; // line-3
  const hi = [0x4f, 0x80, 0xff]; // brand
  const rgb = lo.map((v, i) => Math.round(v + t * (hi[i]! - v)));
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

export function BreakSimulator({ ring, onPreview }: Props) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const pushToast = useStore(s => s.pushToast);

  const edges: PerEdge[] = useMemo(() => ring.per_edge ?? [], [ring]);
  const activeIdx = hoverIdx ?? selectedIdx ?? edges.findIndex(e => e.invoice_id === ring.break_edge?.invoice_id);

  const size = 200;
  const radius = 82;
  const stroke = 14;
  const cx = size / 2;
  const cy = size / 2;
  const n = edges.length;
  const gap = 0.028; // radians

  const preview = (i: number | null) => {
    if (i == null) { onPreview?.(null); return; }
    onPreview?.(edges[i]?.invoice_id ?? null);
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle cx={cx} cy={cy} r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
          {edges.map((e, i) => {
            const arc = (2 * Math.PI) / n - gap;
            const start = -Math.PI / 2 + i * (arc + gap);
            const end = start + arc;
            const x1 = cx + radius * Math.cos(start);
            const y1 = cy + radius * Math.sin(start);
            const x2 = cx + radius * Math.cos(end);
            const y2 = cy + radius * Math.sin(end);
            const isRec = ring.break_edge?.invoice_id === e.invoice_id;
            const isActive = activeIdx === i;
            return (
              <g key={e.invoice_id}>
                <path
                  d={`M ${x1} ${y1} A ${radius} ${radius} 0 0 1 ${x2} ${y2}`}
                  stroke={edgeColor(e.score_drop)}
                  strokeWidth={isActive ? stroke + 4 : stroke}
                  strokeLinecap="butt"
                  fill="none"
                  onMouseEnter={() => { setHoverIdx(i); preview(i); }}
                  onMouseLeave={() => { setHoverIdx(null); preview(null); }}
                  onClick={() => { const ni = selectedIdx === i ? null : i; setSelectedIdx(ni); preview(ni); pushToast({ kind: ni == null ? 'info' : 'ok', title: ni == null ? 'Cleared preview' : `Preview cut · Δ ${e.score_drop.toFixed(3)}`, body: e.invoice_id }); }}
                  style={{ cursor: 'pointer', transition: 'stroke-width 200ms ease-out' }}
                />
                {isRec && (
                  <circle
                    cx={cx + (radius + 20) * Math.cos((start + end) / 2)}
                    cy={cy + (radius + 20) * Math.sin((start + end) / 2)}
                    r={3}
                    fill="var(--signal)"
                  />
                )}
                {/* Score-drop inward bar */}
                <line
                  x1={cx + (radius - stroke) * Math.cos((start + end) / 2)}
                  y1={cy + (radius - stroke) * Math.sin((start + end) / 2)}
                  x2={cx + (radius - stroke - 30 * e.score_drop / 0.35) * Math.cos((start + end) / 2)}
                  y2={cy + (radius - stroke - 30 * e.score_drop / 0.35) * Math.sin((start + end) / 2)}
                  stroke={edgeColor(e.score_drop)}
                  strokeWidth={1.5}
                />
              </g>
            );
          })}
          <text x={cx} y={cy - 4} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={11} fill="var(--text-dim)" letterSpacing={0.5}>SCORE</text>
          <text x={cx} y={cy + 14} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={20} fontWeight={600} fill="var(--signal)">{ring.score.toFixed(3)}</text>
          <text x={cx} y={cy + 30} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={10} fill="var(--text-dim)" letterSpacing={0.5}>
            {activeIdx >= 0 && edges[activeIdx] ? `if cut: ${edges[activeIdx].score_after.toFixed(3)}` : ' '}
          </text>
        </svg>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'baseline' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-strong)', color: 'var(--text-strong)' }}>Counterfactual</span>
            {ring.break_edge && <Pill tone="signal" solid>Recommended cut</Pill>}
          </div>
          <div style={{ fontSize: 'var(--fs-body)', color: 'var(--text-muted)', marginBottom: 12 }}>
            {ring.break_edge?.rationale ?? 'Cutting the highlighted edge minimises evidence loss while breaking the cycle.'}
          </div>
          <div style={{
            border: '1px solid var(--border-solid)',
            borderRadius: 3,
            overflow: 'hidden'
          }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 60px 60px',
              gap: 0,
              padding: '4px 8px',
              background: 'rgba(255,255,255,0.02)',
              borderBottom: '1px solid var(--border-solid)',
              color: 'var(--text-dim)',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--fs-chrome)',
              letterSpacing: '0.08em',
              textTransform: 'uppercase'
            }}>
              <span>Invoice</span><span style={{textAlign:'right'}}>After</span><span style={{textAlign:'right'}}>Δ</span>
            </div>
            {edges.map((e, i) => (
              <div
                key={e.invoice_id}
                onMouseEnter={() => { setHoverIdx(i); preview(i); }}
                onMouseLeave={() => { setHoverIdx(null); preview(null); }}
                onClick={() => { const ni = selectedIdx === i ? null : i; setSelectedIdx(ni); preview(ni); }}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 60px 60px',
                  gap: 0,
                  padding: '4px 8px',
                  cursor: 'pointer',
                  color: 'var(--text)',
                  background: activeIdx === i ? 'var(--brand-dim)' : 'transparent',
                  borderBottom: '1px solid var(--border-solid)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--fs-body)'
                }}
              >
                <span>{e.invoice_id}</span>
                <span style={{ textAlign: 'right' }}>{e.score_after.toFixed(3)}</span>
                <span style={{ textAlign: 'right', color: edgeColor(e.score_drop) }}>−{e.score_drop.toFixed(3)}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <Button
              variant="signal"
              size="sm"
              disabled={!ring.break_edge}
              onClick={() => {
                if (!ring.break_edge) return;
                const idx = edges.findIndex(e => e.invoice_id === ring.break_edge!.invoice_id);
                setSelectedIdx(idx);
                preview(idx);
                pushToast({ kind: 'ok', title: 'Recommended cut applied', body: ring.break_edge.invoice_id });
              }}
            >
              Apply recommended
            </Button>
            <Button variant="ghost" size="sm" onClick={() => { setSelectedIdx(null); preview(null); }}>
              Clear preview
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
