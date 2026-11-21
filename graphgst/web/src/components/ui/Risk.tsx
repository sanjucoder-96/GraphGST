import styles from './Risk.module.css';
import type { Band } from '../../types/case';

/* Canonical band thresholds — mirror backend risk/materialize.band_for
   (V6.4 recalibration: LOW<0.15, MED<0.30, HIGH<0.45, CRITICAL≥0.45).
   Used only when a row carries a score but no server-computed band. */
export function bandFor(score: number): Band {
  if (score >= 0.45) return 'CRITICAL';
  if (score >= 0.30) return 'HIGH';
  if (score >= 0.15) return 'MED';
  return 'LOW';
}

const BAND_CLASS: Record<Band, string> = {
  LOW: styles.low, MED: styles.med, HIGH: styles.high, CRITICAL: styles.crit,
};
const BAND_LABEL: Record<Band, string> = {
  LOW: 'Low', MED: 'Elevated', HIGH: 'High', CRITICAL: 'Critical',
};

/* The signature risk readout. A tabular-mono score in band color over a
   4-segment meter that fills to the band. One visual grammar for risk
   across every surface — queue rows, the case header, the inspector. */
export function RiskMeter({ score, band, size = 'md' }: {
  score: number; band?: Band | null; size?: 'sm' | 'md' | 'lg';
}) {
  const b = band ?? bandFor(score);
  const filled = b === 'LOW' ? 1 : b === 'MED' ? 2 : b === 'HIGH' ? 3 : 4;
  return (
    <div className={`${styles.meter} ${styles[size]} ${BAND_CLASS[b]}`}>
      <span className={styles.score} data-mono>{score.toFixed(3)}</span>
      <span className={styles.segs} aria-hidden>
        {[0, 1, 2, 3].map(i => (
          <span key={i} className={`${styles.seg} ${i < filled ? styles.on : ''}`} />
        ))}
      </span>
    </div>
  );
}

/* Compact band chip — a filled dot + label. Semantic color only. */
export function RiskBand({ band, score }: { band: Band; score?: number }) {
  return (
    <span className={`${styles.band} ${BAND_CLASS[band]}`}>
      <span className={styles.bandDot} />
      {BAND_LABEL[band]}
      {score != null && <span className={styles.bandScore} data-mono>{score.toFixed(2)}</span>}
    </span>
  );
}

/* Horizontal risk bar — continuous fill, for the case header / inspector. */
export function RiskBar({ score, band }: { score: number; band?: Band | null }) {
  const b = band ?? bandFor(score);
  return (
    <span className={`${styles.bar} ${BAND_CLASS[b]}`}>
      <span className={styles.barFill} style={{ width: `${Math.max(3, Math.min(100, score * 100))}%` }} />
    </span>
  );
}
