import { describe, expect, it } from 'vitest';
import {
  ALL_FIELDS,
  COST_FIELD,
  KEPT_FIELDS,
  RIDERSHIP_FIELD,
  costMessage,
  discardQuestion,
  exampleRide,
  failedFields,
  goalBars,
  goalText,
  numberLine,
  parseGoalInput,
  pricingBannerSentences,
  pricingBreadcrumb,
  pricingMenuState,
  pricingPrimaryState,
  pricingRowLetter,
  pricingVersionName,
  rankingLine,
  ruleLines,
  step4Heading,
  thisRunLine,
} from './pricing-goals-text';
import type { PricingGoals, PricingRule, PricingVersion } from './pricing-version';
import type { SystemStatus } from './system-status';

const defaults: PricingGoals = {
  cost_bike_chf: 0.6,
  lowest_price_chf: 0.6,
  ridership_weight: 8,
  station_balance_weight: 0.5,
  pt_fare_chf: 2,
  car_parking_fee_chf: 2.8,
  max_displayed_options: 10,
  flat_price_per_ride_chf: 1,
};

const rule = (name: string, field: string, passed: boolean, message: string): PricingRule => ({
  rule: name,
  field,
  passed,
  message,
});

function status(
  reasons: {
    component: 'solver' | 'package' | 'runner' | 'storage' | 'tripPlanner';
    reason: string;
  }[],
  solver: 'limited' | 'unavailable' | 'available' = 'available',
): SystemStatus {
  const allowed = { allowed: true, reasons: [] };
  return {
    components: [{ name: 'solver', state: solver, reason: null }],
    canBuildInstances: allowed,
    canRunPricing: { allowed: reasons.length === 0, reasons },
    canSimulate: allowed,
  };
}

describe('costMessage', () => {
  it('covers the cost above it, with the margin', () => {
    const covers = costMessage(0.6, 0.8);
    expect(covers.tone).toBe('covers');
    expect(covers.text).toBe(
      'Every ride covers its cost. At the lowest price the operator still earns CHF 0.20 on a ride.',
    );
  });

  it('breaks even when the two are equal, however the floats fall', () => {
    const equal = costMessage(0.6, 0.6);
    expect(equal.tone).toBe('break-even');
    expect(equal.text).toBe(
      'Break-even at the lowest price. The lowest price equals the cost: no ride is sold at a loss, and the cheapest rides bring no profit.',
    );
    expect(costMessage(0.1 + 0.2, 0.3).tone).toBe('break-even');
  });

  it('names the loss and the lowest price when the floor is under the cost', () => {
    const incentive = costMessage(0.6, 0.4);
    expect(incentive.tone).toBe('incentive');
    expect(incentive.lead).toBe('Incentive: the lowest price is under the cost.');
    expect(incentive.text).toContain('On a ride sold at CHF 0.40 the operator loses CHF 0.20.');
    expect(incentive.text).toMatch(/worth more than the loss\.$/);
  });
});

describe('rankingLine', () => {
  it('orders profit, ridership and station balance by value', () => {
    expect(rankingLine(defaults)).toBe(
      'The model favours, in this order: 1 Ridership · 2 Profit · 3 Station balance',
    );
    expect(rankingLine({ ...defaults, ridership_weight: 1.5, station_balance_weight: 2 })).toBe(
      'The model favours, in this order: 1 Station balance · 2 Ridership · 3 Profit',
    );
  });

  it('keeps Profit, Ridership, Station balance for ties', () => {
    const line = (ridership: number, balance: number) =>
      rankingLine({ ...defaults, ridership_weight: ridership, station_balance_weight: balance });
    expect(line(1, 1)).toBe(
      'The model favours, in this order: 1 Profit · 2 Ridership · 3 Station balance',
    );
    expect(line(2, 2)).toBe(
      'The model favours, in this order: 1 Ridership · 2 Station balance · 3 Profit',
    );
    expect(line(0.5, 1)).toBe(
      'The model favours, in this order: 1 Profit · 2 Station balance · 3 Ridership',
    );
  });
});

describe('goalBars', () => {
  it('puts the three bars on the scale of the largest of 1 and the two weights', () => {
    const bars = goalBars(defaults);
    expect(bars.map((bar) => [bar.label, bar.share])).toEqual([
      ['Profit', 0.125],
      ['Ridership', 1],
      ['Station balance', 0.0625],
    ]);
    expect(
      goalBars({ ...defaults, ridership_weight: 0.5, station_balance_weight: 0.25 })[0]?.share,
    ).toBe(1);
  });
});

