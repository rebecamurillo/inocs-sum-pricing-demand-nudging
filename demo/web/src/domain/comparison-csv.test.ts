import { describe, expect, it } from 'vitest';
import { buildComparisonCsv, comparisonCsvFileName } from './comparison-csv';
import type { Comparison, ComparisonRow, FlatReference } from './comparison';
import type { ResultNumber } from './pricing-result';

const BASE_GOALS: Record<string, number> = {
  cost_bike_chf: 0.6,
  lowest_price_chf: 0.4,
  ridership_weight: 10,
  station_balance_weight: 5,
  flat_price_per_ride_chf: 1,
  pt_fare_chf: 2,
  car_parking_fee_chf: 2.8,
  max_displayed_options: 3,
};

const number = (
  value: number,
  source: ResultNumber['source'],
  unit = 'none',
  group: ResultNumber['group'] = 'headline',
): ResultNumber => ({ value, unit, source, group });

/** A comparison of versions named "Version {letter}", with these goals changed from the base. */
function comparisonOf(goals: Record<string, Record<string, number>>): Comparison {
  const letters = Object.keys(goals);
  const goalsOf = (letter: string) => ({ ...BASE_GOALS, ...goals[letter] });
  const flatOf = (letter: string) => goalsOf(letter).flat_price_per_ride_chf ?? 1;
  const flatReferences: FlatReference[] = [...new Set(letters.map(flatOf))].map((flatPrice) => ({
    id: `flat-${String(flatPrice)}`,
    letters: letters.filter((letter) => flatOf(letter) === flatPrice),
    flatPrice,
    fare: 2,
    parkingFee: 2.8,
    costBike: 0.6,
    ruleCurrent: true,
    ruleVersion: 2,
  }));
  const at = (letter: string) => letter.charCodeAt(0) - 'A'.charCodeAt(0);
  const row = (
    key: string,
    make: (letter: string) => ResultNumber,
    flat?: ResultNumber,
  ): ComparisonRow => ({
    key,
    values: Object.fromEntries(letters.map((letter) => [letter, make(letter)])),
    changes: {},
    flats: flat === undefined ? {} : Object.fromEntries(flatReferences.map((r) => [r.id, flat])),
    best: [],
  });
  const sim = (value: number, unit: string) => number(value, 'simulation', unit);
  const model = (value: number, unit = 'none', group: ResultNumber['group'] = 'headline') =>
    number(value, 'model', unit, group);
  const derived = (value: number, unit: string) => number(value, 'derived', unit);
  const differing = Object.keys(BASE_GOALS).filter(
    (key) => new Set(letters.map((letter) => goalsOf(letter)[key])).size > 1,
  );
  return {
    instanceVersion: { id: 'geneva-3km.v1', name: 'Geneva 3 km v1' },
    period: { id: 'monday', name: 'Monday 08:00–09:00' },
    versions: letters.map((letter) => ({
      id: `geneva-3km.v1.${letter}`,
      letter,
      name: `Version ${letter}`,
      goals: Object.fromEntries(
        Object.entries(goalsOf(letter)).map(([key, value]) => [key, number(value, 'input')]),
      ),
      flatReference: `flat-${String(flatOf(letter))}`,
      packageCommit: null,
      packageFingerprint: 'fp',
      simulations: [],
      solveKey: letter,
    })),
    flatReferences,
    identicalSolves: [],
    pairDifferences: { a: 'A', b: 'B', pairs: [] },
    hubDifferences: [],
    groups: [
      {
        name: 'simulated',
        rows: [
          row('share_car', (l) => sim(0.5 - 0.08 * at(l), 'share'), sim(0.55, 'share')),
          row('profit', (l) => sim(4000 + 300 * at(l), 'chf'), sim(3900, 'chf')),
        ],
      },
      {
        name: 'model',
        rows: [
          row('share_car', (l) => model(0.45 - 0.05 * at(l), 'share')),
          row('bike_price_min', () => model(0.6, 'chf')),
          row('bike_price_max', () => model(2.4, 'chf')),
        ],
      },
      {
        name: 'derived',
        rows: [
          row('profit', (l) => derived(4175 + 1000 * at(l), 'chf')),
          row('mean_bike_price', () => derived(1.1, 'chf')),
        ],
      },
      {
        name: 'goals_that_differ',
        rows: differing.map((key) => row(key, (l) => number(goalsOf(l)[key] ?? 0, 'input'))),
      },
      {
        name: 'solver',
        rows: [
          row('solution_time_s', () => model(12.34, 'seconds', 'advanced')),
          row('gap_pct', () => model(0.5, 'percent', 'advanced')),
          row('hub_pairs_with_bike_option', () => model(60, 'hub_pairs', 'advanced')),
          row('bike_options_offered', () => model(240, 'options', 'advanced')),
        ],
      },
    ],
  };
}

