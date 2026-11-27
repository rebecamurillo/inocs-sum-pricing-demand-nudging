/** L-5's drawn route: the default card, the leg lines, the mode styles and the route's bounds. */
import type { GeoBounds, GeoPoint } from './map';
import type { RouteLegResult } from './pricing-result';
import type { QuotedMode, RouteOptionLeg, TripQuote } from './traveller';
import { legKind } from './trip-options';

type LegKind = ReturnType<typeof legKind>;

/** The card selected when a quote shows: PT + bike, else PT, else the first card with an option. */
export function defaultCard(quote: TripQuote): QuotedMode | null {
  const has = (mode: QuotedMode) =>
    quote.options.some((option) => option.mode === mode && option.mostTaken);
  if (has('pt_bike')) return 'pt_bike';
  if (has('pt_only')) return 'pt_only';
  return quote.options.find((option) => option.mostTaken)?.mode ?? null;
}

const TRANSIT_LABELS: Readonly<Record<string, string>> = {
  TRAM: 'Tram',
  BUS: 'Bus',
  RAIL: 'Train',
};

const wholeMinutes = (seconds: number) => `${String(Math.round(seconds / 60))} min`;

/** "Tram 12 · Bel-Air → Rive · 12 min"; a missing line or name is left out. */
export function legLine(leg: RouteLegResult): string {
  const minutes = wholeMinutes(leg.durationS);
  const kind = legKind(leg);
  const span =
    leg.fromPlace !== null && leg.toPlace !== null ? `${leg.fromPlace} → ${leg.toPlace}` : null;
  let head: string;
  if (kind === 'walk') head = 'Walk';
  else if (kind === 'car') head = 'Car';
  else if (kind === 'bike') head = 'Shared bike';
  else {
    const lower = leg.mode.toLowerCase();
    const label = TRANSIT_LABELS[leg.mode] ?? `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
    head = leg.line === null ? label : `${label} ${leg.line}`;
  }
  const withSpan = kind === 'walk' || kind === 'car' ? null : span;
  return [head, withSpan, minutes].filter((part) => part !== null).join(' · ');
}

export interface RouteStyle {
  readonly colour: string;
  readonly width: number;
  readonly dash: 'solid' | 'dashed' | 'dotted';
  readonly label: string;
}

/** A drawn route colours each leg by its kind; `#1baf7a` is the PT + bike card's colour only. */
export const ROUTE_STYLES: Readonly<Record<LegKind, RouteStyle>> = {
  car: { colour: '#eb6834', width: 3, dash: 'solid', label: 'Car' },
  pt: { colour: '#2a78d6', width: 3, dash: 'solid', label: 'Public transport' },
  bike: { colour: '#008300', width: 3, dash: 'dashed', label: 'Shared-bike leg' },
  walk: { colour: '#5a6459', width: 2, dash: 'dotted', label: 'Walking leg' },
};

export const ROUTE_KIND_ORDER: readonly LegKind[] = ['car', 'pt', 'bike', 'walk'];

/** The leg kinds an option has, in the legend's order. */
export function routeLegendKinds(legs: readonly RouteLegResult[]): LegKind[] {
  const present = new Set(legs.map(legKind));
  return ROUTE_KIND_ORDER.filter((kind) => present.has(kind));
}

export function straightLegsSentence(busShapes: boolean): string {
  return busShapes
    ? 'Tram and train legs: straight lines between stops.'
    : 'Tram, train and bus legs: straight lines between stops.';
}

/** The bounds of every leg position and the pins; null when there is none. */
export function routeBounds(
  legs: readonly RouteOptionLeg[],
  pins: readonly GeoPoint[],
): GeoBounds | null {
  const points: (readonly [number, number])[] = [
    ...legs.flatMap((leg) => leg.coordinates ?? []),
    ...pins.map((pin): readonly [number, number] => [pin.lon, pin.lat]),
  ];
  if (points.length === 0) return null;
  const lons = points.map(([lon]) => lon);
  const lats = points.map(([, lat]) => lat);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}
