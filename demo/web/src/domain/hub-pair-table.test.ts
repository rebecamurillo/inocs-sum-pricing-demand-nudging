import { describe, expect, it } from 'vitest';
import type { HubPairResult, HubResult, OptionResult, ResultNumber } from './pricing-result';
import {
  COLUMN_HEADINGS,
  HUB_PAIRS_LINK,
  MAP_MEASURES,
  NONE_OFFERED,
  NO_BIKE_RIDES,
  PRICE_CAPTION,
  formatMinutes,
  hubPairCounts,
  hubPairRow,
  mapLegend,
  measureValue,
  nextSort,
  offeredOptions,
  optionName,
  periodSpan,
  sortRows,
  type HubPairRow,
} from './hub-pair-table';

const num = (value: number, unit = 'CHF'): ResultNumber => ({
  value,
  unit,
  source: 'model',
  group: 'advanced',
});

function option(arc: string, price: number | null, legs: OptionResult['legs'] = []): OptionResult {
  return {
    arcId: arc,
    mode: 'pt_bike',
    legs,
    duration: num(780, 's'),
    bikeLegs: num(1, 'legs'),
    bikePrice: price === null ? null : num(price),
    riders: num(12.4, 'travellers'),
  };
}

function pair(
  origin: string,
  destination: string,
  mean: number | null,
  range: [number, number] | null,
  options: OptionResult[] = [],
  travellers = { car: 10, ptOnly: 20, ptBike: 30 },
): HubPairResult {
  return {
    originHub: origin,
    destinationHub: destination,
    meanBikePrice: mean === null ? null : num(mean),
    minBikePrice: range === null ? null : num(range[0]),
    maxBikePrice: range === null ? null : num(range[1]),
    travellers,
    options,
  };
}

const labels = new Map([
  ['H1', 'H1 Rive'],
  ['H2', 'H2 Eaux-Vives'],
]);

describe('hubPairRow', () => {
  it('shows the mean and the range of a priced pair', () => {
    const row = hubPairRow(
      pair('H1', 'H2', 1.2, [0.8, 1.9], [option('a', 0.8), option('b', 1.9)]),
      labels,
    );
    expect(row).toMatchObject({
      state: 'priced',
      fromTo: 'H1 Rive → H2 Eaux-Vives',
      price: '1.20',
      range: '0.80 – 1.90',
      bikeOptions: 2,
      car: '10',
      pt: '20',
      ptBike: '30',
    });
  });

  it('shows "— no bike rides" with the offered range when the mean is absent', () => {
    const row = hubPairRow(pair('H1', 'H2', null, [0.8, 1.9], [option('a', 0.8)]), labels);
    expect(row.state).toBe('noRides');
    expect(row.price).toBe(NO_BIKE_RIDES);
    expect(NO_BIKE_RIDES).toBe('— no bike rides');
    expect(row.range).toBe('0.80 – 1.90');
  });

  it('shows "no bike option offered" and 0 options when nothing is offered', () => {
    const row = hubPairRow(pair('H9', 'H2', null, null, [option('a', null)]), labels);
    expect(row.state).toBe('noneOffered');
    expect(row.price).toBe(NONE_OFFERED);
    expect(NONE_OFFERED).toBe('no bike option offered');
    expect(row.range).toBeNull();
    expect(row.bikeOptions).toBe(0);
    expect(row.fromTo).toBe('H9 → H2 Eaux-Vives');
  });

  it('rounds and groups the travellers', () => {
    const row = hubPairRow(
      pair('H1', 'H2', null, null, [], { car: 1412.4, ptOnly: 0.2, ptBike: 12345.6 }),
      labels,
    );
    expect([row.car, row.pt, row.ptBike]).toEqual(['1 412', '0', '12 346']);
  });
});