const three = (): Comparison =>
  comparisonOf({ A: {}, B: { ridership_weight: 20 }, C: { lowest_price_chf: 0.9 } });

/** The records of a file, split at the line ends (each ends with one). */
const records = (text: string): string[] => {
  expect(text.endsWith('\r\n')).toBe(true);
  return text.slice(0, -2).split('\r\n');
};
/** The fields of one record, with RFC 4180 quotes undone. */
const fields = (line: string | undefined): string[] =>
  [...(line ?? '').matchAll(/("(?:[^"]|"")*"|[^,]*)(?:,|$)/g)]
    .slice(0, -1)
    .map(([, field = '']) =>
      field.startsWith('"') ? field.slice(1, -1).replaceAll('""', '"') : field,
    );
const find = (lines: readonly string[], first: string): string[] =>
  fields(lines.find((line) => line.startsWith(`${first},`)));

describe('buildComparisonCsv', () => {
  it('opens with the names, the instance version, the period and the eight goals', () => {
    const lines = records(buildComparisonCsv(three(), false));
    expect(lines.slice(0, 3)).toEqual([
      'version,Version A · Version A,Version B · Version B,Version C · Version C',
      'instance version,Geneva 3 km v1 (geneva-3km.v1),Geneva 3 km v1 (geneva-3km.v1),Geneva 3 km v1 (geneva-3km.v1)',
      'period,Monday 08:00–09:00,Monday 08:00–09:00,Monday 08:00–09:00',
    ]);
    expect(lines.slice(3, 11).map((line) => fields(line)[0])).toEqual([
      'cost of one ride (CHF)',
      'lowest price of a ride (CHF)',
      'ridership weight',
      'station balance weight',
      'flat price per ride (CHF)',
      'public transport fare (CHF)',
      'car parking fee (CHF)',
      'options shown per hub pair',
    ]);
    expect(find(lines, 'lowest price of a ride (CHF)')[3]).toBe('0.90');
    expect(find(lines, 'ridership weight')[2]).toBe('20');
    expect(lines[11]).toBe('');
  });

  it('writes a dash for a goal a version does not have', () => {
    const comparison = three();
    const [first, ...rest] = comparison.versions;
    if (first === undefined) throw new Error('no version');
    const { cost_bike_chf: removed, ...goals } = first.goals;
    expect(removed).toBeDefined();
    const lines = records(
      buildComparisonCsv({ ...comparison, versions: [{ ...first, goals }, ...rest] }, false),
    );
    expect(find(lines, 'cost of one ride (CHF)')[1]).toBe('—');
  });

  it('heads the table with the flat column, the versions and source', () => {
    const lines = records(buildComparisonCsv(three(), false));
    expect(lines[12]).toBe(
      'group,row,Flat price 1.00 CHF,Version A · Version A,Version B · Version B,Version C · Version C,source',
    );
  });

  it('puts each flat column before the versions it serves', () => {
    const comparison = comparisonOf({ A: {}, B: {}, C: { flat_price_per_ride_chf: 1.5 } });
    const lines = records(buildComparisonCsv(comparison, false));
    const head = fields(lines.find((line) => line.startsWith('group,row,')));
    expect(head).toEqual([
      'group',
      'row',
      'Flat price 1.00 CHF · for A, B',
      'Version A · Version A',
      'Version B · Version B',
      'Flat price 1.50 CHF · for C',
      'Version C · Version C',
      'source',
    ]);
  });

  it('writes the rows of the screen, the solver only with the Advanced view', () => {
    const off = records(buildComparisonCsv(three(), false));
    expect(off.some((line) => line.startsWith('What the solver maximised'))).toBe(false);
    const on = records(buildComparisonCsv(three(), true));
    expect(on.length).toBeGreaterThan(off.length);
    const solver = on.filter((line) => line.startsWith('What the solver maximised'));
    expect(solver.map((line) => fields(line)[1])).toContain('Solution time (s)');
    expect(solver.map((line) => fields(line)[1])).toContain('Hub pairs · bike options offered');
    expect(find(on, 'What the solver maximised and how it ran').length).toBeGreaterThan(3);
  });

  it('writes plain figures, a dash where the screen has one and the source of each row', () => {
    const lines = records(buildComparisonCsv(three(), true));
    const row = (group: string, label: string): string[] =>
      fields(lines.find((line) => line.startsWith(`${group},${label},`)));
    expect(row('Simulated travellers', 'Car (%)').at(-1)).toBe(
      'Simulated travellers · placeholder rule: half price, half travel time',
    );
    expect(row('Simulated travellers', 'Car (%)')[2]).toBe('55');
    expect(row("Pricing model's result", 'Car (%)').at(-1)).toBe("PRICING MODEL'S RESULT");
    expect(row("Pricing model's result", 'Car (%)')[2]).toBe('—');
    expect(row("Computed from the model's flows", 'Profit (CHF)').at(-1)).toBe(
      "computed from the model's flows",
    );
    expect(row("Computed from the model's flows", 'Mean bike price (CHF)')[3]).toBe('1.10');
    expect(row("Pricing model's result", 'Range of the prices offered (CHF)')[3]).toBe(
      '0.60 – 2.40',
    );
    expect(row('Simulated travellers', 'Profit (CHF)')[2]).toBe('3900');
    expect(row('What the solver maximised and how it ran', 'Solution time (s)')[3]).toBe('12.3');
    expect(row('What the solver maximised and how it ran', 'Optimality gap (%)')[3]).toBe('0.50');
    expect(
      row('What the solver maximised and how it ran', 'Hub pairs · bike options offered').at(-1),
    ).toBe("PRICING MODEL'S RESULT");
    expect(row('Pricing goals that differ', 'Ridership weight')[2]).toBe('—');
  });

  it('writes the small change figures nowhere', () => {
    const text = buildComparisonCsv(three(), false);
    expect(text).not.toMatch(/pts|±0/);
  });

  it('quotes a name holding a comma, a quote or a line break, and nothing else', () => {
    const comparison = three();
    const [first, second, ...rest] = comparison.versions;
    if (first === undefined || second === undefined) throw new Error('no version');
    const named: Comparison = {
      ...comparison,
      versions: [{ ...first, name: 'Low, "cheap"' }, { ...second, name: 'Two\nlines' }, ...rest],
    };
    const text = buildComparisonCsv(named, false);
    expect(
      text.startsWith('version,"Version A · Low, ""cheap""","Version B · Two\nlines",Version C'),
    ).toBe(true);
    expect(text).toContain(',Version C · Version C,source\r\n');
  });
});

describe('comparisonCsvFileName', () => {
  it('names the instance version and the letters', () => {
    expect(comparisonCsvFileName(three())).toBe('comparison-geneva-3km.v1-ABC.csv');
  });
});
