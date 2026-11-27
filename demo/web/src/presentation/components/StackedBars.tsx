import type { ReactNode } from 'react';
import { MODES, type ModeCounts } from '../../domain/pricing-result';
import { modeSummary, segmentShare } from '../../domain/result-text';
import styles from './StackedBars.module.css';

/** Segments narrower than this share of the scale carry no inner label (the legend still names them). */
const MIN_LABELLED_SHARE = 8;

/** The list that holds the bars of one scale. */
export function BarList({
  label,
  className,
  stale,
  children,
}: {
  readonly label: string;
  readonly className?: string;
  /** The bars are simulated with an older rule: dimmed to 60 %. */
  readonly stale?: boolean;
  readonly children: ReactNode;
}) {
  return (
    <ul
      className={[styles.bars, className].join(' ').trim()}
      aria-label={label}
      data-older-rule={stale === true ? '' : undefined}
    >
      {children}
    </ul>
  );
}

/**
 * One stacked bar on the scale `total`: three modes, each with its icon and share, never colour
 * alone. `summary` replaces the accessible summary of the counts (L-4 bars carry shares).
 */
export function StackedBar({
  label,
  counts,
  total,
  summary,
  stale,
}: {
  readonly label: string;
  readonly counts: ModeCounts;
  readonly total: number;
  readonly summary?: string;
  readonly stale?: boolean;
}) {
  return (
    <li data-older-rule={stale === true ? '' : undefined}>
      <span className={styles.barLabel}>{label}</span>
      <div
        className={styles.track}
        role="img"
        aria-label={`${label}: ${summary ?? modeSummary(counts)}`}
      >
        {MODES.map((mode) => {
          const count = counts[mode.key];
          const share = segmentShare(count, total);
          return (
            <span
              key={mode.key}
              className={styles.segment}
              data-mode={mode.key}
              style={{
                width: `${String(total <= 0 ? 0 : (100 * count) / total)}%`,
                background: mode.colour,
              }}
            >
              {share >= MIN_LABELLED_SHARE && (
                <span aria-hidden="true">
                  {mode.icon} {String(share)} %
                </span>
              )}
            </span>
          );
        })}
      </div>
    </li>
  );
}

export function Legend() {
  return (
    <ul className={styles.legend} aria-label="Modes">
      {MODES.map((mode) => (
        <li key={mode.key} className={styles.key}>
          <span className={styles.swatch} style={{ background: mode.colour }} aria-hidden="true" />
          <span aria-hidden="true">{mode.icon}</span>
          <span>{mode.label}</span>
        </li>
      ))}
    </ul>
  );
}