describe('hubPairCounts and the link', () => {
  it('counts a none-offered pair in n, never in m', () => {
    const results = [
      pair('H1', 'H2', 1, [1, 1]),
      pair('H2', 'H1', null, [1, 2]),
      pair('H3', 'H1', null, null),
    ];
    expect(hubPairCounts(results, 3)).toEqual({ pairs: 3, withBikeOption: 2 });
  });

  it('writes the link with grouped numbers', () => {
    expect(HUB_PAIRS_LINK({ pairs: 1412, withBikeOption: 1003 })).toBe(
      'Price and flow per hub pair (1 412 hub pairs, 1 003 with a bike option offered)',
    );
  });
});

describe('sorting', () => {
  const rows: HubPairRow[] = [
    hubPairRow(
      pair('H1', 'H2', 2, [1, 3], [option('a', 1)], { car: 5, ptOnly: 9, ptBike: 1 }),
      labels,
    ),
    hubPairRow(pair('H2', 'H1', null, null, [], { car: 7, ptOnly: 1, ptBike: 2 }), labels),
    hubPairRow(pair('H3', 'H1', 1, [1, 1], [option('b', 1), option('c', 1)]), labels),
    hubPairRow(
      pair('H4', 'H1', 3, [1, 4], [option('d', 1)], { car: 5, ptOnly: 9, ptBike: 1 }),
      labels,
    ),
  ];
  const ids = (list: HubPairRow[]) => list.map((row) => row.key);

  it('orders by the mean ascending and descending with the empty ones last both ways', () => {
    expect(ids(sortRows(rows, 'price', 'asc'))).toEqual(['H3>H1', 'H1>H2', 'H4>H1', 'H2>H1']);
    expect(ids(sortRows(rows, 'price', 'desc'))).toEqual(['H4>H1', 'H1>H2', 'H3>H1', 'H2>H1']);
  });

  it('orders every data column', () => {
    expect(ids(sortRows(rows, 'fromTo', 'desc'))[0]).toBe('H4>H1');
    expect(ids(sortRows(rows, 'bikeOptions', 'asc'))).toEqual(['H2>H1', 'H1>H2', 'H4>H1', 'H3>H1']);
    expect(ids(sortRows(rows, 'bikeOptions', 'desc'))[0]).toBe('H3>H1');
    expect(ids(sortRows(rows, 'car', 'desc'))[0]).toBe('H3>H1');
    expect(ids(sortRows(rows, 'pt', 'asc'))[0]).toBe('H2>H1');
    expect(ids(sortRows(rows, 'ptBike', 'desc'))[0]).toBe('H3>H1');
  });

  it('keeps the given order for ties, both ways', () => {
    expect(ids(sortRows(rows, 'car', 'asc')).slice(0, 2)).toEqual(['H1>H2', 'H4>H1']);
    expect(ids(sortRows(rows, 'car', 'desc')).slice(2, 4)).toEqual(['H1>H2', 'H4>H1']);
  });

  it('does not change the input', () => {
    const copy = [...rows];
    sortRows(rows, 'price', 'desc');
    expect(rows).toEqual(copy);
  });

  it('moves a column ascending, then descending, and starts another ascending', () => {
    expect(nextSort(null, 'price')).toEqual({ column: 'price', direction: 'asc' });
    expect(nextSort({ column: 'price', direction: 'asc' }, 'price')).toEqual({
      column: 'price',
      direction: 'desc',
    });
    expect(nextSort({ column: 'price', direction: 'desc' }, 'car')).toEqual({
      column: 'car',
      direction: 'asc',
    });
  });
});

