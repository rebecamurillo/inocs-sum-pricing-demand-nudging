import { describe, expect, it } from 'vitest';
import {
  LEG_COLOURS,
  MODE_EDGE_COLOURS,
  NO_CAR_ROUTE,
  TRAVELLER_NOTES,
  durationLine,
  legStrip,
  makeUp,
  noBikeOption,
  noPriceMessages,
  otherBikeOptionLine,
  otherBikeOptions,
  otherBikeOptionsLabel,
  quoteHeading,
} from './trip-options';
import type { QuotedOption, QuotedPoint, TripQuote } from './traveller';

const option = (patch: Partial<QuotedOption>): QuotedOption => ({
  mode: 'pt_bike',
  mostTaken: false,
  price: 3.8,
  arcId: 'a1',
  durationS: 900,
  transfers: 0,
  bikeLegs: 1,
  bikePrice: 1.8,
  ptFare: 2,
  carCost: null,
  carParkingFee: null,
  flow: 1,
  legs: [],
  ...patch,
});
const point = (status: QuotedPoint['status']): QuotedPoint => ({
  status,
  hubId: null,
  nearestStopName: null,
  nearestHubId: null,
  distanceFromOutlineM: null,
});
const quote = (patch: Partial<TripQuote>): TripQuote => ({
  status: 'priced',
  fromPoint: null,
  toPoint: null,
  originHub: { hubId: 'H4', hubName: 'Plainpalais' },
  destinationHub: { hubId: 'H18', hubName: 'Eaux-Vives' },
  minTripDistanceM: null,
  noCarOption: null,
  options: [],
  ...patch,
});
const text = (value: QuotedOption) =>
  makeUp(value)
    .parts.map((part) => part.text)
    .join('');

describe('makeUp', () => {
  it('writes the bike make-up with one bike leg, the price bold, and the tag', () => {
    const made = makeUp(option({}));
    expect(text(option({}))).toBe('Fare 2.00 + bike ride 1.80');
    expect(made.parts.filter((part) => part.bold).map((part) => part.text)).toEqual(['1.80']);
    expect(made.tag).toBe('SET BY THE PRICING MODEL');
  });

  it('writes the bike make-up with two bike legs', () => {
    expect(text(option({ bikeLegs: 2, bikePrice: 0.9 }))).toBe('Fare 2.00 + 2 bike rides × 0.90');
  });

  it('writes the public transport and car make-ups without a tag', () => {
    const pt = option({ mode: 'pt_only', ptFare: 2, bikePrice: null });
    const car = option({ mode: 'car', carCost: 3.4, carParkingFee: 2.8 });
    expect(text(pt)).toBe('Fare 2.00');
    expect(text(car)).toBe('Car cost 3.40 + parking fee 2.80');
    expect(makeUp(pt).tag).toBeNull();
    expect(makeUp(car).tag).toBeNull();
  });
});

describe('the heading', () => {
  it('names both hubs for a priced or no-bike-option quote only', () => {
    expect(quoteHeading(quote({}))).toBe(
      'Priced between hub H4 (Plainpalais) and hub H18 (Eaux-Vives)',
    );
    expect(quoteHeading(quote({ status: 'no_bike_option' }))).not.toBeNull();
    expect(quoteHeading(quote({ status: 'same_hub' }))).toBeNull();
    expect(quoteHeading(quote({ originHub: null }))).toBeNull();
  });
});

describe('card parts', () => {
  it('writes the duration line', () => {
    expect(durationLine(option({ durationS: 1000, transfers: 1 }))).toBe('17 min · 1 transfer');
    expect(durationLine(option({ durationS: 600, transfers: 2 }))).toBe('10 min · 2 transfers');
    expect(durationLine(option({ durationS: 600, transfers: 0 }))).toBe('10 min · 0 transfers');
  });

  it('sizes the leg strip by duration and colours it by kind', () => {
    const leg = (mode: string, durationS: number) => ({
      mode,
      line: null,
      fromPlace: null,
      toPlace: null,
      durationS,
    });
    const strip = legStrip([
      leg('WALK', 100),
      leg('TRAM', 300),
      leg('BICYCLE', 100),
      leg('CAR', 0),
    ]);
    expect(strip.map((item) => item.kind)).toEqual(['walk', 'pt', 'bike', 'car']);
    expect(strip.map((item) => item.share)).toEqual([0.2, 0.6, 0.2, 0]);
    expect(strip.map((item) => item.colour)).toEqual(['#5a6459', '#2a78d6', '#008300', '#eb6834']);
    expect(legStrip([leg('WALK', 0), leg('TRAM', 0)]).map((item) => item.share)).toEqual([
      0.5, 0.5,
    ]);
    expect(LEG_COLOURS.pt).toBe('#2a78d6');
  });

  it('has the edge colour of each mode', () => {
    expect(MODE_EDGE_COLOURS).toEqual({
      car: '#eb6834',
      pt_bike: '#1baf7a',
      pt_only: '#2a78d6',
    });
  });
});

