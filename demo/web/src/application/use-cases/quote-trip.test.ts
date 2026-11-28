import { describe, expect, it } from 'vitest';
import { fakeCityInstances } from '../ports/fake-city-instance-gateway';
import {
  fakePricing,
  sampleSealedPricing,
  samplePricingDraft,
} from '../ports/fake-pricing-gateway';
import { fakeTrips } from '../ports/fake-trip-gateway';
import { loadTravellerChoices, quoteTrip, searchPlaces } from './quote-trip';

const a = { lat: 46.199, lon: 6.14 };
const b = { lat: 46.2102, lon: 6.1424 };

describe('quoteTrip', () => {
  it('asks for nothing without a point', async () => {
    const trips = fakeTrips();
    expect(
      await quoteTrip({ trips: trips.gateway }, 'geneva-3km.v1.B', null, null, null),
    ).toBeNull();
    expect(trips.quoteCalls).toEqual([]);
  });

  it('quotes the points that are set, for the version and the period', async () => {
    const trips = fakeTrips();
    const quote = await quoteTrip({ trips: trips.gateway }, 'geneva-3km.v1.B', 'mon-08', a, b);
    expect(quote?.status).toBe('priced');
    expect(trips.quoteCalls).toEqual([
      { pricingVersionId: 'geneva-3km.v1.B', period: 'mon-08', from: a, to: b },
    ]);
    await quoteTrip({ trips: trips.gateway }, 'geneva-3km.v1.B', null, null, b);
    expect(trips.quoteCalls[1]).toMatchObject({ from: null, to: b });
  });
});

describe('searchPlaces', () => {
  it('asks from two characters on, for the instance version', async () => {
    const trips = fakeTrips();
    expect(await searchPlaces({ trips: trips.gateway }, 'geneva-3km.v1', ' p ')).toEqual([]);
    expect(trips.placeCalls).toEqual([]);
    expect(await searchPlaces({ trips: trips.gateway }, 'geneva-3km.v1', 'Plain')).toHaveLength(2);
    expect(trips.placeCalls).toEqual([{ instanceVersionId: 'geneva-3km.v1', text: 'Plain' }]);
  });
});

describe('loadTravellerChoices', () => {
  it('lists the finished versions of the built instance versions in the menu order', async () => {
    const pricing = fakePricing([
      sampleSealedPricing({ id: 'geneva-3km.v1.A', letter: 'A', name: 'Flat' }),
      samplePricingDraft({ id: 'geneva-3km.v1.B', letter: 'B' }),
      sampleSealedPricing({ id: 'geneva-3km.v1.C', letter: 'C', name: 'Incentive' }),
    ]).gateway;

    const choices = await loadTravellerChoices({ cityInstances: fakeCityInstances(), pricing });

    expect(choices.map((choice) => choice.label)).toEqual([
      'Geneva 3 km v1 · Version A · Flat',
      'Geneva 3 km v1 · Version C · Incentive',
    ]);
  });
});