describe('option names', () => {
  const tram = {
    mode: 'TRAM',
    line: '12',
    fromPlace: 'Plainpalais',
    toPlace: 'Rive',
    durationS: 300,
  };
  const bike = {
    mode: 'BICYCLE',
    line: null,
    fromPlace: 'Rive',
    toPlace: 'Eaux-Vives',
    durationS: 400,
  };
  const walk = { mode: 'FOOT', line: null, fromPlace: 'A', toPlace: 'B', durationS: 60 };

  it('names the example by its legs with walking left out', () => {
    expect(optionName([walk, tram, walk, bike])).toBe('Tram 12 → Rive · bike Rive → Eaux-Vives');
  });

  it('names a bus, a train and an unknown mode', () => {
    expect(optionName([{ ...tram, mode: 'BUS', line: '1' }])).toBe('Bus 1 → Rive');
    expect(optionName([{ ...tram, mode: 'RAIL', line: 'R3' }])).toBe('Train R3 → Rive');
    expect(optionName([{ ...tram, mode: 'SUBWAY', line: 'M1' }])).toBe('Metro M1 → Rive');
    expect(optionName([{ ...tram, mode: 'FERRY', line: 'M2' }])).toBe('Boat M2 → Rive');
    expect(optionName([{ ...tram, mode: 'GONDOLA', line: 'G' }])).toBe('Gondola G → Rive');
  });

  it('drops a missing line and names an old leg by its label alone', () => {
    expect(optionName([{ ...tram, line: null }])).toBe('Tram → Rive');
    const old = { mode: 'TRAM', line: null, fromPlace: null, toPlace: null, durationS: 1 };
    expect(optionName([old, { ...old, mode: 'BICYCLE' }])).toBe('Tram · bike');
  });

  it('formats minutes', () => {
    expect(formatMinutes(780)).toBe('13 min');
    expect(formatMinutes(89)).toBe('1 min');
  });

  it('lists the offered options in ascending price order', () => {
    const result = pair('H1', 'H2', 1, [1, 2], [option('x', 2), option('y', null), option('z', 1)]);
    expect(offeredOptions(result).map((item) => item.arcId)).toEqual(['z', 'x']);
  });
});

describe('the map measures and legend', () => {
  const hub: HubResult = {
    hubId: 'H1',
    label: 'H1 Rive',
    lat: 46.2,
    lon: 6.1,
    ridesStarting: num(4, 'rides'),
    ridesEnding: num(7, 'rides'),
    meanBikePrice: null,
  };

  it('offers the three measures in order', () => {
    expect(MAP_MEASURES.map((item) => item.label)).toEqual([
      'Bike rides starting at each hub',
      'Bike rides ending at each hub',
      'Mean bike price from each hub',
    ]);
    expect(measureValue(hub, 'ridesStarting')).toBe(4);
    expect(measureValue(hub, 'ridesEnding')).toBe(7);
    expect(measureValue(hub, 'meanPrice')).toBeNull();
  });

  it('writes the legend per measure with the period span', () => {
    expect(mapLegend('ridesStarting', '08:00–09:00')).toBe(
      "Bike rides starting at each hub, 08:00–09:00 · One disc per hub; a bike ride is one bike leg. Computed from the model's flows.",
    );
    expect(mapLegend('meanPrice', '08:00–09:00')).toContain(
      'Mean bike price from each hub, 08:00–09:00',
    );
    expect(mapLegend('ridesEnding', '08:00–09:00')).toMatch(/^Bike rides ending at each hub, /);
  });

  it('takes the time span after the day', () => {
    expect(periodSpan('Monday 08:00–09:00')).toBe('08:00–09:00');
    expect(periodSpan('Rush hour')).toBe('Rush hour');
  });
});

describe('the wording', () => {
  it('has the columns of the spec and no "Bike" column', () => {
    expect(Object.values(COLUMN_HEADINGS)).toEqual([
      'From → to',
      'Mean bike price',
      'Bike options',
      'Car',
      'PT',
      'PT + bike',
    ]);
    expect(Object.values(COLUMN_HEADINGS)).not.toContain('Bike');
    expect(PRICE_CAPTION).toBe(
      "Mean bike price: per ride, weighted by the model's bike rides on the pair, with the lowest and highest price offered.",
    );
    expect(PRICE_CAPTION).not.toContain('[Q-');
  });
});
