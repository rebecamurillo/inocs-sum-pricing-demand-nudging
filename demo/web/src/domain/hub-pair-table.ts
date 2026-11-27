/** The hub-pair table and the result map of L-3: rows, counts, sorting, option names, measures. */
import { groupThousands } from './l1-text';
import type { HubPairResult, HubResult, RouteLegResult } from './pricing-result';

export const NO_BIKE_RIDES = '— no bike rides';
export const NONE_OFFERED = 'no bike option offered';
export const PRICE_CAPTION =
  "Mean bike price: per ride, weighted by the model's bike rides on the pair, with the lowest and highest price offered.";
export const RANGE_LABEL = 'lowest – highest offered';

export type SortColumn = 'fromTo' | 'price' | 'bikeOptions' | 'car' | 'pt' | 'ptBike';
export const SORT_COLUMNS: readonly SortColumn[] = [
  'fromTo',
  'price',
  'bikeOptions',
  'car',
  'pt',
  'ptBike',
];
export const COLUMN_HEADINGS: Readonly<Record<SortColumn, string>> = {
  fromTo: 'From → to',
  price: 'Mean bike price',
  bikeOptions: 'Bike options',
  car: 'Car',
  pt: 'PT',
  ptBike: 'PT + bike',
};
export type SortDirection = 'asc' | 'desc';
export interface SortState {
  readonly column: SortColumn;
  readonly direction: SortDirection;
}

export interface HubPairCounts {
  readonly pairs: number;
  readonly withBikeOption: number;
}

export function HUB_PAIRS_LINK(counts: HubPairCounts): string {
  return `Price and flow per hub pair (${groupThousands(counts.pairs)} hub pairs, ${groupThousands(counts.withBikeOption)} with a bike option offered)`;
}

/** {n}: the hub pairs with routes (as L-1 counts them); {m}: the rows with an offered bike option. */
export function hubPairCounts(
  results: readonly HubPairResult[],
  hubPairsWithRoutes: number,
): HubPairCounts {
  return {
    pairs: hubPairsWithRoutes,
    withBikeOption: results.filter((item) => item.minBikePrice !== null).length,
  };
}

export type RowState = 'priced' | 'noRides' | 'noneOffered';

export interface HubPairRow {
  readonly key: string;
  readonly state: RowState;
  readonly fromTo: string;
  /** The mean with two decimals, or the sentence of the state. */
  readonly price: string;
  /** "{lowest} – {highest}", null when no option is offered. */
  readonly range: string | null;
  readonly bikeOptions: number;
  readonly car: string;
  readonly pt: string;
  readonly ptBike: string;
  readonly sortValues: Readonly<Record<SortColumn, number | string | null>>;
  readonly result: HubPairResult;
}

const whole = (n: number): string => groupThousands(Math.round(n));
const money = (n: number): string => n.toFixed(2);

export function offeredOptions(result: HubPairResult) {
  return result.options
    .filter((item) => item.mode === 'pt_bike' && item.bikePrice !== null)
    .sort((a, b) => (a.bikePrice?.value ?? 0) - (b.bikePrice?.value ?? 0));
}

export function hubPairRow(
  result: HubPairResult,
  hubLabels: ReadonlyMap<string, string>,
): HubPairRow {
  const min = result.minBikePrice;
  const max = result.maxBikePrice;
  const mean = result.meanBikePrice;
  const state: RowState = min === null ? 'noneOffered' : mean === null ? 'noRides' : 'priced';
  const fromTo = `${hubLabels.get(result.originHub) ?? result.originHub} → ${hubLabels.get(result.destinationHub) ?? result.destinationHub}`;
  const bikeOptions = offeredOptions(result).length;
  const { car, ptOnly, ptBike } = result.travellers;
  return {
    key: `${result.originHub}>${result.destinationHub}`,
    state,
    fromTo,
    price:
      state === 'priced' && mean !== null
        ? money(mean.value)
        : state === 'noRides'
          ? NO_BIKE_RIDES
          : NONE_OFFERED,
    range: min === null ? null : `${money(min.value)} – ${money((max ?? min).value)}`,
    bikeOptions,
    car: whole(car),
    pt: whole(ptOnly),
    ptBike: whole(ptBike),
    sortValues: {
      fromTo,
      price: mean === null ? null : mean.value,
      bikeOptions,
      car,
      pt: ptOnly,
      ptBike,
    },
    result,
  };
}