describe('exampleRide', () => {
  it('computes the three parts and their total from the form values', () => {
    const ride = exampleRide(defaults);
    expect(ride.parts.map((part) => part.amount)).toEqual(['0.80', '8.00', '0.20']);
    expect(ride.totalText).toBe('9.00');
    expect(ride.parts.map((part) => part.label)).toEqual([
      'Profit: price − cost',
      'Ridership: one more rider',
      'Station balance: weight × 0.40',
    ]);
    expect(ride.sentence).toBe(
      'On this ride, ridership counts most (CHF 8.00), then profit (CHF 0.80), then station balance (CHF 0.20).',
    );
  });

  it('makes the profit negative when the cost is above the example price', () => {
    const ride = exampleRide({ ...defaults, cost_bike_chf: 2 });
    const [profit] = ride.parts;
    expect(profit?.amount).toBe('−0.60');
    expect(profit?.share).toBeLessThan(0);
    expect(ride.totalText).toBe('7.60');
    expect(ride.sentence).toContain('then station balance (CHF 0.20), then profit (CHF −0.60).');
  });

  it('keeps the order Profit, Ridership, Station balance for equal parts', () => {
    const ride = exampleRide({
      ...defaults,
      cost_bike_chf: 0.4,
      ridership_weight: 1,
      station_balance_weight: 2.5,
    });
    expect(ride.sentence).toBe(
      'On this ride, profit counts most (CHF 1.00), then ridership (CHF 1.00), then station balance (CHF 1.00).',
    );
  });
});

describe('numberLine', () => {
  it('runs to 2 at least and marks the loss only under the cost', () => {
    const line = numberLine(0.6, 0.4);
    expect(line.max).toBe(2);
    expect(line.ticks.map((tick) => tick.label)).toEqual(['0.00', '0.50', '1.00', '1.50', '2.00+']);
    expect(line.loss).toEqual({ from: 20, to: 30 });
    expect(line.caption).toBe(
      'CHF per bike ride. Green: prices the model may set. Hatched: rides sold under their cost.',
    );
    expect(numberLine(0.6, 0.6).loss).toBeNull();
    expect(numberLine(0.6, 0.6).caption).toBe(
      'CHF per bike ride. Green: prices the model may set.',
    );
  });

  it('widens to the next half franc above a larger value', () => {
    expect(numberLine(2.2, 3).max).toBe(3);
    expect(numberLine(2.2, 2.7).max).toBe(3);
  });
});

describe('inputs', () => {
  it('shows at least the field digits and keeps the digits a value has', () => {
    expect(goalText(COST_FIELD, 0.6)).toBe('0.60');
    expect(goalText(COST_FIELD, 0.125)).toBe('0.125');
    expect(goalText(RIDERSHIP_FIELD, 8)).toBe('8.0');
    expect(goalText(KEPT_FIELDS[2] ?? COST_FIELD, 10)).toBe('10');
  });

  it('reads a number with a point or a comma, and nothing else', () => {
    expect(parseGoalInput(' 0,4 ')).toBe(0.4);
    expect(parseGoalInput('-1')).toBe(-1);
    expect(parseGoalInput('')).toBeNull();
    expect(parseGoalInput('abc')).toBeNull();
  });

  it('names the package names the Advanced view shows', () => {
    expect(ALL_FIELDS.map((field) => field.packageName)).toEqual([
      'cost_bike',
      'P_bar',
      'ridership_weight',
      'theta',
      'pt_price',
      'parking_fee',
      'max_displayed_alternatives',
      null,
    ]);
  });

  it('writes the sentences from the weights', () => {
    expect(RIDERSHIP_FIELD.sentence(defaults)).toBe(
      'One more traveller on public transport + bike counts like CHF 8.00 of profit.',
    );
  });
});

describe('step 4 and the discard question', () => {
  it('names the version the values were kept from, or says default values', () => {
    expect(step4Heading({ id: 'x.A', letter: 'A' })).toBe('Kept from Version A');
    expect(step4Heading(null)).toBe('Default values');
  });

  it('names that version in the question, or asks the short one', () => {
    expect(discardQuestion({ id: 'x.A', letter: 'A' })).toBe(
      'Discard this draft? Its values are removed; Version A stays as it is.',
    );
    expect(discardQuestion(null)).toBe('Discard this draft? Its values are removed.');
  });
});

describe('this run', () => {
  it('names the instance, the pairs, the period and the last duration when there is one', () => {
    expect(thisRunLine('Geneva 3 km v1', 1806, 404)).toEqual([
      'This run: Geneva 3 km v1',
      '1 806 hub pairs with routes',
      '1 period · Monday 08:00–09:00',
      'Last run on this instance: 6 min 44 s',
    ]);
    expect(thisRunLine('Geneva 3 km v1', null, null)).toEqual([
      'This run: Geneva 3 km v1',
      '1 period · Monday 08:00–09:00',
    ]);
  });
});

