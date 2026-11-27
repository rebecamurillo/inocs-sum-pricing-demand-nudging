/** Every wording of L-4 (compare versions), verbatim from UX-SPEC.md § L-4, and the table behind it. */
import {
  identicalPair,
  olderRuleOf,
  type Comparison,
  type ComparisonColumn,
  type ComparisonGroup,
  type ComparisonRow,
  type FlatReference,
  type GroupName,
  type HubDifference,
  type PairDifference,
} from './comparison';
import { COLUMN_HEADINGS } from './hub-pair-table';
import { groupThousands } from './l1-text';
import { solverStatusText } from './advanced-text';
import { MODES, type ModeCounts, type ResultNumber } from './pricing-result';
import {
  COMPUTED_LABEL,
  MODEL_TAG,
  SIMULATION_SOURCE,
  SIMULATION_TAG,
  THREE_MODES_SENTENCE,
  formatAmount,
  formatChange,
  toChangeUnits,
} from './result-text';

export const COMPARE_BRIEF = 'Versions of one city instance, side by side';
export const COMPARE_VERSIONS = 'Compare versions →';
export const COMPARE_MENU = 'Compare versions';
export const compareBreadcrumb = (instanceName: string, number: number): string =>
  `${instanceName} v${String(number)} › ${COMPARE_MENU}`;
export const COMPARE_OFF = 'Compare needs two pricing versions of this city instance.';
export const TABLE_CAPTION =
  'Small figures: change against the flat-price column the version is simulated with. The pricing model is not run with a flat price: its rows show — there.';
export const SAME_BASIS_NOTE = 'same hubs, routes, travellers and bikes.';
export const BARS_CAPTION_END = THREE_MODES_SENTENCE;
export const BARS_TITLE = 'Simulated split of the travellers';
export { SIMULATION_SOURCE, SIMULATION_TAG, MODEL_TAG };
const DASH = '—';

export const GROUP_TITLES: Readonly<Record<GroupName, string>> = {
  simulated: 'Simulated travellers',
  model: "Pricing model's result",
  derived: "Computed from the model's flows",
  goals_that_differ: 'Pricing goals that differ',
  solver: 'What the solver maximised and how it ran',
};

export function pillLabel(letter: string, name: string, ticked: boolean): string {
  return `${ticked ? '✓ ' : ''}${letter} · ${name}`;
}

export const versionHeader = (letter: string, name: string): string =>
  `Version ${letter} · ${name}`;

export const flatPill = (reference: Pick<FlatReference, 'flatPrice'>): string =>
  `Flat price ${formatAmount(reference.flatPrice, 2)} CHF · simulated · always shown`;

const differs = (values: readonly number[]): boolean => new Set(values).size > 1;

/** "Flat price 1.00 CHF", with what differs from another flat column and the letters it serves. */
export function flatColumnHeader(reference: FlatReference, all: readonly FlatReference[]): string {
  const parts = [`Flat price ${formatAmount(reference.flatPrice, 2)} CHF`];
  if (all.length > 1) {
    if (differs(all.map((item) => item.fare)))
      parts.push(`fare ${formatAmount(reference.fare, 2)}`);
    if (differs(all.map((item) => item.parkingFee))) {
      parts.push(`parking fee ${formatAmount(reference.parkingFee, 2)}`);
    }
    if (differs(all.map((item) => item.costBike))) {
      parts.push(`cost ${formatAmount(reference.costBike, 2)}`);
    }
    parts.push(`for ${reference.letters.join(', ')}`);
  }
  return parts.join(' · ');
}

export const compareScopeLine = (instanceLabel: string, periodLabel: string): string =>
  `${instanceLabel} · ${periodLabel}`;

function joinAnd(items: readonly string[]): string {
  const last = items[items.length - 1] ?? '';
  return items.length <= 1 ? last : `${items.slice(0, -1).join(', ')} and ${last}`;
}

export function buildsNotice(commits: readonly string[]): string {
  return `These versions were run with different builds of the pricing model (package commits ${joinAnd(commits)}): a difference can come from the model's code, not only from the goals.`;
}

