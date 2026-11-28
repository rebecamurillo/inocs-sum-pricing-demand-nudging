import { describe, expect, it } from 'vitest';
import type { InstanceMenuEntry } from './city-instance';
import type { PricingVersion } from './pricing-version';
import {
  OPTION_CARDS,
  cardPrices,
  fieldForClick,
  finishedVersionChoices,
  firstFinished,
  instanceSentence,
  nextPrevious,
  noHubMessage,
  placeLine,
  pointFieldText,
  priceText,
  scopeLine,
  timeSlots,
  type QuotedPoint,
  type QuotedOption,
  type TripQuote,
} from './traveller';

const blankOption: QuotedOption = {
  mode: 'car',
  mostTaken: true,
  price: 0,
  arcId: 'a',
  durationS: 0,
  transfers: 0,
  bikeLegs: 0,
  bikePrice: null,
  ptFare: null,
  carCost: null,
  carParkingFee: null,
  flow: null,
  legs: [],
};
const blankQuote: TripQuote = {
  status: 'priced',
  fromPoint: null,
  toPoint: null,
  originHub: null,
  destinationHub: null,
  minTripDistanceM: null,
  noCarOption: null,
  options: [],
};

const menu: InstanceMenuEntry[] = [
  {
    id: 'geneva-3km',
    name: 'Geneva 3 km',
    datasetId: 'd',
    versions: [
      {
        id: 'geneva-3km.v1',
        number: 1,
        status: 'sealed',
        state: 'ready',
        pricingVersionCount: 0,
        pricingVersionLetters: [],
      },
      {
        id: 'geneva-3km.v2',
        number: 2,
        status: 'draft',
        state: 'draft',
        pricingVersionCount: 0,
        pricingVersionLetters: [],
      },
    ],
  },
  {
    id: 'geneva-2km',
    name: 'Geneva 2 km',
    datasetId: 'd',
    versions: [
      {
        id: 'geneva-2km.v1',
        number: 1,
        status: 'sealed',
        state: 'ready',
        pricingVersionCount: 0,
        pricingVersionLetters: [],
      },
    ],
  },
];

const pricing = (
  instanceVersionId: string,
  letter: string,
  state: PricingVersion['state'],
  name = `Version ${letter}`,
): PricingVersion =>
  ({
    id: `${instanceVersionId}.${letter}`,
    instanceVersionId,
    letter,
    name,
    state,
    periods: [{ id: 'p', key: 'mon-08', label: 'Monday 08:00–09:00' }],
  }) as unknown as PricingVersion;

describe('finishedVersionChoices', () => {
  const byVersion = {
    'geneva-3km.v1': [
      pricing('geneva-3km.v1', 'A', 'draft'),
      pricing('geneva-3km.v1', 'B', 'result', 'Incentive'),
      pricing('geneva-3km.v1', 'C', 'running'),
      pricing('geneva-3km.v1', 'D', 'failed'),
      pricing('geneva-3km.v1', 'E', 'cancelled'),
      pricing('geneva-3km.v1', 'F', 'queued'),
      pricing('geneva-3km.v1', 'G', 'result'),
    ],
    'geneva-2km.v1': [pricing('geneva-2km.v1', 'A', 'result')],
  };

  it('lists the finished versions only, named with their instance, in the menu order', () => {
    const choices = finishedVersionChoices(menu, byVersion);
    expect(choices.map((choice) => choice.label)).toEqual([
      'Geneva 3 km v1 · Version B · Incentive',
      'Geneva 3 km v1 · Version G · Version G',
      'Geneva 2 km v1 · Version A · Version A',
    ]);
    expect(choices[0]).toMatchObject({
      id: 'geneva-3km.v1.B',
      instanceVersionId: 'geneva-3km.v1',
      instanceId: 'geneva-3km',
      instanceVersionName: 'Geneva 3 km v1',
      number: 1,
      letter: 'B',
    });
  });

  it('orders the versions of one instance version by letter', () => {
    const choices = finishedVersionChoices(menu, {
      'geneva-3km.v1': [
        pricing('geneva-3km.v1', 'C', 'result'),
        pricing('geneva-3km.v1', 'A', 'result'),
      ],
    });
    expect(choices.map((choice) => choice.letter)).toEqual(['A', 'C']);
  });

  it('offers nothing without a finished version', () => {
    expect(
      finishedVersionChoices(menu, { 'geneva-3km.v1': [pricing('geneva-3km.v1', 'A', 'draft')] }),
    ).toEqual([]);
    expect(firstFinished([])).toBeNull();
  });

  it('finds the first finished version', () => {
    expect(firstFinished(finishedVersionChoices(menu, byVersion))?.id).toBe('geneva-3km.v1.B');
  });
});

