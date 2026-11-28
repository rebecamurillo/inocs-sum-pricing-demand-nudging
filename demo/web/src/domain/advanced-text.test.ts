import { describe, expect, it } from 'vitest';
import {
  BIKE_RIDE_SENTENCE,
  aboutRows,
  coefficientsText,
  earlierSimulations,
  objectiveRows,
  packageSummaryRows,
  parameterRows,
  ruleLine,
  simulationRows,
  solverRows,
  solverStatusText,
} from './advanced-text';
import type {
  ResultNumber,
  ResultProvenance,
  SimulationOutcome,
  StoredSimulation,
} from './pricing-result';

const num = (value: number): ResultNumber => ({
  value,
  unit: 'x',
  source: 'model',
  group: 'advanced',
});

const outcome = (
  displaced: number,
  bikeRides: number,
  revenue: number,
  cost: number,
): SimulationOutcome => ({
  ruleId: 'balanced-score',
  ruleVersion: 1,
  ruleCurrent: true,
  ruleParameters: { price_weight: 0.5, time_weight: 0.5 },
  travellers: { car: 1, ptOnly: 2, ptBike: 3 },
  bikeRides: num(bikeRides),
  revenue: num(revenue),
  cost: num(cost),
  displaced,
  unserved: 0,
  createdAt: '2026-11-10T09:00:00+00:00',
});

const sampleProvenance: ResultProvenance = {
  packageVersion: '0.4.2',
  packageCommit: '0123456789abcdef0123456789abcdef01234567',
  gurobiVersion: '12.0.1',
  licenceKind: 'full',
  demonstratorVersion: '0.1.0',
  timetableOperator: 'tpg',
  timetableValidFrom: '2024-12-15',
  timetableValidTo: '2025-12-13',
  routingDate: '2025-03-10',
  routingTime: '08:30:00',
  routingDateProvisional: true,
  bikeStationsSourceUrl: 'https://stables.donkey.bike/api/public/gbfs/2/donkey_ge/gbfs.json',
  bikeStationsFetchedAt: '2026-11-10T00:00:00+00:00',
  simulations: [
    {
      priceScheme: 'model_prices',
      ruleId: 'balanced-score',
      ruleVersion: 1,
      createdAt: '2026-11-10T09:00:00+00:00',
    },
  ],
};

const GUROBI_STATUSES = [
  'OPTIMAL',
  'SUBOPTIMAL',
  'TIME_LIMIT',
  'INFEASIBLE',
  'INF_OR_UNBD',
  'INTERRUPTED',
  'NODE_LIMIT',
  'SOLUTION_LIMIT',
  'ITERATION_LIMIT',
  'WORK_LIMIT',
  'MEM_LIMIT',
  'USER_OBJ_LIMIT',
  'NUMERIC',
];

describe('solverStatusText', () => {
  it('words the three known statuses and lower-cases the others', () => {
    expect(solverStatusText('OPTIMAL')).toBe('optimal');
    expect(solverStatusText('SUBOPTIMAL')).toBe('suboptimal');
    expect(solverStatusText('TIME_LIMIT')).toBe('stopped with a solution');
    expect(solverStatusText('INF_OR_UNBD')).toBe('inf or unbd');
  });

  it('never produces the words "time limit" for any status', () => {
    for (const status of GUROBI_STATUSES) {
      expect(solverStatusText(status)).not.toMatch(/time limit/i);
    }
  });
});

describe('objectiveRows', () => {
  it('lists the four terms and the tagged objective value', () => {
    const rows = objectiveRows({
      solverStatusName: 'OPTIMAL',
      numbers: {
        objective_term_ridership: num(98765.4),
        objective_term_revenue: num(11544),
        objective_term_cost: num(7369),
        objective_term_station_balance: num(-120.6),
        objective_value: num(1234567.4),
      },
    });

    expect(rows.map((row) => [row.label, row.value, row.tag ?? null])).toEqual([
      ['Ridership term', '98 765', null],
      ['+ Revenue', '11 544', null],
      ['− Cost', '7 369', null],
      ['+ Station balance term', '-121', null],
      ['= Objective value', '1 234 567', 'model'],
    ]);
  });

  it('keeps only the objective value when the residual check failed', () => {
    const rows = objectiveRows({
      solverStatusName: 'OPTIMAL',
      numbers: { objective_value: num(500) },
    });

    expect(rows.map((row) => row.label)).toEqual(['= Objective value']);
    expect(rows[0]?.tag).toBe('model');
  });

  it('shows a dash for an objective value the API left out', () => {
    expect(objectiveRows({ solverStatusName: 'OPTIMAL', numbers: {} })[0]?.value).toBe('—');
  });
});