export function olderRuleNotice(letter: string, ruleVersion: number): string {
  return `Version ${letter} was simulated with an older rule (v${String(ruleVersion)}): its simulated numbers are greyed. Simulate it again to compare like with like.`;
}

export const simulateLetterAgain = (letter: string): string => `Simulate ${letter} again`;

export const olderRuleSuffix = (ruleVersion: number): string =>
  ` · older rule (v${String(ruleVersion)})`;

/** "1 pt", "−3 pts", "±0 pts": a change in percentage points. */
export function changePoints(points: number): string {
  return `${formatChange(points, 0)} ${Math.abs(points) === 1 ? 'pt' : 'pts'}`;
}

// ---- the insight title ----------------------------------------------------------------------

const CLAUSES: readonly {
  readonly row: string;
  readonly direction: 'lowest' | 'highest';
  readonly text: string;
}[] = [
  { row: 'share_car', direction: 'lowest', text: 'the lowest car share' },
  { row: 'profit', direction: 'highest', text: 'the highest profit' },
  { row: 'stations_empty_or_full', direction: 'lowest', text: 'the fewest stations empty or full' },
];

const TOLERANCE = 1e-9;
const close = (a: number, b: number): boolean =>
  Math.abs(a - b) <= TOLERANCE * Math.max(1, Math.abs(a), Math.abs(b));

function winners(
  row: ComparisonRow | undefined,
  direction: 'lowest' | 'highest',
): readonly string[] {
  if (row === undefined) return [];
  const found = Object.entries(row.values).flatMap(([letter, item]) =>
    item === null ? [] : [[letter, item.value] as const],
  );
  if (found.length < 2) return [];
  const values = found.map(([, value]) => value);
  const best = direction === 'lowest' ? Math.min(...values) : Math.max(...values);
  if (values.every((value) => close(value, best))) return [];
  return found.filter(([, value]) => close(value, best)).map(([letter]) => letter);
}

const MINUS = '\u2212';

/** "Versions B and D have the same prices; against a flat price of 1.50 instead of 1.00, their simulated car share is 6 pts lower instead of 4". */
export function identicalInsightTitle(comparison: Comparison, x: string, y: string): string {
  const flatOf = (letter: string): number | null => {
    const reference = comparison.versions.find((item) => item.letter === letter)?.flatReference;
    return comparison.flatReferences.find((item) => item.id === reference)?.flatPrice ?? null;
  };
  const changeOf = (letter: string): number | null => {
    const row = comparison.groups
      .find((group) => group.name === 'simulated')
      ?.rows.find((item) => item.key === 'share_car');
    const change = row?.changes[letter] ?? null;
    // Rounded as the table's change cell rounds it, so the title and the cell read the same points.
    return change === null ? null : toChangeUnits(change.value, 0);
  };
  const price = (letter: string): string => formatAmount(flatOf(letter) ?? 0, 2);
  const head = `Versions ${x} and ${y} have the same prices; against a flat price of ${price(y)} instead of ${price(x)}`;
  const first = changeOf(x);
  const second = changeOf(y);
  if (first === null || second === null) return head;
  const direction = (points: number): string => (points < 0 ? 'lower' : 'higher');
  const pts = Math.abs(second);
  const earlier =
    direction(first) === direction(second)
      ? String(Math.abs(first))
      : `${String(Math.abs(first))} ${direction(first)}`;
  return `${head}, their simulated car share is ${String(pts)} ${pts === 1 ? 'pt' : 'pts'} ${direction(second)} instead of ${earlier}`;
}

