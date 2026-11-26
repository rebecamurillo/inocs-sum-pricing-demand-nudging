import type { ReactNode } from 'react';
import styles from './LoadingCard.module.css';

/**
 * The card while its content loads. First load: the skeleton alone. Reload after a render: the
 * previous render stays at 50 % opacity with the skeleton over it.
 */
export function LoadingCard({ previous }: { previous?: ReactNode }) {
  const skeleton = (
    <div role="status" aria-label="Loading" className={styles.skeleton}>
      <span className={styles.line} />
      <span className={styles.line} />
      <span className={styles.shortLine} />
    </div>
  );

  if (previous === undefined) return <div className={styles.card}>{skeleton}</div>;

  return (
    <div className={styles.card}>
      <div className={styles.previous} aria-hidden="true" data-testid="previous-render">
        {previous}
      </div>
      <div className={styles.over}>{skeleton}</div>
    </div>
  );
}
