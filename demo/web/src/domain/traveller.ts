/** The traveller view (L-5): labels, the version list, the time slots and the quote's reading. */
import type { InstanceMenuEntry } from './city-instance';
import type { GeoPoint } from './map';
import type { RouteLegResult } from './pricing-result';
import type { PricingPeriod, PricingVersion } from './pricing-version';

export const TRAVELLER_BRIEF = {
  title: 'Traveller view',
  sentence:
    'What a traveller is offered for one trip: the options, how long they take and what they cost. The bike price comes from the pricing version chosen first.',
} as const;
export const ROW_TITLES = { version: 'Pricing version', trip: 'Trip', slot: 'Time slot' } as const;
export const TRIP_SENTENCE = 'Click the map or type a stop or station name.';
export const SWAP_LABEL = 'Swap A and B';
export const NEXT_VERSION_TAG = 'NEXT VERSION';
export const NEXT_VERSION_TEXT = 'every hour the version has priced.';
export const OPEN_IN_TRAVELLER_VIEW = 'Open in the traveller view';
export const RUN_A_PRICING_VERSION_FIRST = 'Run a pricing version first.';
export const DAY_NAME = 'Monday';
const NO_PRICES_SUFFIX = ' · no prices in this version';

/** The wire's quoted point, as the view reads it. */
export interface QuotedPoint {
  readonly status: 'matched' | 'outside_zone' | 'no_hub_here';
  readonly hubId: string | null;
  readonly nearestStopName: string | null;
  readonly nearestHubId: string | null;
  readonly distanceFromOutlineM: number | null;
}

export type QuotedMode = 'car' | 'pt_bike' | 'pt_only';

export interface QuotedOption {
  readonly mode: QuotedMode;
  /** The option with the largest flow within its mode. */
  readonly mostTaken: boolean;
  readonly price: number;
  readonly arcId: string;
  readonly durationS: number;
  readonly transfers: number;
  readonly bikeLegs: number;
  /** Per bike ride; PT + bike only. */
  readonly bikePrice: number | null;
  readonly ptFare: number | null;
  readonly carCost: number | null;
  readonly carParkingFee: number | null;
  readonly flow: number | null;
  readonly legs: readonly RouteLegResult[];
}

export type QuoteStatus =
  | 'one_point'
  | 'outside_zone'
  | 'no_hub_here'
  | 'same_hub'
  | 'under_minimum_distance'
  | 'no_route'
  | 'removed_by_quality_check'
  | 'no_bike_option'
  | 'priced';

export interface QuotedHub {
  readonly hubId: string;
  readonly hubName: string;
}

export interface TripQuote {
  readonly status: QuoteStatus;
  readonly originHub: QuotedHub | null;
  readonly destinationHub: QuotedHub | null;
  readonly minTripDistanceM: number | null;
  readonly noCarOption: boolean | null;
  readonly fromPoint: QuotedPoint | null;
  readonly toPoint: QuotedPoint | null;
  readonly options: readonly QuotedOption[];
}

export interface PlaceLine {
  readonly name: string;
  readonly kind: 'stop' | 'bike_station';
  readonly hubId: string;
  readonly lat: number;
  readonly lon: number;
}

/** A finished pricing version the traveller view offers. */
export interface VersionChoice {
  /** The pricing version's id. */
  readonly id: string;
  readonly instanceVersionId: string;
  readonly instanceId: string;
  /** "Geneva 3 km v1". */
  readonly instanceVersionName: string;
  readonly number: number;
  readonly letter: string;
  /** "Geneva 3 km v1 · Version B · Incentive". */
  readonly label: string;
  readonly periods: readonly PricingPeriod[];
}

/**
 * Every finished version of the built instance versions: the menu's order (instances as listed,
 * then versions), then letter order. Drafts, queued, running, failed and cancelled are absent.
 */
export function finishedVersionChoices(
  menu: readonly InstanceMenuEntry[],
  byInstanceVersion: Readonly<Record<string, readonly PricingVersion[]>>,
): VersionChoice[] {
  return menu.flatMap((entry) =>
    entry.versions.flatMap((version) =>
      [...(byInstanceVersion[version.id] ?? [])]
        .filter((item) => item.state === 'result')
        .sort((a, b) => a.letter.localeCompare(b.letter))
        .map((item) => ({
          id: item.id,
          instanceVersionId: version.id,
          instanceId: entry.id,
          instanceVersionName: `${entry.name} v${String(version.number)}`,
          number: version.number,
          letter: item.letter,
          label: `${entry.name} v${String(version.number)} · Version ${item.letter} · ${item.name}`,
          periods: item.periods,
        })),
    ),
  );
}

export function firstFinished(choices: readonly VersionChoice[]): VersionChoice | null {
  return choices[0] ?? null;
}

export function instanceSentence(hubs: number, bikeStations: number): string {
  return `Gives the city instance (its ${String(hubs)} hubs and ${String(bikeStations)} bike stations, on the map) and the time slots that have prices.`;
}

