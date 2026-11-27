import { describe, expect, it } from 'vitest';
import type {
  GoalComparison,
  GoalName,
  PricingResult,
  ResultNumber,
  SimulationOutcome,
} from './pricing-result';
import { GOAL_NAMES } from './pricing-result';
import type { PricingVersion } from './pricing-version';
import {
  COMPUTED_LABEL,
  GOALS_TITLE,
  MODEL_SPLIT_TITLE,
  MODEL_TAG,
  PLACEHOLDER_SENTENCE,
  RESULT_BRIEF,
  RESULT_SENTENCE,
  SIMULATED_LABEL,
  SIMULATION_SOURCE,
  SOURCE_LABELS,
  SIMULATION_TAG,
  THREE_MODES_SENTENCE,
  WHY_IT_DIFFERS,
  captionParts,
  captionText,
  carShareChangePoints,
  flatBarLabel,
  formatChange,
  goalTiles,
  insightTitle,
  modeSummary,
  modelBarLabel,
  scopeLine,
  segmentShare,
  versionBarLabel,
} from './result-text';

const num = (
  value: number,
  source: ResultNumber['source'] = 'simulation',
  unit = 'travellers',
): ResultNumber => ({ value, unit, source, group: 'headline' });

const sim = (overrides: Partial<SimulationOutcome> = {}): SimulationOutcome => ({
  ruleId: 'balanced-score',
  ruleVersion: 1,
  ruleCurrent: true,
  ruleParameters: { price_weight: 0.5, time_weight: 0.5 },
  travellers: { car: 30000, ptOnly: 40000, ptBike: 2240 },
  bikeRides: num(2240, 'simulation', 'bike_rides'),
  revenue: num(0, 'simulation', 'chf'),
  cost: num(0, 'simulation', 'chf'),
  displaced: 1240,
  unserved: 0,
  createdAt: '2026-11-10T09:00:00Z',
  ...overrides,
});

const emptyGoal: GoalComparison = { model: null, modelPrices: null, flat: null, change: null };