/** "In the simulation, Version B has the lowest car share; Version C has the highest profit and …". */
export function insightTitle(comparison: Comparison): string {
  const identical = identicalPair(comparison);
  if (identical !== null) return identicalInsightTitle(comparison, ...identical.letters);
  const simulated = comparison.groups.find((group) => group.name === 'simulated');
  const subjects: { letters: readonly string[]; texts: string[] }[] = [];
  for (const clause of CLAUSES) {
    const letters = winners(
      simulated?.rows.find((row) => row.key === clause.row),
      clause.direction,
    );
    if (letters.length === 0) continue;
    const same = subjects.find((item) => item.letters.join() === letters.join());
    if (same === undefined) subjects.push({ letters, texts: [clause.text] });
    else same.texts.push(clause.text);
  }
  if (subjects.length === 0) {
    return 'In the simulation, the versions are level on car share, profit and stations empty or full';
  }
  const sentences = subjects.map(({ letters, texts }) => {
    const who =
      letters.length === 1 ? `Version ${letters.join()} has` : `Versions ${joinAnd(letters)} have`;
    return `${who} ${joinAnd(texts)}`;
  });
  return `In the simulation, ${sentences.join('; ')}`;
}

// ---- the bars -------------------------------------------------------------------------------

/** The simulated shares (0 to 1) of a column's three modes; null when the column has none. */
export function columnShares(comparison: Comparison, column: ComparisonColumn): ModeCounts | null {
  const simulated = comparison.groups.find((group) => group.name === 'simulated');
  const keys = { car: 'share_car', ptOnly: 'share_pt_only', ptBike: 'share_pt_bike' } as const;
  const found: Partial<Record<keyof typeof keys, number>> = {};
  for (const [mode, key] of Object.entries(keys) as [keyof typeof keys, string][]) {
    const row = simulated?.rows.find((item) => item.key === key);
    const cell =
      row === undefined
        ? null
        : column.kind === 'flat'
          ? (row.flats[column.reference.id] ?? null)
          : (row.values[column.version.letter] ?? null);
    if (cell === null) return null;
    found[mode] = cell.value;
  }
  return { car: found.car ?? 0, ptOnly: found.ptOnly ?? 0, ptBike: found.ptBike ?? 0 };
}

/** The bar's accessible name: the three modes with their shares. */
export function sharesSummary(shares: ModeCounts): string {
  return MODES.map((mode) => `${mode.label} ${String(Math.round(100 * shares[mode.key]))} %`).join(
    ', ',
  );
}

export function columnLabel(column: ComparisonColumn, all: readonly FlatReference[]): string {
  return column.kind === 'flat'
    ? flatColumnHeader(column.reference, all)
    : versionHeader(column.version.letter, column.version.name);
}

// ---- the table ------------------------------------------------------------------------------

export interface TableCell {
  readonly text: string;
  /** The small figure: the change against the version's flat column. */
  readonly change: string | null;
  readonly best: boolean;
  readonly bold: boolean;
  /** Drawn at 60 % opacity: a simulated figure of an older rule. */
  readonly stale: boolean;
}

export interface TableRow {
  readonly key: string;
  readonly label: string;
  readonly note: string | null;
  readonly tag: 'model' | null;
  readonly cells: readonly TableCell[];
}

export interface TableGroup {
  readonly name: GroupName;
  readonly title: string;
  readonly tag: 'simulation' | 'model' | null;
  readonly source: string | null;
  readonly rows: readonly TableRow[];
}

const ROW_LABELS: Readonly<Record<string, string>> = {
  share_car: 'Car',
  share_pt_only: 'Public transport',
  share_pt_bike: 'Public transport + shared bike',
  ridership: 'Ridership',
  profit: 'Profit',
  revenue: 'Revenue',
  cost: 'Cost',
  mean_bike_price: 'Mean price paid per bike ride',
  stations_empty_or_full: 'Stations empty or full at 09:00',
  displaced: 'Travellers who did not get their first choice',
  bike_price_range: 'Range of the prices offered',
  rides_under_cost: 'Rides under the cost',
  cost_bike_chf: 'Cost of one ride',
  lowest_price_chf: 'Lowest price of a ride',
  ridership_weight: 'Ridership weight',
  station_balance_weight: 'Station balance weight',
  flat_price_per_ride_chf: 'Flat price per ride',
  objective_term_ridership: 'Ridership term',
  objective_term_revenue: '+ Revenue',
  objective_term_cost: '− Cost',
  objective_term_station_balance: '+ Station balance term',
  objective_value: '= Objective value',
  solution_time_s: 'Solution time',
  gap_pct: 'Optimality gap',
  solver_status: 'Status',
  hub_pairs_with_bike_option: 'Hub pairs · bike options offered',
};

