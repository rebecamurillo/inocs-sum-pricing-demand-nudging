/** Every wording of L-3 (the result of a pricing version), verbatim from UX-SPEC.md, and the arithmetic behind it. */
import { groupThousands } from './l1-text';
import {
  BALANCE_FIELD,
  PROFIT_FIXED,
  PROFIT_LABEL,
  RIDERSHIP_FIELD,
  goalText,
} from './pricing-goals-text';
import {
  MODES,
  periodTravellers,
  type GoalName,
  type ModeCounts,
  type PricingResult,
  type ResultNumber,
  type SimulationOutcome,
} from './pricing-result';
import type { PricingVersion } from './pricing-version';

export const RESULT_BRIEF = 'Result · pipeline step 6';
export const RESULT_SENTENCE =
  "The pricing model's prices for the period, and the same travellers simulated twice: with these prices and with a flat bike price.";
export const SIMULATION_TAG = 'SIMULATION';
export const SIMULATION_SOURCE =
  'Simulated travellers · placeholder rule: half price, half travel time';
export const PLACEHOLDER_SENTENCE =
  "A placeholder until the model's author defines the simulation.";
export const THREE_MODES_SENTENCE =
  'The pricing model prices a shared bike only together with a public transport trip: trips by shared bike alone are not part of these results.';
export const MODEL_TAG = "PRICING MODEL'S RESULT";
export const MODEL_SPLIT_TITLE = "The pricing model's own split";
export const WHY_IT_DIFFERS =
  'Why it differs from the simulated split: the pricing model spreads the travellers of each hub pair over the options with its own choice rule; the simulation sends each traveller to one option by the placeholder rule and counts the bikes and docks. The pricing model is not run with the flat price.';
export const GOALS_TITLE = 'The three goals of this version';
export const SIMULATED_LABEL = 'simulated travellers · placeholder rule';
export const COMPUTED_LABEL = "computed from the model's flows";
export const NO_STORED_RESULT = 'The result could not be read: no stored result.';

export function scopeLine(
  letter: string,
  name: string,
  instanceLabel: string,
  periodLabel: string,
): string {
  return `Version ${letter} · ${name} · ${instanceLabel} · ${periodLabel}`;
}

export const versionBarLabel = (letter: string): string => `With Version ${letter}'s prices`;
export const flatBarLabel = (amount: number): string =>
  `With a flat price ${amount.toFixed(2)} CHF`;
export const modelBarLabel = (letter: string): string => `Version ${letter}, pricing model`;

/** Rounds half away from zero; the noise of binary fractions (10.005) is dropped first. */
function roundHalfAway(value: number): number {
  const rounded = Math.round(Number(Math.abs(value).toPrecision(12)));
  return value < 0 && rounded !== 0 ? -rounded : rounded;
}

/** The car share with the flat price minus the car share with the version's prices, in points, whole. */
export function carShareChangePoints(
  flatCar: number,
  versionCar: number,
  travellers: number,
): number {
  if (travellers <= 0) return 0;
  return roundHalfAway((100 * flatCar) / travellers - (100 * versionCar) / travellers);
}

export function insightTitle(letter: string, points: number): string {
  const head = `With Version ${letter}'s prices, `;
  if (points > 0) {
    return `${head}${String(points)} in 100 fewer simulated travellers take the car than with the flat price`;
  }
  if (points < 0) {
    return `${head}${String(-points)} in 100 more simulated travellers take the car than with the flat price`;
  }
  return `${head}as many simulated travellers take the car as with the flat price`;
}

/** A text segment, or one of the two unserved counts (the view links it when above 0). */
export type CaptionPart = string | { readonly unserved: number };

export function captionParts(
  versionSim: SimulationOutcome,
  flatSim: SimulationOutcome,
): readonly CaptionPart[] {
  return [
    `Each of the ${groupThousands(periodTravellers(versionSim))} travellers of the period takes the option that scores best on half price, half travel time, while a bike and a dock remain at its stations. ${groupThousands(versionSim.displaced)} did not get their first choice (no bike or dock); ${groupThousands(flatSim.displaced)} with the flat price. Travellers left with no option: `,
    { unserved: versionSim.unserved },
    ' · ',
    { unserved: flatSim.unserved },
    '.',
  ];
}

