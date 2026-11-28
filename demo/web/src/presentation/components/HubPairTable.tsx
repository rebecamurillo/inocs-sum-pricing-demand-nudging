import { Fragment, useMemo, useState } from 'react';
import {
  COLUMN_HEADINGS,
  PRICE_CAPTION,
  RANGE_LABEL,
  SORT_COLUMNS,
  formatMinutes,
  formatPrice,
  formatRiders,
  hubPairRow,
  nextSort,
  offeredOptions,
  optionName,
  sortRows,
  type SortColumn,
  type SortState,
} from '../../domain/hub-pair-table';
import type { HubPairResult } from '../../domain/pricing-result';
import { COMPUTED_LABEL } from '../../domain/result-text';
import styles from './HubPairTable.module.css';
import { SourceTag } from './SourceTag';

interface HubPairTableProps {
  readonly results: readonly HubPairResult[];
  /** Hub id → "H4 Plainpalais"; a hub not listed shows its id. */
  readonly hubLabels: ReadonlyMap<string, string>;
  /** The key of the pair the map draws, or null. */
  readonly shownPair: string | null;
  readonly onShowOnMap: (key: string | null) => void;
}

const COLUMN_COUNT = SORT_COLUMNS.length + 1;
const TRAVELLER_COLUMNS: readonly SortColumn[] = ['car', 'pt', 'ptBike'];
const ARIA_SORT = { asc: 'ascending', desc: 'descending' } as const;

/** L-3's table of every hub pair: price and flow, sortable, with a row's offered options under it. */
export function HubPairTable({ results, hubLabels, shownPair, onShowOnMap }: HubPairTableProps) {
  const [sort, setSort] = useState<SortState | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const rows = useMemo(() => {
    const built = results.map((result) => hubPairRow(result, hubLabels));
    return sort === null ? built : sortRows(built, sort.column, sort.direction);
  }, [results, hubLabels, sort]);

  return (
    <div className={styles.block}>
      <p className={styles.caption}>{PRICE_CAPTION}</p>
      <p className={styles.small}>{COMPUTED_LABEL}</p>
      <div className={styles.wrapper}>
        <table className={styles.table} aria-label="Price and flow per hub pair">
          <thead>
            <tr>
              <td colSpan={SORT_COLUMNS.length - TRAVELLER_COLUMNS.length} />
              <th scope="colgroup" colSpan={TRAVELLER_COLUMNS.length} className={styles.group}>
                Travellers per mode <SourceTag kind="model" />
              </th>
              <td />
            </tr>
            <tr>
              {SORT_COLUMNS.map((column) => (
                <th
                  key={column}
                  scope="col"
                  aria-sort={
                    sort !== null && sort.column === column ? ARIA_SORT[sort.direction] : 'none'
                  }
                  data-column={column}
                >
                  <button
                    type="button"
                    className={styles.sortButton}
                    onClick={() => {
                      setSort((current) => nextSort(current, column));
                    }}
                  >
                    {COLUMN_HEADINGS[column]}
                  </button>
                  {column === 'price' && <span className={styles.small}>{RANGE_LABEL}</span>}
                </th>
              ))}
              <th scope="col">
                <span className={styles.hidden}>Map</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const options = offeredOptions(row.result);
              const expandable = options.length > 0;
              const expanded = expandable && open === row.key;
              const toggle = () => {
                if (!expandable) return;
                setOpen((current) => (current === row.key ? null : row.key));
              };
              return (
                <Fragment key={row.key}>
                  <tr
                    className={styles.row}
                    data-state={row.state}
                    data-expandable={expandable}
                    tabIndex={expandable ? 0 : undefined}
                    aria-expanded={expandable ? expanded : undefined}
                    onClick={toggle}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget) return;
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        toggle();
                      }
                    }}
                  >
                    <td>{row.fromTo}</td>
                    <td data-state={row.state}>
                      <span className={styles.price}>{row.price}</span>
                      {row.range !== null && <span className={styles.small}>{row.range}</span>}
                    </td>
                    <td className={styles.number}>{row.bikeOptions}</td>
                    <td className={styles.number}>{row.car}</td>
                    <td className={styles.number}>{row.pt}</td>
                    <td className={styles.number}>{row.ptBike}</td>
                    <td>
                      <button
                        type="button"
                        className={styles.showOnMap}
                        aria-pressed={shownPair === row.key}
                        onClick={(event) => {
                          event.stopPropagation();
                          onShowOnMap(shownPair === row.key ? null : row.key);
                        }}
                      >
                        Show on map
                      </button>
                    </td>
                  </tr>
                  {expanded && (
                    <tr className={styles.options}>
                      <td colSpan={COLUMN_COUNT}>
                        <table className={styles.inner} aria-label="Offered bike options">
                          <thead>
                            <tr>
                              <th scope="col">Option, by its legs</th>
                              <th scope="col">Duration</th>
                              <th scope="col">Bike legs</th>
                              <th scope="col">
                                Price, CHF <SourceTag kind="model" />
                              </th>
                              <th scope="col">Riders in the model</th>
                            </tr>
                          </thead>
                          <tbody>
                            {options.map((option) => (
                              <tr key={option.arcId}>
                                <td>{optionName(option.legs)}</td>
                                <td>{formatMinutes(option.duration.value)}</td>
                                <td className={styles.number}>
                                  {option.bikeLegs === null ? '' : option.bikeLegs.value}
                                </td>
                                <td className={styles.number}>
                                  {option.bikePrice === null
                                    ? ''
                                    : formatPrice(option.bikePrice.value)}
                                </td>
                                <td className={styles.number}>
                                  {option.riders === null ? '' : formatRiders(option.riders.value)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