const SHARE_KEYS = ['share_car', 'share_pt_only', 'share_pt_bike'];
const CHF_ROWS = ['profit', 'revenue', 'cost', 'bike_price_min', 'bike_price_max'];

function digitsOf(key: string): number {
  return key === 'mean_bike_price' ? 2 : 0;
}

function formatValue(key: string, item: ResultNumber): string {
  if (SHARE_KEYS.includes(key) || item.unit === 'share') {
    return `${formatAmount(100 * item.value, 0)} %`;
  }
  switch (key) {
    case 'mean_bike_price':
      return `${formatAmount(item.value, 2)} CHF`;
    case 'cost_bike_chf':
    case 'lowest_price_chf':
    case 'flat_price_per_ride_chf':
      return `${formatAmount(item.value, 2)} CHF`;
    case 'ridership_weight':
    case 'station_balance_weight':
      return String(item.value);
    case 'solution_time_s':
      return `${item.value.toFixed(1)} s`;
    case 'gap_pct':
      return `${item.value.toFixed(2)} %`;
    case 'solver_status':
      return solverStatusText(statusName(item.value));
    default:
      return CHF_ROWS.includes(key)
        ? `${formatAmount(item.value, 0)} CHF`
        : formatAmount(item.value, 0);
  }
}

/** Gurobi's status codes, named as the API names them (`solve_reading.STATUS_NAMES`); 0 is unknown. */
const STATUS_NAMES: readonly string[] = [
  'UNKNOWN',
  'LOADED',
  'OPTIMAL',
  'INFEASIBLE',
  'INF_OR_UNBD',
  'UNBOUNDED',
  'CUTOFF',
  'ITERATION_LIMIT',
  'NODE_LIMIT',
  'TIME_LIMIT',
  'SOLUTION_LIMIT',
  'INTERRUPTED',
  'NUMERIC',
  'SUBOPTIMAL',
  'INPROGRESS',
  'USER_OBJ_LIMIT',
  'WORK_LIMIT',
  'MEM_LIMIT',
];

function statusName(code: number): string {
  return STATUS_NAMES[code] ?? 'UNKNOWN';
}

function formatChangeCell(key: string, change: ResultNumber | null): string | null {
  if (change === null) return null;
  if (SHARE_KEYS.includes(key)) return changePoints(toChangeUnits(change.value, 0));
  const digits = digitsOf(key);
  return formatChange(toChangeUnits(change.value, digits), digits);
}

const NO_CELL: TableCell = { text: DASH, change: null, best: false, bold: false, stale: false };

/** The values of a row that differ from the most common one: all of them when none is more common. */
function differingLetters(row: ComparisonRow): ReadonlySet<string> {
  const entries = Object.entries(row.values).flatMap(([letter, item]) =>
    item === null ? [] : [[letter, item.value] as const],
  );
  const counts = new Map<number, number>();
  for (const [, value] of entries) counts.set(value, (counts.get(value) ?? 0) + 1);
  const top = Math.max(0, ...counts.values());
  const common = [...counts].filter(([, count]) => count === top);
  const mode = common.length === 1 ? common[0]?.[0] : undefined;
  return new Set(entries.filter(([, value]) => value !== mode).map(([letter]) => letter));
}

function cellsOf(
  group: ComparisonGroup,
  row: ComparisonRow,
  columns: readonly ComparisonColumn[],
  comparison: Comparison,
  render: (item: ResultNumber | null) => string,
): TableCell[] {
  const bold = group.name === 'goals_that_differ' ? differingLetters(row) : new Set<string>();
  return columns.map((column) => {
    if (column.kind === 'flat') {
      if (group.name !== 'simulated') return NO_CELL;
      const item = row.flats[column.reference.id] ?? null;
      return { ...NO_CELL, text: render(item), stale: !column.reference.ruleCurrent };
    }
    const { letter } = column.version;
    const version = comparison.versions.find((item) => item.letter === letter);
    const stale =
      group.name === 'simulated' && version !== undefined && olderRuleOf(version) !== null;
    return {
      text: render(row.values[letter] ?? null),
      change:
        group.name === 'simulated' ? formatChangeCell(row.key, row.changes[letter] ?? null) : null,
      best: row.best.includes(letter),
      bold: bold.has(letter),
      stale,
    };
  });
}