export function captionText(parts: readonly CaptionPart[]): string {
  return parts
    .map((part) => (typeof part === 'string' ? part : groupThousands(part.unserved)))
    .join('');
}

/** A segment's share of the scale in whole percent. */
export function segmentShare(count: number, total: number): number {
  return total <= 0 ? 0 : Math.round((100 * count) / total);
}

/** The bar's accessible name: the three modes with their counts, so colour is never alone. */
export function modeSummary(counts: ModeCounts): string {
  return MODES.map((mode) => `${mode.label} ${groupThousands(counts[mode.key])}`).join(', ');
}

// ---- numbers on the tiles -------------------------------------------------------------------

/** An integer count of 10^-digits units as text, grouped, with U+2212 for a minus. */
function formatUnits(units: number, digits: number): string {
  const scale = 10 ** digits;
  const abs = Math.abs(units);
  const whole = Math.floor(abs / scale);
  const text =
    groupThousands(whole) + (digits > 0 ? `.${String(abs % scale).padStart(digits, '0')}` : '');
  return units < 0 ? `−${text}` : text;
}

/** A change with its sign: "+" or "−" (U+2212), 0 as "±0". `value` is in units of 10^-digits. */
export function formatChange(units: number, digits: number): string {
  if (units === 0) return '±0';
  return `${units > 0 ? '+' : ''}${formatUnits(units, digits)}`;
}

const toUnits = (value: number, digits: number): number => roundHalfAway(value * 10 ** digits);
const amount = (value: number, digits: number): string =>
  formatUnits(toUnits(value, digits), digits);

/** A number rounded half away from zero to `digits` decimals, grouped, with U+2212 for a minus. */
export const formatAmount = amount;
/** A value in whole units of 10^-digits, as `formatChange` takes it. */
export const toChangeUnits = toUnits;

export interface TileModelLine {
  readonly before: string;
  /** The blue tag follows `before` when the number before it is the pricing model's own. */
  readonly tagged: boolean;
  readonly after: string;
}

export interface GoalTile {
  readonly key: 'profit' | 'ridership' | 'station_balance' | 'average_bike_price';
  readonly heading: string;
  readonly weight: string | null;
  readonly note: string | null;
  readonly figure: string;
  readonly unit: string | null;
  readonly change: string | null;
  readonly flat: string | null;
  /** The figure, change and flat value in whole units of the tile's precision; null with no figure. */
  readonly units: {
    readonly figure: number;
    readonly change: number;
    readonly flat: number;
  } | null;
  readonly line: string | null;
  readonly simulatedLabel: string;
  /** A figure is always simulated: never under the blue tag. */
  readonly figureTagged: false;
  readonly model: TileModelLine | null;
}

function simulated(result: PricingResult, name: GoalName): { figure: number; flat: number } | null {
  const goal = result.goals[name];
  return goal.modelPrices === null || goal.flat === null
    ? null
    : { figure: goal.modelPrices.value, flat: goal.flat.value };
}

function figures(pair: { figure: number; flat: number } | null, digits: number) {
  if (pair === null) {
    return { figure: '—', change: null, flat: null, units: null };
  }
  const figure = toUnits(pair.figure, digits);
  const flat = toUnits(pair.flat, digits);
  const change = figure - flat;
  return {
    figure: formatUnits(figure, digits),
    change: formatChange(change, digits),
    flat: formatUnits(flat, digits),
    units: { figure, change, flat },
  };
}

const modelLine = (parts: readonly string[], tagged = false, after = ''): TileModelLine | null =>
  parts.length === 0 ? null : { before: `Pricing model: ${parts.join('')}`, tagged, after };

function profitModel(result: PricingResult): TileModelLine | null {
  const { profit, revenue, cost } = result.headline;
  if (profit === undefined) return null;
  const detail =
    revenue !== undefined && cost !== undefined
      ? ` (revenue ${amount(revenue.value, 0)} − cost ${amount(cost.value, 0)})`
      : '';
  return modelLine([`${amount(profit.value, 0)} CHF${detail} · ${COMPUTED_LABEL}`]);
}