describe('the instance sentence and the time slots', () => {
  it('writes the counts of the instance version', () => {
    expect(instanceSentence(14, 22)).toBe(
      'Gives the city instance (its 14 hubs and 22 bike stations, on the map) and the time slots that have prices.',
    );
  });

  it('lists the 17 hours from 06:00 to 23:00 with the priced ones selectable', () => {
    const slots = timeSlots([{ id: 'p', key: 'mon-08', label: 'Monday 08:00–09:00' }]);
    expect(slots).toHaveLength(17);
    expect(slots[0]).toEqual({
      key: 'mon-06',
      label: '06:00–07:00 · no prices in this version',
      range: '06:00–07:00',
      priced: false,
    });
    expect(slots[2]).toEqual({
      key: 'mon-08',
      label: '08:00–09:00',
      range: '08:00–09:00',
      priced: true,
    });
    expect(slots[16]?.range).toBe('22:00–23:00');
    expect(slots.filter((slot) => slot.priced)).toHaveLength(1);
  });
});

describe('points and messages', () => {
  const matched: QuotedPoint = {
    status: 'matched',
    hubId: 'H4',
    nearestStopName: 'Plainpalais',
    nearestHubId: null,
    distanceFromOutlineM: null,
  };
  const noHub: QuotedPoint = {
    status: 'no_hub_here',
    hubId: null,
    nearestStopName: null,
    nearestHubId: 'H7',
    distanceFromOutlineM: 412.6,
  };

  it('writes the field of a matched point and leaves the others empty', () => {
    expect(pointFieldText(matched)).toBe('hub H4 · Plainpalais');
    expect(pointFieldText(noHub)).toBe('');
    expect(pointFieldText({ ...noHub, status: 'outside_zone' })).toBe('');
    expect(pointFieldText(null)).toBe('');
  });

  it('writes the no-hub message with the distance in whole metres', () => {
    expect(noHubMessage(noHub)).toBe(
      'No hub here: the nearest hub, H7, is 413 m away. Click closer to a stop or a bike station.',
    );
    expect(noHubMessage(matched)).toBeNull();
    expect(noHubMessage({ ...noHub, status: 'outside_zone' })).toBeNull();
  });

  it('writes a place line', () => {
    expect(placeLine({ name: 'Plainpalais', kind: 'stop', hubId: 'H4', lat: 1, lon: 2 })).toBe(
      'Plainpalais · stop · hub H4',
    );
    expect(
      placeLine({ name: 'Rond-Point', kind: 'bike_station', hubId: 'H9', lat: 1, lon: 2 }),
    ).toBe('Rond-Point · bike station · hub H9');
  });

  it('sets the focused field on a click, else A when it is empty, else B', () => {
    const point = { lat: 1, lon: 2 };
    expect(fieldForClick('a', point)).toBe('a');
    expect(fieldForClick('b', null)).toBe('b');
    expect(fieldForClick(null, null)).toBe('a');
    expect(fieldForClick(null, point)).toBe('b');
  });
});

describe('prices', () => {
  const option = (mode: QuotedOption['mode'], price: number, mostTaken: boolean): QuotedOption => ({
    ...blankOption,
    mode,
    price,
    mostTaken,
  });
  const quote = (options: QuotedOption[]): TripQuote => ({
    ...blankQuote,
    status: 'priced',
    options,
  });

  it('writes the scope line and the price', () => {
    expect(scopeLine('08:00–09:00', 'C')).toBe('Monday 08:00–09:00 · Version C');
    expect(priceText(2.5)).toBe('2.50 CHF');
  });

  it('orders the cards car, public transport + shared bike, public transport', () => {
    expect(OPTION_CARDS.map((card) => card.mode)).toEqual(['car', 'pt_bike', 'pt_only']);
    expect(OPTION_CARDS.map((card) => card.label)).toEqual([
      'Car',
      'Public transport + shared bike',
      'Public transport',
    ]);
  });

  it('takes the most taken option of each mode and none for an absent mode', () => {
    const prices = cardPrices(
      quote([
        option('pt_only', 2, true),
        option('pt_bike', 3.1, false),
        option('pt_bike', 2.9, true),
      ]),
    );
    expect(prices.get('pt_bike')).toBe(2.9);
    expect(prices.get('pt_only')).toBe(2);
    expect(prices.has('car')).toBe(false);
  });
});

describe('the struck-through previous quote', () => {
  const shown = (
    pricingVersionId: string,
    instanceVersionId: string,
    points = 'p1',
    price = 2,
  ) => ({
    pricingVersionId,
    instanceVersionId,
    points,
    quote: {
      ...blankQuote,
      status: 'priced' as const,
      options: [{ ...blankOption, mode: 'car' as const, price, mostTaken: true }],
    } satisfies TripQuote,
  });

  it('keeps the previous quote of another version of the same instance version and the same points', () => {
    const b = shown('v1.B', 'v1');
    const c = shown('v1.C', 'v1', 'p1', 3);
    expect(nextPrevious(b, null, c)).toBe(b);
  });

  it('keeps no previous quote across instance versions', () => {
    expect(nextPrevious(shown('v1.B', 'v1'), null, shown('w1.A', 'w1'))).toBeNull();
  });

  it('drops it when the points change and keeps it when the same quote is read again', () => {
    const b = shown('v1.B', 'v1');
    const c = shown('v1.C', 'v1');
    expect(nextPrevious(b, null, shown('v1.B', 'v1', 'p2'))).toBeNull();
    expect(nextPrevious(c, b, shown('v1.C', 'v1'))).toBe(b);
    expect(nextPrevious(null, null, c)).toBeNull();
  });
});