function rowOf(
  group: ComparisonGroup,
  row: ComparisonRow,
  columns: readonly ComparisonColumn[],
  comparison: Comparison,
): TableRow {
  const noteFor =
    row.key === 'stations_empty_or_full' && group.name === 'derived'
      ? 'provisional'
      : row.key === 'objective_term_station_balance'
        ? COMPUTED_LABEL
        : null;
  return {
    key: row.key,
    label:
      group.name === 'derived' && row.key === 'mean_bike_price'
        ? 'Mean bike price'
        : (ROW_LABELS[row.key] ?? row.key),
    note: noteFor,
    tag: row.key === 'objective_value' ? 'model' : null,
    cells: cellsOf(group, row, columns, comparison, (item) =>
      item === null ? DASH : formatValue(row.key, item),
    ),
  };
}

/** The price range row joins the two price rows of the model group. */
function rangeRow(group: ComparisonGroup, columns: readonly ComparisonColumn[]): TableRow | null {
  const low = group.rows.find((row) => row.key === 'bike_price_min');
  const high = group.rows.find((row) => row.key === 'bike_price_max');
  if (low === undefined || high === undefined) return null;
  const cells = columns.map((column): TableCell => {
    if (column.kind === 'flat') return NO_CELL;
    const min = low.values[column.version.letter] ?? null;
    const max = high.values[column.version.letter] ?? null;
    const text =
      min === null || max === null
        ? DASH
        : `${formatAmount(min.value, 2)} – ${formatAmount(max.value, 2)} CHF`;
    return { ...NO_CELL, text };
  });
  return {
    key: 'bike_price_range',
    label: ROW_LABELS.bike_price_range ?? '',
    note: null,
    tag: null,
    cells,
  };
}

/** The solver's two last rows read as one: "{hub pairs} · {bike options}". */
function pairsRow(group: ComparisonGroup, columns: readonly ComparisonColumn[]): TableRow | null {
  const pairs = group.rows.find((row) => row.key === 'hub_pairs_with_bike_option');
  const options = group.rows.find((row) => row.key === 'bike_options_offered');
  if (pairs === undefined || options === undefined) return null;
  const cells = columns.map((column): TableCell => {
    if (column.kind === 'flat') return NO_CELL;
    const a = pairs.values[column.version.letter] ?? null;
    const b = options.values[column.version.letter] ?? null;
    return {
      ...NO_CELL,
      text:
        a === null || b === null
          ? DASH
          : `${formatAmount(a.value, 0)} · ${formatAmount(b.value, 0)}`,
    };
  });
  return {
    key: 'hub_pairs_with_bike_option',
    label: ROW_LABELS.hub_pairs_with_bike_option ?? '',
    note: null,
    tag: null,
    cells,
  };
}

/** The groups of the table, in the API's order; the solver's only with the Advanced view on. */
export function tableGroups(
  comparison: Comparison,
  columns: readonly ComparisonColumn[],
  advancedView: boolean,
): readonly TableGroup[] {
  const shown = comparison.groups.filter(
    (group) => group.rows.length > 0 && (advancedView || group.name !== 'solver'),
  );
  return shown.map((group) => {
    const rows: TableRow[] = [];
    for (const row of group.rows) {
      if (
        group.name === 'model' &&
        (row.key === 'bike_price_min' || row.key === 'bike_price_max')
      ) {
        if (row.key === 'bike_price_min') {
          const range = rangeRow(group, columns);
          if (range !== null) rows.push(range);
        }
        continue;
      }
      if (group.name === 'solver' && row.key === 'bike_options_offered') continue;
      if (group.name === 'solver' && row.key === 'hub_pairs_with_bike_option') {
        const joined = pairsRow(group, columns);
        if (joined !== null) rows.push(joined);
        continue;
      }
      rows.push(rowOf(group, row, columns, comparison));
    }
    return {
      name: group.name,
      title: GROUP_TITLES[group.name],
      tag: group.name === 'simulated' ? 'simulation' : group.name === 'model' ? 'model' : null,
      source: group.name === 'simulated' ? SIMULATION_SOURCE : null,
      rows,
    };
  });
}

