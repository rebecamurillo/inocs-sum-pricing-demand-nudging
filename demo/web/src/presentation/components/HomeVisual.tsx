import {
  HOME_MAP_LEGEND,
  NO_SHOWCASE_TEXT,
  PROVISIONAL_LINE,
  SHOWCASE_ERROR_TEXT,
  showcaseFigure,
  showcaseLine,
  showcaseScope,
  showcaseSourceLine,
} from '../../domain/home-text';
import type { Showcase } from '../../domain/showcase';
import { useShowcase } from '../hooks/useShowcase';
import styles from './Home.module.css';
import { HomeMap } from './HomeMap';
import { SourceTag } from './SourceTag';

function StatTile({ showcase }: { readonly showcase: Showcase }) {
  const figure = showcaseFigure(showcase.carShareDifference.value);
  return (
    <div className={styles.stat} data-testid="home-tile">
      <p className={styles.figure} data-testid="home-figure">
        {String(figure)}
      </p>
      <p className={styles.statLine}>{showcaseLine(figure, showcase.flatPrice.value)}</p>
      <p className={styles.statSource}>
        <SourceTag kind="simulation" />{' '}
        {showcaseSourceLine(showcase.rule.current, showcase.rule.version)}
      </p>
      <p className={styles.statMeta}>
        {showcaseScope(
          showcase.city,
          showcase.radiusKm.value,
          showcase.periodLabel,
          showcase.letter,
          showcase.instanceVersionName,
        )}
      </p>
      <p className={styles.statMeta}>{PROVISIONAL_LINE}</p>
    </div>
  );
}

/**
 * Home's visual. With a showcase: the stat tile, then the non-interactive map of the priced
 * trips in the 5:4 box and its legend under the box. Without one, or while it loads: a tile
 * on the map ground colour that says so.
 */
export function HomeVisual() {
  const showcase = useShowcase();
  const data = showcase.data ?? null;
  if (data !== null) {
    return (
      <div className={styles.visualColumn}>
        <StatTile showcase={data} />
        <div className={styles.visual} data-testid="home-visual">
          <HomeMap showcase={data} />
        </div>
        <p className={styles.legend} data-testid="home-legend">
          {HOME_MAP_LEGEND}
        </p>
      </div>
    );
  }
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
  } else {
    content = <p className={styles.tileText}>{NO_SHOWCASE_TEXT}</p>;
  }
  return (
    <div className={styles.visual} data-testid="home-visual">
      <div className={styles.tile}>{content}</div>
    </div>
  );
}