describe('the other bike options', () => {
  it('leaves out the most taken, and orders by flow then arc id', () => {
    const shown = quote({
      options: [
        option({ arcId: 'a1', mostTaken: true, flow: 9 }),
        option({ arcId: 'a3', flow: 2 }),
        option({ arcId: 'a2', flow: 2 }),
        option({ arcId: 'a4', flow: 5 }),
        option({ arcId: 'p', mode: 'pt_only', flow: 50 }),
      ],
    });
    expect(otherBikeOptions(shown).map((item) => item.arcId)).toEqual(['a4', 'a2', 'a3']);
    expect(otherBikeOptionsLabel(3)).toBe('+ 3 other bike options offered');
  });

  it('writes a line with the legs, the minutes and the price', () => {
    const line = otherBikeOptionLine(
      option({
        durationS: 1260,
        price: 3.1,
        legs: [
          { mode: 'WALK', line: null, fromPlace: 'A', toPlace: 'B', durationS: 60 },
          { mode: 'TRAM', line: '12', fromPlace: 'B', toPlace: 'Rive', durationS: 600 },
          { mode: 'BICYCLE', line: null, fromPlace: 'Rive', toPlace: 'Eaux-Vives', durationS: 600 },
        ],
      }),
    );
    expect(line).toEqual({
      legs: 'Tram 12 → Rive · bike Rive → Eaux-Vives',
      duration: '21 min',
      price: '3.10 CHF',
    });
  });
});

describe('the notes and the card-place messages', () => {
  it('has the three notes in order', () => {
    expect(TRAVELLER_NOTES).toEqual([
      "The bike price is the pricing model's price for this option, per bike ride, added to the public transport fare. Durations and legs: trip planner, between the two hubs.",
      'The pricing model prices a shared bike only together with a public transport trip: a trip by shared bike alone has no option here.',
      'Durations and legs are those of the hub pair: the walk from your point to the hub is not included.',
    ]);
    expect(TRAVELLER_NOTES.join(' ').toLowerCase()).not.toContain('recommend');
  });

  it('words the missing bike and car options', () => {
    expect(noBikeOption('B')).toBe(
      'No bike option offered: the pricing model offers none on this hub pair in Version B.',
    );
    expect(NO_CAR_ROUTE).toBe(
      "No car route: the trip planner's car query failed for this hub pair when the instance was built.",
    );
  });
});

describe('noPriceMessages', () => {
  const messages = (patch: Partial<TripQuote>, radiusM: number | null = 3000) =>
    noPriceMessages(quote(patch), 'Geneva 3 km v1', radiusM);

  it('words each hub-pair status with its values', () => {
    expect(messages({ status: 'same_hub' })).toEqual([
      'No model price for this trip: both points are in hub H4. The model prices trips between hubs.',
    ]);
    expect(messages({ status: 'under_minimum_distance', minTripDistanceM: 500 })).toEqual([
      "No model price: hubs H4 and H18 are closer than this instance's minimum trip distance (500 m).",
    ]);
    expect(messages({ status: 'removed_by_quality_check' })).toEqual([
      "No model price: the routes of H4 → H18 were removed when the instance's routes were checked.",
    ]);
    expect(messages({ status: 'no_route' })).toEqual([
      'No model price: the trip planner found no public transport route for H4 → H18 when the instance was built.',
    ]);
  });

  it('writes one outside-zone line per point outside, A first, with the radius in km', () => {
    const both = {
      status: 'outside_zone' as const,
      fromPoint: point('outside_zone'),
      toPoint: point('outside_zone'),
    };
    expect(messages(both)).toEqual([
      'Point A is outside the 3 km zone of Geneva 3 km v1.',
      'Point B is outside the 3 km zone of Geneva 3 km v1.',
    ]);
    expect(
      messages(
        { status: 'outside_zone', fromPoint: point('matched'), toPoint: point('outside_zone') },
        2500,
      ),
    ).toEqual(['Point B is outside the 2.5 km zone of Geneva 3 km v1.']);
    expect(
      messages({
        status: 'outside_zone',
        fromPoint: point('outside_zone'),
        toPoint: point('matched'),
      }),
    ).toEqual(['Point A is outside the 3 km zone of Geneva 3 km v1.']);
  });

  it('says nothing for priced, one point and no hub here', () => {
    for (const status of ['priced', 'one_point', 'no_hub_here', 'no_bike_option'] as const) {
      expect(messages({ status })).toEqual([]);
    }
  });
});