// ---- where prices differ: the table and the map ----------------------------------------------

export const differencesHeading = (a: string, b: string): string =>
  `Hub pairs where the mean bike price differs most: Version ${b} ${MINUS} Version ${a}`;
export const DIFFERENCES_CAPTION =
  "Mean price per bike ride on the pair, weighted by the model's bike rides: a difference mixes a change of price with a change of who rides. Computed from the model's flows.";
export const identicalResultSentence = (x: string, y: string): string =>
  `Versions ${x} and ${y} have the same pricing model result: no hub pair price differs.`;

export const differenceHeaders = (a: string, b: string) =>
  ({
    fromTo: COLUMN_HEADINGS.fromTo,
    priceA: `Mean bike price in ${a} (CHF per ride)`,
    priceB: `Mean bike price in ${b} (CHF per ride)`,
    difference: 'Difference',
    travellers: 'Travellers on bike options',
  }) as const;

export interface DifferenceRow {
  readonly key: string;
  readonly fromTo: string;
  readonly priceA: string;
  readonly priceB: string;
  /** "▲ 0.12", "▼ 0.12" or "0.12". */
  readonly difference: string;
  readonly travellers: string;
}

const whole = (value: number): string => groupThousands(Math.round(value));

export function differenceRow(
  pair: PairDifference,
  hubLabels: ReadonlyMap<string, string>,
): DifferenceRow {
  const label = (hub: string): string => hubLabels.get(hub) ?? hub;
  const change = pair.priceDifference.value;
  const amount = formatAmount(Math.abs(change), 2);
  return {
    key: `${pair.originHub}>${pair.destinationHub}`,
    fromTo: `${label(pair.originHub)} → ${label(pair.destinationHub)}`,
    priceA: formatAmount(pair.meanPriceA.value, 2),
    priceB: formatAmount(pair.meanPriceB.value, 2),
    difference: change > 0 ? `▲ ${amount}` : change < 0 ? `▼ ${amount}` : amount,
    travellers: `${whole(pair.travellersA.value)} → ${whole(pair.travellersB.value)}`,
  };
}

export type CompareMeasure = 'priceDifference' | 'priceBMinusFlat' | 'ridesStartingDifference';
export const COMPARE_MAP_MEASURES: readonly CompareMeasure[] = [
  'priceDifference',
  'priceBMinusFlat',
  'ridesStartingDifference',
];

/** "Mean bike price: C − B"; the letters only. */
export function compareMeasureLabel(key: CompareMeasure, a: string, b: string): string {
  if (key === 'priceDifference') return `Mean bike price: ${b} ${MINUS} ${a}`;
  if (key === 'priceBMinusFlat') return `Mean bike price: ${b} ${MINUS} flat price`;
  return `Bike rides starting: ${b} ${MINUS} ${a}`;
}

export function compareMeasureValue(hub: HubDifference, key: CompareMeasure): number | null {
  return hub[key]?.value ?? null;
}

export interface LegendAnchors {
  readonly lower: string;
  readonly none: string;
  readonly higher: string;
}

/** The three anchor values of the legend: −m, 0 and +m with the unit of the measure. */
export function compareLegendAnchors(key: CompareMeasure, m: number): LegendAnchors {
  const rides = key === 'ridesStartingDifference';
  const unit = rides ? 'rides' : 'CHF per ride';
  const figure = rides ? whole(m) : formatAmount(m, 2);
  return {
    lower: `${MINUS}${figure} ${unit}`,
    none: `0 ${unit}`,
    higher: `+${figure} ${unit}`,
  };
}