describe('rules box', () => {
  const passing = [
    rule('cost_bike_chf_zero_or_more', 'cost_bike_chf', true, 'ok'),
    rule('lowest_price_chf_zero_or_more', 'lowest_price_chf', true, 'ok'),
    rule('options_shown_at_least_1', 'max_displayed_options', true, 'ok'),
  ];

  it('lists the two rules, each passing', () => {
    expect(ruleLines(passing)).toEqual([
      { key: 'amounts', passed: true, text: 'Every amount is 0 or more' },
      {
        key: 'options_shown_at_least_1',
        passed: true,
        text: 'Options shown per hub pair: at least 1',
      },
    ]);
  });

  it('names the failing value and the field', () => {
    const broken = [
      rule(
        'lowest_price_chf_zero_or_more',
        'lowest_price_chf',
        false,
        'Lowest price of a ride must be 0 or more: now -0.5',
      ),
      rule(
        'options_shown_at_least_1',
        'max_displayed_options',
        false,
        'Options shown per hub pair must be at least 1: now 0',
      ),
    ];
    expect(ruleLines(broken).map((line) => [line.passed, line.text])).toEqual([
      [false, 'Lowest price of a ride must be 0 or more: now -0.5'],
      [false, 'Options shown per hub pair must be at least 1: now 0'],
    ]);
    expect([...failedFields(broken)]).toEqual(['lowest_price_chf', 'max_displayed_options']);
  });
});

describe('banners and the primary', () => {
  it('words each blocking component, the solver by its state', () => {
    const sentences = (reasons: Parameters<typeof status>[0], solver?: 'limited' | 'unavailable') =>
      pricingBannerSentences(status(reasons, solver));
    expect(sentences([{ component: 'solver', reason: 'x' }], 'unavailable')).toEqual([
      'Pricing runs are off: no Gurobi licence was found on this machine.',
    ]);
    expect(sentences([{ component: 'solver', reason: 'x' }], 'limited')).toEqual([
      "Pricing runs are off: this machine has Gurobi's size-limited licence, which cannot solve a city instance.",
    ]);
    expect(sentences([{ component: 'package', reason: 'x' }])).toEqual([
      "Pricing runs are off: the pricing model's package does not load on this machine.",
    ]);
    expect(sentences([{ component: 'runner', reason: 'x' }])).toEqual([
      'Pricing runs are off: the runner is not running. Queued runs wait.',
    ]);
    expect(sentences([{ component: 'storage', reason: 'the database is down' }])).toEqual([
      'Pricing runs are off: the database is down',
    ]);
  });

  it('shows nothing while the status is unknown or allows the run', () => {
    expect(pricingBannerSentences(undefined)).toEqual([]);
    expect(pricingBannerSentences(status([]))).toEqual([]);
  });

  it('disables the primary for a broken rule first, then for a banner', () => {
    const broken = [rule('options_shown_at_least_1', 'max_displayed_options', false, 'm')];
    const off = status([{ component: 'runner', reason: 'x' }]);
    expect(pricingPrimaryState(broken, off)).toEqual({
      disabled: true,
      note: 'One rule is not met.',
    });
    expect(pricingPrimaryState([], off)).toEqual({
      disabled: true,
      note: 'Pricing runs are off: the runner is not running. Queued runs wait.',
    });
    expect(pricingPrimaryState([], status([]))).toEqual({ disabled: false, note: null });
  });
});

describe('menu rows', () => {
  it('words each state', () => {
    expect(pricingMenuState('draft')).toBe('draft');
    expect(pricingMenuState('running')).toBe('● running');
    expect(pricingMenuState('queued', 2)).toBe('◷ queued · 2nd');
    expect(pricingMenuState('queued')).toBe('◷ queued');
    expect(pricingMenuState('failed')).toBe('✕ failed');
    expect(pricingMenuState('cancelled')).toBe('cancelled');
    expect(pricingMenuState('result')).toBe('✓ result');
  });

  const version = (overrides: Partial<PricingVersion>): PricingVersion => ({
    id: 'geneva-3km.v1.A',
    instanceVersionId: 'geneva-3km.v1',
    name: 'Version A',
    letter: 'A',
    status: 'draft',
    state: 'draft',
    basedOnId: null,
    runId: null,
    keptFrom: null,
    goals: defaults,
    rules: [],
    lastDurationS: null,
    ...overrides,
  });

  it('calls a draft on its default name "New version" and shows no letter for it', () => {
    expect(pricingVersionName(version({}))).toBe('New version');
    expect(pricingRowLetter(version({}))).toBeNull();
    expect(pricingVersionName(version({ name: 'Cheaper' }))).toBe('Cheaper');
  });

  it('shows the letter once sealed, unless the name already says it', () => {
    expect(pricingRowLetter(version({ status: 'sealed', name: 'Cheaper' }))).toBe('A');
    expect(pricingRowLetter(version({ status: 'sealed' }))).toBeNull();
    expect(pricingVersionName(version({ status: 'sealed' }))).toBe('Version A');
  });

  it('writes the breadcrumb', () => {
    expect(pricingBreadcrumb('Geneva 3 km', 1, 'New version')).toBe(
      'Geneva 3 km v1 › Pricing versions › New version',
    );
  });
});