function result(overrides: Partial<PricingResult> = {}): PricingResult {
  const goals = Object.fromEntries(GOAL_NAMES.map((name) => [name, emptyGoal])) as Record<
    GoalName,
    GoalComparison
  >;
  return {
    pricingVersionId: 'geneva-3km.v1.B',
    periodId: 'monday-08',
    simulations: { modelPrices: sim(), flat: sim({ displaced: 2115 }) },
    modelSplit: null,
    goals,
    headline: {},
    advanced: { solverStatusName: 'OPTIMAL', numbers: {} },
    coefficients: null,
    provenance: {
      packageVersion: null,
      packageCommit: null,
      gurobiVersion: '12.0.1',
      licenceKind: 'full',
      demonstratorVersion: '0.1.0',
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
    ...overrides,
  };
}

const version = {
  letter: 'B',
  goals: { ridership_weight: 8, station_balance_weight: 0.5, flat_price_per_ride_chf: 1 },
} as unknown as PricingVersion;

describe('the fixed wordings', () => {
  it('read as UX-SPEC L-3 writes them', () => {
    expect(RESULT_BRIEF).toBe('Result · pipeline step 6');
    expect(RESULT_SENTENCE).toBe(
      "The pricing model's prices for the period, and the same travellers simulated twice: with these prices and with a flat bike price.",
    );
    expect(SIMULATION_TAG).toBe('SIMULATION');
    expect(SIMULATION_SOURCE).toBe(
      'Simulated travellers · placeholder rule: half price, half travel time',
    );
    expect(PLACEHOLDER_SENTENCE).toBe(
      "A placeholder until the model's author defines the simulation.",
    );
    expect(THREE_MODES_SENTENCE).toBe(
      'The pricing model prices a shared bike only together with a public transport trip: trips by shared bike alone are not part of these results.',
    );
    expect(MODEL_TAG).toBe("PRICING MODEL'S RESULT");
    expect(MODEL_SPLIT_TITLE).toBe("The pricing model's own split");
    expect(WHY_IT_DIFFERS).toBe(
      'Why it differs from the simulated split: the pricing model spreads the travellers of each hub pair over the options with its own choice rule; the simulation sends each traveller to one option by the placeholder rule and counts the bikes and docks. The pricing model is not run with the flat price.',
    );
    expect(GOALS_TITLE).toBe('The three goals of this version');
    expect(SIMULATED_LABEL).toBe('simulated travellers · placeholder rule');
    expect(COMPUTED_LABEL).toBe("computed from the model's flows");
  });

  it('show the scope and the bar labels', () => {
    expect(scopeLine('B', 'Incentive', 'Geneva 3 km v1', 'Monday 08:00–09:00')).toBe(
      'Version B · Incentive · Geneva 3 km v1 · Monday 08:00–09:00',
    );
    expect(versionBarLabel('B')).toBe("With Version B's prices");
    expect(flatBarLabel(1)).toBe('With a flat price 1.00 CHF');
    expect(flatBarLabel(0.6)).toBe('With a flat price 0.60 CHF');
    expect(modelBarLabel('B')).toBe('Version B, pricing model');
  });

  it('carry no bracketed reference and no time limit', () => {
    const all = [
      RESULT_SENTENCE,
      SIMULATION_SOURCE,
      PLACEHOLDER_SENTENCE,
      THREE_MODES_SENTENCE,
      WHY_IT_DIFFERS,
      captionText(captionParts(sim(), sim())),
    ].join(' ');
    expect(all).not.toMatch(/\[Q-/);
    expect(all).not.toMatch(/time limit/i);
  });
});

describe('the insight title', () => {
  it('counts points of the period travellers, flat minus version', () => {
    expect(carShareChangePoints(40, 36, 100)).toBe(4);
    expect(carShareChangePoints(36, 40, 100)).toBe(-4);
    expect(carShareChangePoints(40, 40, 100)).toBe(0);
  });

  it('rounds half away from zero and never returns -0', () => {
    expect(carShareChangePoints(2.5, 0, 100)).toBe(3);
    expect(carShareChangePoints(0, 2.5, 100)).toBe(-3);
    expect(carShareChangePoints(0, 0.4, 100)).toBe(0);
    expect(Object.is(carShareChangePoints(0, 0.4, 100), 0)).toBe(true);
    expect(carShareChangePoints(10, 5, 0)).toBe(0);
  });

  it('words a positive change as fewer, a negative one as more, zero as as many', () => {
    expect(insightTitle('B', 4)).toBe(
      "With Version B's prices, 4 in 100 fewer simulated travellers take the car than with the flat price",
    );
    expect(insightTitle('B', -4)).toBe(
      "With Version B's prices, 4 in 100 more simulated travellers take the car than with the flat price",
    );
    expect(insightTitle('B', 0)).toBe(
      "With Version B's prices, as many simulated travellers take the car as with the flat price",
    );
    expect(insightTitle('B', -0)).toBe(
      "With Version B's prices, as many simulated travellers take the car as with the flat price",
    );
  });
});

describe('the caption', () => {
  it('reads exactly the wording with grouped counts', () => {
    const text = captionText(
      captionParts(
        sim({
          travellers: { car: 30000, ptOnly: 40000, ptBike: 2240 },
          unserved: 0,
          displaced: 1240,
        }),
        sim({ displaced: 2115 }),
      ),
    );
    expect(text).toBe(
      'Each of the 72 240 travellers of the period takes the option that scores best on half price, half travel time, while a bike and a dock remain at its stations. 1 240 did not get their first choice (no bike or dock); 2 115 with the flat price. Travellers left with no option: 0 · 0.',
    );
  });

  it('keeps the two unserved counts as separate parts', () => {
    const parts = captionParts(sim({ unserved: 12 }), sim({ unserved: 1500 }));
    const counts = parts.filter((part) => typeof part !== 'string');
    expect(counts).toEqual([{ unserved: 12 }, { unserved: 1500 }]);
    expect(captionText(parts)).toMatch(/no option: 12 · 1 500\.$/);
  });
});

describe('the bars', () => {
  it('give whole-percent shares of the scale', () => {
    expect(segmentShare(1, 3)).toBe(33);
    expect(segmentShare(1, 8)).toBe(13);
    expect(segmentShare(0, 0)).toBe(0);
  });

  it('name the three modes with their counts', () => {
    expect(modeSummary({ car: 1200, ptOnly: 3, ptBike: 0 })).toBe(
      'Car 1 200, Public transport 3, Public transport + shared bike 0',
    );
  });
});

describe('formatChange', () => {
  it('always shows a sign, with U+2212 for a minus and ±0 for none', () => {
    expect(formatChange(120, 0)).toBe('+120');
    expect(formatChange(-1200, 0)).toBe('−1 200');
    expect(formatChange(0, 0)).toBe('±0');
    expect(formatChange(-3, 2)).toBe('−0.03');
    expect(formatChange(15, 2)).toBe('+0.15');
  });
});

describe('the goal tiles', () => {
  const goals = (over: Partial<Record<GoalName, Partial<GoalComparison>>>) =>
    Object.fromEntries(
      GOAL_NAMES.map((name) => [name, { ...emptyGoal, ...(over[name] ?? {}) }]),
    ) as Record<GoalName, GoalComparison>;

  const full = result({
    goals: goals({
      profit: {
        modelPrices: num(4175.4, 'simulation', 'chf'),
        flat: num(3900.6, 'simulation', 'chf'),
      },
      ridership: { modelPrices: num(12000), flat: num(11000), model: num(12281, 'model') },
      stations_empty: { modelPrices: num(10), flat: num(12) },
      stations_full: { modelPrices: num(12), flat: num(14) },
      mean_bike_price: {
        modelPrices: num(0.945, 'simulation', 'chf_per_bike_leg'),
        flat: num(1, 'simulation', 'chf_per_bike_leg'),
      },
    }),
    headline: {
      profit: num(4175, 'derived', 'chf'),
      revenue: num(11544, 'derived', 'chf'),
      cost: num(7369, 'derived', 'chf'),
      bike_price_min: num(0.4, 'model', 'chf_per_bike_leg'),
      bike_price_max: num(2.1, 'model', 'chf_per_bike_leg'),
      mean_bike_price: num(0.94, 'derived', 'chf_per_bike_leg'),
      rides_under_cost: num(4667, 'derived', 'bike_rides'),
      rides_under_cost_share: num(0.38, 'derived', 'share'),
      stations_empty_end: num(10, 'derived', 'stations'),
      stations_full_end: num(12, 'derived', 'stations'),
      stations_empty_start: num(3, 'input', 'stations'),
      stations_full_start: num(4, 'input', 'stations'),
    },
  });
  const cost = { ...version, goals: { ...version.goals, cost_bike_chf: 0.6 } } as PricingVersion;

  it('come in order with their headings and weights', () => {
    const tiles = goalTiles(full, cost, 118);
    expect(tiles.map((tile) => tile.heading)).toEqual([
      'Profit',
      'Ridership',
      'Station balance',
      'Average bike price',
    ]);
    expect(tiles.map((tile) => tile.weight)).toEqual([
      'weight 1 · fixed',
      'weight 8.00',
      'weight 0.5',
      null,
    ]);
    expect(tiles.every((tile) => tile.simulatedLabel === SIMULATED_LABEL)).toBe(true);
  });

  it('show the figure, the signed change and the flat value', () => {
    const [profit, ridership, , price] = goalTiles(full, cost, 118);
    expect(profit?.figure).toBe('4 175');
    expect(profit?.unit).toBe('CHF');
    expect(profit?.flat).toBe('3 901');
    expect(profit?.change).toBe('+274');
    expect(profit?.note).toBe('revenue − cost of the simulated bike rides');
    expect(ridership?.change).toBe('+1 000');
    expect(price?.figure).toBe('0.95');
    expect(price?.change).toBe('−0.05');
    expect(price?.flat).toBe('1.00');
  });

  it('keeps figure − change = flat on the shown values', () => {
    const awkward = result({
      goals: goals({
        profit: { modelPrices: num(10.4), flat: num(4.6) },
        ridership: { modelPrices: num(2.5), flat: num(1.5) },
        mean_bike_price: { modelPrices: num(10.005), flat: num(4.996) },
        stations_empty: { modelPrices: num(3), flat: num(1) },
        stations_full: { modelPrices: num(0), flat: num(0) },
      }),
    });
    const tiles = goalTiles(awkward, cost, 10);
    for (const tile of tiles) {
      expect(tile.units).not.toBeNull();
      const units = tile.units;
      if (units === null) continue;
      expect(units.figure - units.change).toBe(units.flat);
    }
    const profit = tiles[0];
    // 10.4 → 10 and 4.6 → 5 shown; the change is 10 − 5, not round(5.8) = 6.
    expect([profit?.figure, profit?.change, profit?.flat]).toEqual(['10', '+5', '5']);
    const price = tiles[3];
    // 10.005 → 10.01 and 4.996 → 5.00 shown; the change is 5.01.
    expect([price?.figure, price?.change, price?.flat]).toEqual(['10.01', '+5.01', '5.00']);
  });

  it('writes the station balance line and the model lines', () => {
    const [profit, ridership, balance, price] = goalTiles(full, cost, 118);
    expect(balance?.figure).toBe('22');
    expect(balance?.line).toBe(
      '22 of 118 stations empty or full at 09:00 · 26 with the flat price · 7 at 08:00',
    );
    expect(balance?.model).toEqual({
      before: 'Pricing model: 22',
      tagged: false,
      after: ` · ${COMPUTED_LABEL}`,
    });
    expect(profit?.model).toEqual({
      before: `Pricing model: 4 175 CHF (revenue 11 544 − cost 7 369) · ${COMPUTED_LABEL}`,
      tagged: false,
      after: '',
    });
    expect(ridership?.model).toEqual({ before: 'Pricing model: 12 281', tagged: true, after: '' });
    expect(price?.model).toEqual({
      before: 'Pricing model: prices 0.40 to 2.10',
      tagged: true,
      after: `; mean 0.94, 4 667 rides (38 %) under the cost of 0.60 · ${COMPUTED_LABEL}`,
    });
  });

  it('shows a dash for a missing simulated number and omits missing model parts', () => {
    const sparse = result({ goals: goals({}), headline: { profit: num(5, 'derived', 'chf') } });
    const tiles = goalTiles(sparse, cost, 118);
    expect(tiles.map((tile) => tile.figure)).toEqual(['—', '—', '—', '—']);
    expect(tiles.every((tile) => tile.change === null && tile.flat === null)).toBe(true);
    expect(tiles[0]?.model?.before).toBe(`Pricing model: 5 CHF · ${COMPUTED_LABEL}`);
    expect(tiles[1]?.model).toBeNull();
    expect(tiles[2]?.model).toBeNull();
    expect(tiles[3]?.model).toBeNull();
    expect(tiles[2]?.line).toBeNull();
  });

  it('puts the blue tag on model-source numbers only', () => {
    for (const tile of goalTiles(full, cost, 118)) {
      if (tile.model?.tagged === true) expect(tile.heading).toMatch(/Ridership|Average bike price/);
    }
    expect(goalTiles(full, cost, 118).map((tile) => tile.figureTagged)).toEqual([
      false,
      false,
      false,
      false,
    ]);
  });
});

describe('the source labels', () => {
  it('name the six sources, the three the screen tags in its words', () => {
    expect(SOURCE_LABELS).toEqual({
      simulation: SIMULATION_SOURCE,
      model: MODEL_TAG,
      derived: COMPUTED_LABEL,
      input: 'input',
      package_summary: 'package_summary',
      trip_planner: 'trip_planner',
    });
  });
});
