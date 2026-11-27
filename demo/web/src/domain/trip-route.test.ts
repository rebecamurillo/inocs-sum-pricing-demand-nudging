import { describe, expect, it } from 'vitest';
import type { RouteOptionLeg, QuotedOption, TripQuote } from './traveller';
import type { RouteLegResult } from './pricing-result';
import {
  ROUTE_STYLES,
  defaultCard,
  legLine,
  routeBounds,
  routeLegendKinds,
  straightLegsSentence,
} from './trip-route';

const leg = (
  mode: string,
  line: string | null,
  fromPlace: string | null,
  toPlace: string | null,
  durationS: number,
): RouteLegResult => ({ mode, line, fromPlace, toPlace, durationS });

const option = (mode: QuotedOption['mode'], mostTaken = true): QuotedOption => ({
  mode,
  mostTaken,
  price: 1,
  arcId: `${mode}-${String(mostTaken)}`,
  durationS: 600,
  transfers: 0,
  bikeLegs: 0,
  bikePrice: null,
  ptFare: null,
  carCost: null,
  carParkingFee: null,
  flow: null,
  legs: [],
});

const quote = (options: QuotedOption[], status: TripQuote['status'] = 'priced'): TripQuote => ({
  status,
  originHub: null,
  destinationHub: null,
  minTripDistanceM: null,
  noCarOption: null,
  fromPoint: null,
  toPoint: null,
  options,
});

describe('defaultCard', () => {
  it('is PT + bike when the quote has a most taken bike option', () => {
    expect(defaultCard(quote([option('car'), option('pt_bike'), option('pt_only')]))).toBe(
      'pt_bike',
    );
  });
  it('is PT when there is no bike option', () => {
    expect(defaultCard(quote([option('car'), option('pt_only')], 'no_bike_option'))).toBe(
      'pt_only',
    );
    expect(defaultCard(quote([option('pt_bike', false), option('pt_only')]))).toBe('pt_only');
  });
  it('falls back to the first card with an option, and to null without one', () => {
    expect(defaultCard(quote([option('car')]))).toBe('car');
    expect(defaultCard(quote([]))).toBeNull();
  });
});

describe('legLine', () => {
  it('writes each leg form', () => {
    expect(legLine(leg('WALK', null, 'A', 'Plainpalais', 120))).toBe('Walk · 2 min');
    expect(legLine(leg('FOOT', null, null, null, 30))).toBe('Walk · 1 min');
    expect(legLine(leg('TRAM', '12', 'Plainpalais', 'Rive', 700))).toBe(
      'Tram 12 · Plainpalais → Rive · 12 min',
    );
    expect(legLine(leg('BUS', '3', 'X', 'Y', 600))).toBe('Bus 3 · X → Y · 10 min');
    expect(legLine(leg('RAIL', 'IR', 'X', 'Y', 600))).toBe('Train IR · X → Y · 10 min');
    expect(legLine(leg('FERRY', null, 'X', 'Y', 600))).toBe('Ferry · X → Y · 10 min');
    expect(legLine(leg('BICYCLE', null, 'Rive', 'Cornavin', 260))).toBe(
      'Shared bike · Rive → Cornavin · 4 min',
    );
    expect(legLine(leg('CAR', null, 'Rive', 'Cornavin', 540))).toBe('Car · 9 min');
  });
  it('leaves out a missing line and missing names', () => {
    expect(legLine(leg('TRAM', null, null, 'Rive', 600))).toBe('Tram · 10 min');
    expect(legLine(leg('BICYCLE', null, 'Rive', null, 600))).toBe('Shared bike · 10 min');
  });
});

describe('ROUTE_STYLES', () => {
  it('holds the colours, widths and dashes of the mode table', () => {
    expect(ROUTE_STYLES.car).toMatchObject({ colour: '#eb6834', width: 3, dash: 'solid' });
    expect(ROUTE_STYLES.pt).toMatchObject({ colour: '#2a78d6', width: 3, dash: 'solid' });
    expect(ROUTE_STYLES.bike).toMatchObject({ colour: '#008300', width: 3, dash: 'dashed' });
    expect(ROUTE_STYLES.walk).toMatchObject({ colour: '#5a6459', width: 2, dash: 'dotted' });
    expect(Object.values(ROUTE_STYLES).map((s) => s.colour)).not.toContain('#1baf7a');
    expect(Object.values(ROUTE_STYLES).map((s) => s.label)).toEqual([
      'Car',
      'Public transport',
      'Shared-bike leg',
      'Walking leg',
    ]);
  });
});

describe('routeLegendKinds', () => {
  const route = (mode: string): RouteOptionLeg => ({
    mode,
    line: null,
    fromPlace: null,
    toPlace: null,
    durationS: 1,
    lineKind: 'street_path',
    coordinates: null,
  });
  it('lists the kinds present once, in a fixed order', () => {
    expect(
      routeLegendKinds([
        route('WALK'),
        route('BICYCLE'),
        route('TRAM'),
        route('BUS'),
        route('FOOT'),
      ]),
    ).toEqual(['pt', 'bike', 'walk']);
    expect(routeLegendKinds([route('CAR')])).toEqual(['car']);
    expect(routeLegendKinds([])).toEqual([]);
  });
});

describe('straightLegsSentence', () => {
  it('names the legs drawn as straight lines', () => {
    expect(straightLegsSentence(true)).toBe('Tram and train legs: straight lines between stops.');
    expect(straightLegsSentence(false)).toBe(
      'Tram, train and bus legs: straight lines between stops.',
    );
  });
});

describe('routeBounds', () => {
  const withLine = (coordinates: [number, number][] | null): RouteOptionLeg => ({
    mode: 'TRAM',
    line: null,
    fromPlace: null,
    toPlace: null,
    durationS: 1,
    lineKind: 'straight_line',
    coordinates,
  });
  it('spans the legs and the pins', () => {
    expect(
      routeBounds(
        [
          withLine([
            [6.14, 46.2],
            [6.15, 46.21],
          ]),
          withLine(null),
        ],
        [{ lat: 46.19, lon: 6.16 }],
      ),
    ).toEqual([6.14, 46.19, 6.16, 46.21]);
  });
  it('spans the pins alone, and is null with nothing', () => {
    expect(
      routeBounds(
        [],
        [
          { lat: 46.2, lon: 6.1 },
          { lat: 46.3, lon: 6.2 },
        ],
      ),
    ).toEqual([6.1, 46.2, 6.2, 46.3]);
    expect(routeBounds([withLine(null)], [])).toBeNull();
  });
});
