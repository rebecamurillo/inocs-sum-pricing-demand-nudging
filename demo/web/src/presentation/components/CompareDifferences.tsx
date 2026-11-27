import { identicalPair, topPairDifferences, type Comparison } from '../../domain/comparison';
import {
  DIFFERENCES_CAPTION,
  differenceHeaders,
  differenceRow,
  differencesHeading,
  identicalResultSentence,
} from '../../domain/comparison-text';
import styles from './CompareDifferences.module.css';

interface CompareDifferencesProps {
  readonly comparison: Comparison;
  /** Hub id → "H4 Plainpalais"; a hub not listed shows its id. */
  readonly hubLabels: ReadonlyMap<string, string>;
  /** The key of the pair the map draws, or null. */
  readonly shownPair: string | null;
  readonly onShowOnMap: (key: string | null) => void;
}

/**
 * L-4's hub pairs where the mean bike price differs most between the last two compared versions, or,
 * when the two share one solve, the sentence that no hub pair price differs.
 */
export function CompareDifferences({
  comparison,
  hubLabels,
  shownPair,
  onShowOnMap,
}: CompareDifferencesProps) {
  const { a, b } = comparison.pairDifferences;
  const same = identicalPair(comparison);
  if (same?.coversAB === true) {
    const [x, y] = same.letters;
    return (
      <section className={styles.block} data-testid="compare-differences">
        <p className={styles.same}>{identicalResultSentence(x, y)}</p>
      </section>
    );
  }
  const headers = differenceHeaders(a, b);
  const rows = topPairDifferences(comparison).map((pair) => differenceRow(pair, hubLabels));
  return (
    <section className={styles.block} data-testid="compare-differences">
      <h3 className={styles.heading}>{differencesHeading(a, b)}</h3>
      <div
        className={styles.wrapper}
        role="region"
        aria-label="Hub pairs by price difference"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be reachable by keyboard
        tabIndex={0}
      >
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">{headers.fromTo}</th>
              <th scope="col">{headers.priceA}</th>
              <th scope="col">{headers.priceB}</th>
              <th scope="col">{headers.difference}</th>
              <th scope="col">{headers.travellers}</th>
              <th scope="col">
                <span className={styles.hidden}>Map</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td>{row.fromTo}</td>
                <td className={styles.number}>{row.priceA}</td>
                <td className={styles.number}>{row.priceB}</td>
                <td className={styles.number}>{row.difference}</td>
                <td className={styles.number}>{row.travellers}</td>
                <td>
                  <button
                    type="button"
                    className={styles.showOnMap}
                    aria-pressed={shownPair === row.key}
                    onClick={() => {
                      onShowOnMap(shownPair === row.key ? null : row.key);
                    }}
                  >
                    Show on map
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.caption}>{DIFFERENCES_CAPTION}</p>
    </section>
  );
}