describe('solverRows', () => {
  const advanced = (name: string, limit: number) => ({
    solverStatusName: name,
    numbers: {
      solution_time_s: num(12.345),
      gap_pct: num(0.5),
      time_limit_reached: num(limit),
    },
  });

  it('words the time, the gap, the status, the counts and the stop', () => {
    const rows = solverRows(advanced('OPTIMAL', 0), 1412, 3000);

    expect(rows.map((row) => [row.label, row.value])).toEqual([
      ['Solution time', '12.3 s'],
      ['Optimality gap', '0.50 %'],
      ['Status', 'optimal'],
      ['Hub pairs · bike options offered', '1 412 · 3 000'],
      ['Stopped before the search ended', 'no'],
    ]);
  });

  it('says yes without the words "time limit" when the solve stopped', () => {
    const rows = solverRows(advanced('TIME_LIMIT', 1), 10, 20);

    expect(rows.map((row) => row.value)).toContain('yes');
    expect(rows.map((row) => `${row.label} ${row.value}`).join(' ')).not.toMatch(/time limit/i);
  });

  it('shows a dash for what the API or the screen has not read', () => {
    const rows = solverRows({ solverStatusName: 'OPTIMAL', numbers: {} }, null, 5);

    expect(rows.map((row) => row.value)).toEqual(['—', '—', 'optimal', '—', '—']);
  });
});

describe('simulation rows and rule line', () => {
  const modelPrices = outcome(1240, 12000, 11544.4, 7369);
  const flat = outcome(2115, 11000, 11269.2, 7369);

  it('words the rule with its parameters', () => {
    expect(ruleLine(modelPrices)).toBe(
      'Rule: balanced-score v1 · price weight 0.5 · time weight 0.5 · placeholder',
    );
  });

  it('shows both schemes in one row each', () => {
    const rows = simulationRows(modelPrices, flat);

    expect(rows.map((row) => row.label)).toEqual([
      'Bike rides · with these prices / with the flat price',
      'Revenue − cost · with these prices / with the flat price',
      'Did not get their first choice · left with no option · with these prices / with the flat price',
    ]);
    expect(rows[0]?.value).toBe('12 000 / 11 000');
    expect(rows[1]?.value).toBe('4 175 / 3 900');
    expect(rows[2]?.value).toBe('1 240 · 0 / 2 115 · 0');
  });

  it('states what a bike ride is', () => {
    expect(BIKE_RIDE_SENTENCE).toBe(
      'A bike ride is one bike leg; an option with two bike legs counts two rides',
    );
  });
});

describe('earlierSimulations', () => {
  const stored = (
    overrides: Partial<StoredSimulation> & Pick<StoredSimulation, 'ruleCurrent'>,
  ): StoredSimulation => ({
    periodId: 'monday-08',
    priceScheme: 'model_prices',
    ruleId: 'balanced-score',
    ruleVersion: 1,
    ruleParameters: { price_weight: 0.5, time_weight: 0.5 },
    createdAt: '2026-11-10T09:00:00+00:00',
    ...overrides,
  });

  it('lists only the simulations of an earlier rule, with scheme and date', () => {
    const lines = earlierSimulations([
      stored({ ruleCurrent: true }),
      stored({
        ruleCurrent: false,
        ruleVersion: 0,
        priceScheme: 'flat',
        ruleParameters: { price_weight: 1, time_weight: 0 },
      }),
    ]);

    expect(lines).toEqual([
      'balanced-score v0 · price weight 1 · time weight 0 · placeholder · with the flat price · 10 Nov 2026',
    ]);
  });

  it('is empty when every stored simulation uses the current rule', () => {
    expect(earlierSimulations([stored({ ruleCurrent: true })])).toEqual([]);
    expect(earlierSimulations([])).toEqual([]);
  });
});

describe('packageSummaryRows', () => {
  it('shows both averages with two decimals and a dash for an absent one', () => {
    const numbers = {
      package_avg_bike_price_multimodal: num(0.9456),
    };

    expect(
      packageSummaryRows({ solverStatusName: 'OPTIMAL', numbers }).map((row) => [
        row.label,
        row.value,
      ]),
    ).toEqual([
      ['Avg Bike Price (Multimodal, Flow ≥ 1)', '0.95 CHF'],
      ['Avg Bike Price (for all offered arcs)', '—'],
    ]);
  });
});