export interface TimeSlot {
  readonly key: string;
  /** The option's text: the range, with the reason when the version has no prices for it. */
  readonly label: string;
  /** "08:00–09:00". */
  readonly range: string;
  readonly priced: boolean;
}

const FIRST_HOUR = 6;
const LAST_HOUR = 22;
const two = (hour: number) => String(hour).padStart(2, '0');

/** One slot per hour cell of L-2's period row, 06 to 22; the version's periods are priced. */
export function timeSlots(periods: readonly PricingPeriod[]): TimeSlot[] {
  const priced = new Set(periods.map((period) => period.key));
  const slots: TimeSlot[] = [];
  for (let hour = FIRST_HOUR; hour <= LAST_HOUR; hour += 1) {
    const key = `mon-${two(hour)}`;
    const range = `${two(hour)}:00–${two(hour + 1)}:00`;
    const isPriced = priced.has(key);
    slots.push({
      key,
      range,
      priced: isPriced,
      label: isPriced ? range : `${range}${NO_PRICES_SUFFIX}`,
    });
  }
  return slots;
}

/** "hub H4 · Plainpalais" for a matched point; empty otherwise. */
export function pointFieldText(point: QuotedPoint | null): string {
  if (point?.status !== 'matched' || point.hubId === null) return '';
  return `hub ${point.hubId} · ${point.nearestStopName ?? ''}`;
}

export function noHubMessage(point: QuotedPoint | null): string | null {
  if (point?.status !== 'no_hub_here') return null;
  const metres = Math.round(point.distanceFromOutlineM ?? 0);
  return `No hub here: the nearest hub, ${point.nearestHubId ?? ''}, is ${String(metres)} m away. Click closer to a stop or a bike station.`;
}

export function placeLine(line: PlaceLine): string {
  const kind = line.kind === 'stop' ? 'stop' : 'bike station';
  return `${line.name} · ${kind} · hub ${line.hubId}`;
}

export type PointField = 'a' | 'b';

/** A map click sets the focused field; with none focused, A when it is empty, else B. */
export function fieldForClick(focused: PointField | null, a: GeoPoint | null): PointField {
  if (focused !== null) return focused;
  return a === null ? 'a' : 'b';
}

export function scopeLine(range: string, letter: string): string {
  return `${DAY_NAME} ${range} · Version ${letter}`;
}

export function priceText(value: number): string {
  return `${value.toFixed(2)} CHF`;
}

export const OPTION_CARDS: readonly { mode: QuotedMode; icon: string; label: string }[] = [
  { mode: 'car', icon: '🚗', label: 'Car' },
  { mode: 'pt_bike', icon: '🚋+🚲', label: 'Public transport + shared bike' },
  { mode: 'pt_only', icon: '🚋', label: 'Public transport' },
];

/** The price of the `most_taken` option of each mode the quote has. */
export function cardPrices(quote: TripQuote): Map<QuotedMode, number> {
  const prices = new Map<QuotedMode, number>();
  for (const option of quote.options) {
    if (option.mostTaken) prices.set(option.mode, option.price);
  }
  return prices;
}

/** A quote as the view showed it, with what it answered for. */
export interface ShownQuote {
  readonly pricingVersionId: string;
  readonly instanceVersionId: string;
  /** The points and the period it was asked for. */
  readonly points: string;
  readonly quote: TripQuote;
}

/**
 * The quote to strike through once `shown` arrives: the one shown before when it was another
 * version of the same instance version for the same points; the one already held when the same
 * version is read again; none otherwise (across instance versions, or after a change of points).
 */
export function nextPrevious(
  shownBefore: ShownQuote | null,
  previous: ShownQuote | null,
  shown: ShownQuote,
): ShownQuote | null {
  if (shownBefore?.points !== shown.points) return null;
  if (shownBefore.pricingVersionId === shown.pricingVersionId) return previous;
  return shownBefore.instanceVersionId === shown.instanceVersionId ? shownBefore : null;
}

export type RouteLineKind = 'street_path' | 'timetable_shape' | 'straight_line';

/** One leg of a stored option, with the line the map draws for it. */
export interface RouteOptionLeg {
  readonly mode: string;
  readonly line: string | null;
  readonly fromPlace: string | null;
  readonly toPlace: string | null;
  readonly durationS: number;
  readonly lineKind: RouteLineKind;
  /** `[lon, lat]` positions; null when the leg has no stored geometry. */
  readonly coordinates: readonly (readonly [number, number])[] | null;
}

export interface RouteOption {
  readonly arcId: string;
  readonly mode: QuotedMode;
  readonly legs: readonly RouteOptionLeg[];
}

export interface RouteOptionList {
  /** False when the city data set has no bus shapes. */
  readonly busShapes: boolean;
  readonly items: readonly RouteOption[];
}
