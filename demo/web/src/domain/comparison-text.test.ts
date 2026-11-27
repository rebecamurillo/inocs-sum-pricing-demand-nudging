import { describe, expect, it } from 'vitest';
import {
  buildsNotice,
  changePoints,
  flatColumnHeader,
  flatPill,
  insightTitle,
  olderRuleNotice,
  pillLabel,
  tableGroups,
} from './comparison-text';
import { comparisonColumns, type Comparison, type FlatReference } from './comparison';
import type { ResultNumber } from './pricing-result';

const sim = (value: number, unit = 'share'): ResultNumber => ({
  value,
  unit,
  source: 'simulation',
  group: 'headline',
});

type Figures = Record<string, [car: number, profit: number, stations: number]>;

/** A comparison of versions with these car shares, profits and stations empty or full. */
function comparisonOf(figures: Figures): Comparison {
  const letters = Object.keys(figures);
  const row = (key: string, at: 0 | 1 | 2, unit: string) => ({
    key,
    values: Object.fromEntries(letters.map((l) => [l, sim(figures[l]?.[at] ?? 0, unit)])),
    changes: {},
    flats: {},
    best: [],
  });
  return {
    instanceVersion: { id: 'geneva-3km.v1', name: 'Geneva 3 km v1' },
    period: { id: 'monday', name: 'Monday 08:00–09:00' },
    versions: [],
    flatReferences: [],
    identicalSolves: [],
    groups: [
      {
        name: 'simulated',
        rows: [
          row('share_car', 0, 'share'),
          row('profit', 1, 'chf'),
          row('stations_empty_or_full', 2, 'stations'),
        ],
      },
    ],
  };
}

describe('the insight title', () => {
  it('names a different winner for each goal, worded as simulated', () => {
    const title = insightTitle(
      comparisonOf({ A: [0.5, 100, 9], B: [0.3, 90, 8], C: [0.4, 120, 7] }),
    );
    expect(title).toBe(
      'In the simulation, Version B has the lowest car share; Version C has the highest profit and the fewest stations empty or full',
    );
  });

  it('joins the clauses of one version', () => {
    const title = insightTitle(comparisonOf({ A: [0.5, 100, 9], B: [0.3, 120, 7] }));
    expect(title).toBe(
      'In the simulation, Version B has the lowest car share, the highest profit and the fewest stations empty or full',
    );
  });

  it('names tied versions together', () => {
    const title = insightTitle(
      comparisonOf({ A: [0.5, 100, 9], B: [0.3, 90, 8], C: [0.3, 120, 8], D: [0.6, 80, 12] }),
    );
    expect(title).toBe(
      'In the simulation, Versions B and C have the lowest car share and the fewest stations empty or full; Version C has the highest profit',
    );
  });

  it('names three tied versions with a comma and "and"', () => {
    const title = insightTitle(
      comparisonOf({ A: [0.5, 100, 9], B: [0.3, 90, 8], C: [0.3, 90, 8], D: [0.3, 90, 8] }),
    );
    expect(title).toContain('Versions B, C and D have the lowest car share');
  });

  it('says the versions are level when nothing separates them', () => {
    expect(insightTitle(comparisonOf({ A: [0.5, 100, 9], B: [0.5, 100, 9] }))).toBe(
      'In the simulation, the versions are level on car share, profit and stations empty or full',
    );
  });
});

const reference = (id: string, over: Partial<FlatReference> = {}): FlatReference => ({
  id,
  letters: ['B'],
  flatPrice: 1,
  fare: 2,
  parkingFee: 2.8,
  costBike: 0.6,
  ruleCurrent: true,
  ruleVersion: 1,
  ...over,
});

describe('the flat-column headers', () => {
  it('reads the amount alone with one column', () => {
    const one = reference('a', { letters: ['A', 'B'] });
    expect(flatColumnHeader(one, [one])).toBe('Flat price 1.00 CHF');
    expect(flatPill(one)).toBe('Flat price 1.00 CHF · simulated · always shown');
  });

  it('adds the letters served when there are several columns', () => {
    const a = reference('a', { letters: ['B'] });
    const b = reference('b', { letters: ['D'], flatPrice: 1.5 });
    expect(flatColumnHeader(a, [a, b])).toBe('Flat price 1.00 CHF · for B');
    expect(flatColumnHeader(b, [a, b])).toBe('Flat price 1.50 CHF · for D');
  });

  it('names the fare, the parking fee and the cost of one ride when they differ', () => {
    const a = reference('a', { letters: ['A', 'B'] });
    const fare = reference('b', { letters: ['C'], fare: 2.5 });
    expect(flatColumnHeader(fare, [a, fare])).toBe('Flat price 1.00 CHF · fare 2.50 · for C');
    const parking = reference('c', { letters: ['C'], parkingFee: 3 });
    expect(flatColumnHeader(parking, [a, parking])).toBe(
      'Flat price 1.00 CHF · parking fee 3.00 · for C',
    );
    const cost = reference('d', { letters: ['B'], costBike: 0.9 });
    expect(flatColumnHeader(cost, [a, cost])).toBe('Flat price 1.00 CHF · cost 0.90 · for B');
    const all = reference('e', { letters: ['D'], fare: 2.5, parkingFee: 3, costBike: 0.9 });
    expect(flatColumnHeader(all, [a, all])).toBe(
      'Flat price 1.00 CHF · fare 2.50 · parking fee 3.00 · cost 0.90 · for D',
    );
  });
});