describe('parameterRows and coefficientsText', () => {
  const advanced = {
    solverStatusName: 'OPTIMAL',
    numbers: {
      parameter_cost_bike: num(0.6),
      parameter_P_bar: num(0.6),
      parameter_ridership_weight: num(8),
      parameter_theta: num(0.5),
      parameter_pt_price: num(2),
      parameter_parking_fee: num(2.8),
      parameter_max_displayed_alternatives: num(10),
    },
  };

  it('lists the package names with their values and the flat price', () => {
    const rows = parameterRows(advanced, 1);

    expect(rows.map((row) => [row.label, row.value])).toEqual([
      ['cost_bike', '0.60'],
      ['P_bar', '0.60'],
      ['ridership_weight', '8.0'],
      ['theta', '0.5'],
      ['pt_price', '2.00'],
      ['parking_fee', '2.80'],
      ['max_displayed_alternatives', '10'],
      ['Flat price for the comparison', '1.00 CHF per ride · traveller simulation only'],
    ]);
    expect(rows.slice(0, 7).every((row) => row.code === true)).toBe(true);
  });

  it('shows a dash for a parameter the API left out', () => {
    const rows = parameterRows({ solverStatusName: 'OPTIMAL', numbers: {} }, 1);

    expect(rows[0]?.value).toBe('—');
  });

  it('says where the coefficients come from, or that the package does not expose them', () => {
    expect(coefficientsText({ ASC_PT: num(-0.756) })).toBe(
      'Read from the package source (optimizer/solver.py), fixed inside the model',
    );
    expect(coefficientsText(null)).toBe('Fixed inside the model, not exposed by the package.');
  });
});

describe('aboutRows', () => {
  const provenance = sampleProvenance;

  it('words every line of the block', () => {
    const rows = aboutRows(provenance, 'OPTIMAL');

    expect(rows.map((row) => [row.label, row.value])).toEqual([
      ['Pricing model', 'package 0.4.2 · commit 0123456'],
      ['Solver', 'Gurobi 12.0.1 · full licence · status optimal'],
      [
        'Timetable',
        'tpg · valid 15 Dec 2024 to 13 Dec 2025 · routes planned for Monday 10 March 2025, arrive by 08:30 · provisional',
      ],
      ['Bike stations', 'stables.donkey.bike · fetched 10 Nov 2026'],
      ['Simulation', 'balanced-score v1 · 10 Nov 2026'],
      ['Demonstrator', '0.1.0'],
    ]);
  });

  it('reads "not recorded" for every missing value', () => {
    const rows = aboutRows(
      {
        ...provenance,
        packageVersion: null,
        packageCommit: null,
        licenceKind: 'limited',
        timetableOperator: null,
        timetableValidFrom: null,
        timetableValidTo: null,
        routingDate: null,
        routingTime: null,
        routingDateProvisional: null,
        bikeStationsSourceUrl: null,
        bikeStationsFetchedAt: null,
        simulations: [],
      },
      'TIME_LIMIT',
    );

    expect(rows.map((row) => row.value)).toEqual([
      'package not recorded · commit not recorded',
      'Gurobi 12.0.1 · size-limited licence · status stopped with a solution',
      'not recorded · valid not recorded to not recorded · routes planned for not recorded',
      'not recorded · fetched not recorded',
      'not recorded',
      '0.1.0',
    ]);
  });

  it('keeps a source address that does not parse as written', () => {
    const rows = aboutRows({ ...provenance, bikeStationsSourceUrl: 'not a url' }, 'OPTIMAL');

    expect(rows[3]?.value).toBe('not a url · fetched 10 Nov 2026');
  });

  it('names the latest simulation by its instant, a zero fraction of a second left out or not', () => {
    const rows = aboutRows(
      {
        ...provenance,
        simulations: [
          {
            priceScheme: 'model_prices',
            ruleId: 'balanced-score',
            ruleVersion: 1,
            createdAt: '2026-11-09T23:59:59Z',
          },
          {
            priceScheme: 'flat',
            ruleId: 'balanced-score',
            ruleVersion: 2,
            createdAt: '2026-11-09T23:59:59.5Z',
          },
        ],
      },
      'OPTIMAL',
    );

    expect(rows[4]?.value).toBe('balanced-score v2 · 9 Nov 2026');
  });

  it('shows no "time limit" or bracketed reference in any produced text', () => {
    const texts = [
      ...aboutRows(provenance, 'TIME_LIMIT'),
      ...solverRows(
        { solverStatusName: 'TIME_LIMIT', numbers: { time_limit_reached: num(1) } },
        1,
        1,
      ),
    ].map((row) => `${row.label} ${row.value}`);

    for (const text of texts) {
      expect(text).not.toMatch(/time limit|\[Q-/i);
    }
  });
});
