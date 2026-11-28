/** The comparison table as a CSV file: built from the comparison already loaded, as the screen shows it. */
import { comparisonColumns, type Comparison } from './comparison';
import { flatColumnHeader, tableGroups, versionHeader } from './comparison-text';
import { SOURCE_LABELS } from './result-text';

const DASH = '—';

/** The goals of the header block: the key of a version's goals, the record's first field, its unit. */
const GOAL_RECORDS: readonly { key: string; label: string; chf: boolean }[] = [
  { key: 'cost_bike_chf', label: 'cost of one ride (CHF)', chf: true },
  { key: 'lowest_price_chf', label: 'lowest price of a ride (CHF)', chf: true },
  { key: 'ridership_weight', label: 'ridership weight', chf: false },
  { key: 'station_balance_weight', label: 'station balance weight', chf: false },
  { key: 'flat_price_per_ride_chf', label: 'flat price per ride (CHF)', chf: true },
  { key: 'pt_fare_chf', label: 'public transport fare (CHF)', chf: true },
  { key: 'car_parking_fee_chf', label: 'car parking fee (CHF)', chf: true },
  { key: 'max_displayed_options', label: 'options shown per hub pair', chf: false },
];

/** A field as RFC 4180 writes it: quoted, quotes doubled, when it holds a comma, a quote or a line break. */
function csvField(text: string): string {
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const record = (fields: readonly string[]): string => fields.map(csvField).join(',');

/** The file's text: a header block (versions, goals), an empty line, then the table with its `source` column. */
export function buildComparisonCsv(comparison: Comparison, advancedView: boolean): string {
  const { versions } = comparison;
  const same = (label: string, text: string): string =>
    record([label, ...versions.map(() => text)]);
  const goals = GOAL_RECORDS.map(({ key, label, chf }) =>
    record([
      label,
      ...versions.map((version) => {
        const goal = version.goals[key];
        if (goal === undefined) return DASH;
        return chf ? goal.value.toFixed(2) : String(goal.value);
      }),
    ]),
  );
  const columns = comparisonColumns(comparison);
  const head = record([
    'group',
    'row',
    ...columns.map((column) =>
      column.kind === 'flat'
        ? flatColumnHeader(column.reference, comparison.flatReferences)
        : versionHeader(column.version.letter, column.version.name),
    ),
    'source',
  ]);
  const rows = tableGroups(comparison, columns, advancedView).flatMap((group) =>
    group.rows.map((row) =>
      record([
        group.title,
        row.unit === null ? row.label : `${row.label} (${row.unit})`,
        ...row.cells.map((cell) => cell.csv),
        SOURCE_LABELS[row.source],
      ]),
    ),
  );
  const lines = [
    record(['version', ...versions.map((v) => versionHeader(v.letter, v.name))]),
    same(
      'instance version',
      `${comparison.instanceVersion.name} (${comparison.instanceVersion.id})`,
    ),
    same('period', comparison.period.name),
    ...goals,
    '',
    head,
    ...rows,
  ];
  return `${lines.join('\r\n')}\r\n`;
}

/** `comparison-{instance version}-{letters}.csv`. */
export function comparisonCsvFileName(comparison: Comparison): string {
  const letters = comparison.versions.map((version) => version.letter).join('');
  return `comparison-${comparison.instanceVersion.id}-${letters}.csv`;
}
