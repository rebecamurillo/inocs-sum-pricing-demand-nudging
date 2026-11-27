import { NO_SHOWCASE_TEXT, SHOWCASE_ERROR_TEXT } from '../../domain/home-text';
import { useShowcase } from '../hooks/useShowcase';
import styles from './Home.module.css';

/**
 * Home's visual: a square tile on the map ground colour. No map is created in any state of this
 * version; the figure, its tag and the map arrive with the showcase's story.
 */
export function HomeVisual() {
  const showcase = useShowcase();
  let content = null;
  if (showcase.isPending) {
    content = (
      <div className={styles.skeleton} data-testid="home-skeleton" aria-busy="true">
        <i />
        <i />
      </div>
    );
  } else if (showcase.isError) {
    content = <p className={styles.tileText}>{SHOWCASE_ERROR_TEXT}</p>;
  } else if (showcase.data === null) {
    content = <p className={styles.tileText}>{NO_SHOWCASE_TEXT}</p>;
  }
  return (
    <div className={styles.visual} data-testid="home-visual">
      {content !== null && <div className={styles.tile}>{content}</div>}
    </div>
  );
}