function ridershipModel(result: PricingResult): TileModelLine | null {
  const model: ResultNumber | null = result.goals.ridership.model;
  return model === null ? null : modelLine([amount(model.value, 0)], true);
}

function balanceModel(result: PricingResult): TileModelLine | null {
  const { stations_empty_end: empty, stations_full_end: full } = result.headline;
  if (empty === undefined || full === undefined) return null;
  return modelLine([amount(empty.value + full.value, 0)], false, ` · ${COMPUTED_LABEL}`);
}

function priceModel(result: PricingResult, version: PricingVersion): TileModelLine | null {
  const { bike_price_min: low, bike_price_max: high, mean_bike_price: mean } = result.headline;
  // `rides_under_cost_share` is a fraction of the bike rides (unit `share`); the line shows whole percent.
  const { rides_under_cost: rides, rides_under_cost_share: share } = result.headline;
  const prices =
    low !== undefined && high !== undefined
      ? `prices ${amount(low.value, 2)} to ${amount(high.value, 2)}`
      : null;
  const rest = [
    mean === undefined ? null : `mean ${amount(mean.value, 2)}`,
    rides === undefined || share === undefined
      ? null
      : `${amount(rides.value, 0)} rides (${amount(100 * share.value, 0)} %) under the cost of ${amount(version.goals.cost_bike_chf, 2)}`,
  ].filter((part): part is string => part !== null);
  if (prices === null && rest.length === 0) return null;
  const tail = rest.length === 0 ? '' : `${prices === null ? '' : '; '}${rest.join(', ')}`;
  const after = `${tail} · ${COMPUTED_LABEL}`;
  return prices === null
    ? modelLine([tail.trimStart() + ` · ${COMPUTED_LABEL}`])
    : modelLine([prices], true, after);
}

/** The four goal tiles in order. `bikeStations` is the instance's count of bike stations. */
export function goalTiles(
  result: PricingResult,
  version: PricingVersion,
  bikeStations: number,
): readonly GoalTile[] {
  const base = { simulatedLabel: SIMULATED_LABEL, figureTagged: false } as const;

  const profit = figures(simulated(result, 'profit'), 0);
  const ridership = figures(simulated(result, 'ridership'), 0);
  const price = figures(simulated(result, 'mean_bike_price'), 2);

  const empty = simulated(result, 'stations_empty');
  const full = simulated(result, 'stations_full');
  const balanceSums =
    empty === null || full === null
      ? null
      : { figure: empty.figure + full.figure, flat: empty.flat + full.flat };
  const balance = figures(balanceSums, 0);
  const { stations_empty_start: startEmpty, stations_full_start: startFull } = result.headline;
  const line =
    balanceSums === null
      ? null
      : [
          `${balance.figure} of ${groupThousands(bikeStations)} stations empty or full at 09:00`,
          `${balance.flat ?? ''} with the flat price`,
          ...(startEmpty === undefined || startFull === undefined
            ? []
            : [`${amount(startEmpty.value + startFull.value, 0)} at 08:00`]),
        ].join(' · ');

  return [
    {
      ...base,
      key: 'profit',
      heading: PROFIT_LABEL,
      weight: `weight ${PROFIT_FIXED}`,
      note: 'revenue − cost of the simulated bike rides',
      unit: 'CHF',
      line: null,
      model: profitModel(result),
      ...profit,
    },
    {
      ...base,
      key: 'ridership',
      heading: RIDERSHIP_FIELD.label,
      weight: `weight ${version.goals.ridership_weight.toFixed(2)}`,
      note: 'riders on public transport + bike',
      unit: null,
      line: null,
      model: ridershipModel(result),
      ...ridership,
    },
    {
      ...base,
      key: 'station_balance',
      heading: BALANCE_FIELD.label,
      weight: `weight ${goalText(BALANCE_FIELD, version.goals.station_balance_weight)}`,
      note: null,
      unit: null,
      line,
      model: balanceModel(result),
      ...balance,
    },
    {
      ...base,
      key: 'average_bike_price',
      heading: 'Average bike price',
      weight: null,
      note: 'CHF per bike ride, the mean paid by simulated riders, against the flat price',
      unit: 'CHF',
      line: null,
      model: priceModel(result, version),
      ...price,
    },
  ];
}