describe('the small wordings', () => {
  it('writes the pills, the notices and the changes as the spec words them', () => {
    expect(pillLabel('B', 'Cheaper', true)).toBe('✓ B · Cheaper');
    expect(pillLabel('B', 'Cheaper', false)).toBe('B · Cheaper');
    expect(buildsNotice(['aaaaaaa', 'bbbbbbb'])).toBe(
      "These versions were run with different builds of the pricing model (package commits aaaaaaa and bbbbbbb): a difference can come from the model's code, not only from the goals.",
    );
    expect(buildsNotice(['a', 'b', 'c'])).toContain('(package commits a, b and c)');
    expect(olderRuleNotice('B', 1)).toBe(
      'Version B was simulated with an older rule (v1): its simulated numbers are greyed. Simulate it again to compare like with like.',
    );
    expect(changePoints(1)).toBe('+1 pt');
    expect(changePoints(-3)).toBe('−3 pts');
    expect(changePoints(0)).toBe('±0 pts');
  });
});

describe('the table', () => {
  it('shows — in flat columns outside the simulated group and bolds the differing goal', () => {
    const base = comparisonOf({ A: [0.5, 100, 9], B: [0.3, 90, 8], C: [0.4, 120, 7] });
    const goal = (value: number): ResultNumber => ({
      value,
      unit: 'chf',
      source: 'input',
      group: 'headline',
    });
    const found: Comparison = {
      ...base,
      versions: ['A', 'B', 'C'].map((letter) => ({
        id: `geneva-3km.v1.${letter}`,
        letter,
        name: `Version ${letter}`,
        goals: {},
        flatReference: 'f',
        packageCommit: null,
        packageFingerprint: '',
        simulations: [],
        solveKey: letter,
      })),
      flatReferences: [reference('f', { letters: ['A', 'B', 'C'] })],
      groups: [
        ...base.groups,
        {
          name: 'model',
          rows: [
            {
              key: 'ridership',
              values: { A: goal(1), B: goal(2), C: goal(3) },
              changes: {},
              flats: {},
              best: ['C'],
            },
          ],
        },
        {
          name: 'goals_that_differ',
          rows: [
            {
              key: 'cost_bike_chf',
              values: { A: goal(0.6), B: goal(0.6), C: goal(0.9) },
              changes: {},
              flats: {},
              best: [],
            },
          ],
        },
      ],
    };
    const columns = comparisonColumns(found);
    const groups = tableGroups(found, columns, false);
    expect(groups.map((group) => group.title)).toEqual([
      'Simulated travellers',
      "Pricing model's result",
      'Pricing goals that differ',
    ]);
    const model = groups[1]?.rows[0];
    expect(model?.cells.map((cell) => cell.text)).toEqual(['—', '1', '2', '3']);
    expect(model?.cells.map((cell) => cell.best)).toEqual([false, false, false, true]);
    const goals = groups[2]?.rows[0];
    expect(goals?.cells.map((cell) => [cell.text, cell.bold])).toEqual([
      ['—', false],
      ['0.60 CHF', false],
      ['0.60 CHF', false],
      ['0.90 CHF', true],
    ]);
    const car = groups[0]?.rows[0];
    expect(car?.cells.map((cell) => cell.text)).toEqual(['—', '50 %', '30 %', '40 %']);
  });
});

describe('the solver rows', () => {
  it('names every status code as L-3 does, not only optimal, time limit and suboptimal', () => {
    const code = (value: number): ResultNumber => ({
      value,
      unit: 'status',
      source: 'model',
      group: 'advanced',
    });
    const found: Comparison = {
      ...comparisonOf({ A: [0.5, 100, 9], B: [0.3, 90, 8] }),
      versions: ['A', 'B'].map((letter) => ({
        id: `geneva-3km.v1.${letter}`,
        letter,
        name: `Version ${letter}`,
        goals: {},
        flatReference: 'f',
        packageCommit: null,
        packageFingerprint: '',
        simulations: [],
        solveKey: letter,
      })),
      flatReferences: [reference('f', { letters: ['A', 'B'] })],
      groups: [
        {
          name: 'solver',
          rows: [
            {
              key: 'solver_status',
              values: { A: code(11), B: code(0) },
              changes: {},
              flats: {},
              best: [],
            },
          ],
        },
      ],
    };
    const groups = tableGroups(found, comparisonColumns(found), true);
    expect(groups[0]?.rows[0]?.cells.map((cell) => cell.text)).toEqual([
      '—',
      'interrupted',
      'unknown',
    ]);
  });
});