/** Ascending, then descending; rows without a value last both ways; ties keep their order. */
export function sortRows(
  rows: readonly HubPairRow[],
  column: SortColumn,
  direction: SortDirection,
): HubPairRow[] {
  const sign = direction === 'asc' ? 1 : -1;
  return rows
    .map((row, at) => ({ row, at }))
    .sort((a, b) => {
      const left = a.row.sortValues[column];
      const right = b.row.sortValues[column];
      if (left === null || right === null) {
        if (left === right) return a.at - b.at;
        return left === null ? 1 : -1;
      }
      const order =
        typeof left === 'string' || typeof right === 'string'
          ? String(left).localeCompare(String(right))
          : left - right;
      return order === 0 ? a.at - b.at : sign * order;
    })
    .map((item) => item.row);
}

export function nextSort(current: SortState | null, column: SortColumn): SortState {
  if (current !== null && current.column === column) {
    return { column, direction: current.direction === 'asc' ? 'desc' : 'asc' };
  }
  return { column, direction: 'asc' };
}

const TRANSIT_LABELS: Readonly<Record<string, string>> = {
  TRAM: 'Tram',
  BUS: 'Bus',
  RAIL: 'Train',
  SUBWAY: 'Metro',
  FERRY: 'Boat',
};
const WALKING = new Set(['FOOT', 'WALK']);

function legName(leg: RouteLegResult): string {
  if (leg.mode === 'BICYCLE') {
    return leg.fromPlace !== null && leg.toPlace !== null
      ? `bike ${leg.fromPlace} → ${leg.toPlace}`
      : 'bike';
  }
  if (leg.mode === 'CAR') return 'Car';
  const lower = leg.mode.toLowerCase();
  const label = TRANSIT_LABELS[leg.mode] ?? `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
  const named = leg.line === null ? label : `${label} ${leg.line}`;
  return leg.toPlace === null ? named : `${named} → ${leg.toPlace}`;
}

/** "Tram 12 → Rive · bike Rive → Eaux-Vives": the legs joined, walking left out. */
export function optionName(legs: readonly RouteLegResult[]): string {
  return legs
    .filter((leg) => !WALKING.has(leg.mode))
    .map(legName)
    .join(' · ');
}

export const formatMinutes = (seconds: number): string => `${String(Math.round(seconds / 60))} min`;
export const formatPrice = money;
export const formatRiders = whole;

export type MapMeasure = 'ridesStarting' | 'ridesEnding' | 'meanPrice';
export const MAP_MEASURES: readonly { readonly key: MapMeasure; readonly label: string }[] = [
  { key: 'ridesStarting', label: 'Bike rides starting at each hub' },
  { key: 'ridesEnding', label: 'Bike rides ending at each hub' },
  { key: 'meanPrice', label: 'Mean bike price from each hub' },
];

export function measureValue(hub: HubResult, measure: MapMeasure): number | null {
  if (measure === 'ridesStarting') return hub.ridesStarting.value;
  if (measure === 'ridesEnding') return hub.ridesEnding.value;
  return hub.meanBikePrice === null ? null : hub.meanBikePrice.value;
}

export function mapLegend(measure: MapMeasure, periodSpanText: string): string {
  const label = MAP_MEASURES.find((item) => item.key === measure)?.label ?? '';
  return `${label}, ${periodSpanText} · One disc per hub; a bike ride is one bike leg. Computed from the model's flows.`;
}

/** "Monday 08:00–09:00" → "08:00–09:00": the part after the day. */
export function periodSpan(periodLabel: string): string {
  const found = /\d{1,2}:\d{2}\s*[–-]\s*\d{1,2}:\d{2}/.exec(periodLabel);
  return found === null ? periodLabel : found[0];
}
