import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, ChevronsLeft, ChevronsRight, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Ring } from '../../types/domain';
import styles from './TimelineScrubber.module.css';

interface Props {
  ring: Ring;
  onDateChange: (isoDate: string | null) => void;
  initialDate?: string | null;
}

// Return unique sorted ISO dates covered by the ring's edges.
function ringDates(ring: Ring): string[] {
  const uniq = new Set<string>();
  for (const e of ring.edges) uniq.add(e.date);
  return [...uniq].sort();
}

export function TimelineScrubber({ ring, onDateChange, initialDate }: Props) {
  const dates = useMemo(() => ringDates(ring), [ring]);
  const [idx, setIdx] = useState<number>(() => {
    if (initialDate) {
      const i = dates.indexOf(initialDate);
      if (i >= 0) return i;
    }
    return Math.max(0, dates.length - 1);
  });
  const [playing, setPlaying] = useState(false);
  const stripRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (!stripRef.current) return;
    const el = stripRef.current;
    const ro = new ResizeObserver((entries) => {
      for (const ent of entries) setWidth(ent.contentRect.width);
    });
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    onDateChange(dates[idx] ?? null);
  }, [idx, dates, onDateChange]);

  // Play stepper — driven by real ticks, one date every 400ms
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setIdx((i) => {
        if (i + 1 >= dates.length) { setPlaying(false); return i; }
        return i + 1;
      });
    }, 400);
    return () => window.clearInterval(id);
  }, [playing, dates.length]);

  // Keyboard for timeline. Scoped: only fires when focus is inside the
  // container. The container is tabIndex=0 and captures its own keydown, so
  // Space/Arrows/Home/End on other buttons behave normally.
  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    // If focus moved to an inner control that itself uses Space/Arrows
    // (e.g. a select), do not hijack.
    const tgt = e.target as HTMLElement | null;
    if (tgt && tgt !== containerRef.current) {
      const tag = tgt.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'A') return;
    }
    if (e.key === ' ') { e.preventDefault(); setPlaying(p => !p); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); setIdx(i => Math.max(0, i - (e.shiftKey ? 7 : 1))); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); setIdx(i => Math.min(dates.length - 1, i + (e.shiftKey ? 7 : 1))); }
    else if (e.key === 'Home') { e.preventDefault(); setIdx(0); }
    else if (e.key === 'End') { e.preventDefault(); setIdx(dates.length - 1); }
  }, [dates.length]);

  const xFor = useCallback((i: number): number => {
    if (dates.length <= 1) return width / 2;
    return (i / (dates.length - 1)) * (width - 24) + 12;
  }, [dates, width]);

  const onStripClick = (evt: React.MouseEvent<HTMLDivElement>) => {
    const rect = evt.currentTarget.getBoundingClientRect();
    const x = evt.clientX - rect.left;
    let best = 0; let bestDist = Infinity;
    for (let i = 0; i < dates.length; i += 1) {
      const dx = Math.abs(x - xFor(i));
      if (dx < bestDist) { best = i; bestDist = dx; }
    }
    setIdx(best);
    // Bring focus into the container so the keys start responding without a tab.
    containerRef.current?.focus();
  };

  // Score-evolution sparkline data: use ring.sparkline if present, else linear
  const spark = ring.sparkline ?? Array.from({ length: dates.length }, (_, i) => (ring.score * (i + 1)) / dates.length);
  const sparkSlice = spark.slice(0, idx + 1);
  const currentScore = spark[idx] ?? ring.score;

  return (
    <div
      className={styles.wrap}
      ref={containerRef}
      tabIndex={0}
      role="group"
      aria-label="Timeline scrubber — press Space to play, arrows to step, Home/End for ends"
      onKeyDown={onKeyDown}
    >
      <div className={styles.header}>
        <div className={styles.controls}>
          <button type="button" onClick={() => setIdx(0)} title="First (Home)"><ChevronsLeft size={12} strokeWidth={1.5} /></button>
          <button type="button" onClick={() => setIdx(i => Math.max(0, i - 1))} title="Prev (Left)"><ChevronLeft size={12} strokeWidth={1.5} /></button>
          <button type="button" onClick={() => setPlaying(p => !p)} title="Play/Pause (Space)">
            {playing ? <Pause size={12} strokeWidth={1.5} /> : <Play size={12} strokeWidth={1.5} />}
          </button>
          <button type="button" onClick={() => setIdx(i => Math.min(dates.length - 1, i + 1))} title="Next (Right)"><ChevronRight size={12} strokeWidth={1.5} /></button>
          <button type="button" onClick={() => setIdx(dates.length - 1)} title="Last (End)"><ChevronsRight size={12} strokeWidth={1.5} /></button>
        </div>
        <span className={styles.date} data-mono>{dates[idx] ?? '—'}</span>
        <span className={styles.meta}>{idx + 1} / {dates.length}</span>
      </div>

      <div className={styles.sparkWrap}>
        <svg viewBox={`0 0 ${Math.max(1, width)} 24`} width="100%" height="24" preserveAspectRatio="none" aria-hidden>
          <path
            d={buildSparkPath(spark, Math.max(1, width), 24)}
            fill="none"
            stroke="#4a5058"
            strokeWidth={1.25}
          />
          <path
            d={buildSparkPath(sparkSlice, Math.max(1, width), 24, spark.length - 1)}
            fill="none"
            stroke="var(--signal)"
            strokeWidth={1.75}
          />
        </svg>
      </div>

      <div
        className={styles.strip}
        ref={stripRef}
        onClick={onStripClick}
      >
        {dates.map((d, i) => (
          <div key={d} className={styles.tick} style={{ left: xFor(i) - 1 }}>
            {i % Math.max(1, Math.ceil(dates.length / 6)) === 0 && (
              <div className={styles.tickLabel}>{d.slice(5)}</div>
            )}
          </div>
        ))}
        <div className={styles.playhead} style={{ left: xFor(idx) - 1 }} />
        <div className={styles.playheadDiamond} style={{ left: xFor(idx) }} />
      </div>

      <div className={styles.scoreLegend}>
        <span>score up to playhead</span>
        <span className={styles.cur} data-mono>{currentScore.toFixed(3)}</span>
        <span>final {ring.score.toFixed(3)}</span>
      </div>
    </div>
  );
}

function buildSparkPath(values: number[], w: number, h: number, totalLen?: number): string {
  const n = values.length;
  if (n === 0) return '';
  const total = totalLen ?? n - 1;
  const denom = Math.max(1, total);
  const min = 0;
  const max = 1;
  const y = (v: number) => h - ((v - min) / (max - min)) * (h - 2) - 1;
  const x = (i: number) => (i / denom) * (w - 16) + 8;
  let d = `M ${x(0)} ${y(values[0]!)}`;
  for (let i = 1; i < n; i += 1) d += ` L ${x(i)} ${y(values[i]!)}`;
  return d;
}
