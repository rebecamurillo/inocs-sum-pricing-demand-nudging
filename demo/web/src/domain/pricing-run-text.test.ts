import { describe, expect, it } from 'vitest';
import {
  PRICING_RUN_BRIEF,
  RESULT_OPENS,
  CONTINUES,
  RUNNING_LABEL,
  changedGoals,
  checkOf,
  instanceLine,
  openMeanwhileLabel,
  previousFinished,
  pricingFailureReason,
  pricingModelLine,
  runAgainLabel,
  runLineResultReady,
  simulationLine,
  statusInWords,
} from './pricing-run-text';
import type { PricingGoals, PricingVersion } from './pricing-version';
import type { RunStep } from './run';
import { cancelQuestion, queuedSentence, subjectName } from './run-text';

const GOALS: PricingGoals = {
  cost_bike_chf: 0.6,
  lowest_price_chf: 0.6,
  ridership_weight: 8,
  station_balance_weight: 0.5,
  pt_fare_chf: 2,
  car_parking_fee_chf: 2.8,
  max_displayed_options: 10,
  flat_price_per_ride_chf: 1,
};

function samplePricingDraft(
  overrides: Partial<Omit<PricingVersion, 'goals'>> & { goals?: Partial<PricingGoals> } = {},
): PricingVersion {
  const { goals, ...rest } = overrides;
  return {
    id: 'geneva-3km.v1.D',
    instanceVersionId: 'geneva-3km.v1',
    letter: 'D',
    name: 'Version D',
    status: 'sealed',
    state: 'result',
    basedOnId: null,
    runId: null,
    keptFrom: null,
    goals: { ...GOALS, ...goals },
    rules: [],
    lastDurationS: null,
    ...rest,
  };
}
const sampleSealedPricing = samplePricingDraft;

const step = (overrides: Partial<RunStep>): RunStep => ({
  step: 'pricing_model',
  number: 5,
  state: 'pending',
  startedAt: null,
  finishedAt: null,
  counts: {},
  progress: null,
  lastDurationS: null,
  ...overrides,
});

describe('the fixed sentences', () => {
  it('writes the brief, the closing lines and the bar', () => {
    expect(PRICING_RUN_BRIEF).toBe(
      'The pricing model is setting the bike prices for Monday 08:00–09:00; then the travellers are simulated.',
    );
    expect(RESULT_OPENS).toBe('The result opens when both steps are done.');
    expect(CONTINUES).toBe(
      'It continues if you open another page, and you can queue another version meanwhile.',
    );
    expect(RUNNING_LABEL).toBe('Running…');
    expect(openMeanwhileLabel('A')).toBe('Open Version A meanwhile');
  });

  it('writes the instance line with and without the hub pairs', () => {
    expect(instanceLine('Geneva 3 km v1', 1806)).toBe(
      '✓ City instance · Geneva 3 km v1 · 1 806 hub pairs with routes',
    );
    expect(instanceLine('Geneva 3 km v1', null)).toBe('✓ City instance · Geneva 3 km v1');
  });
});

describe('the pricing model line', () => {
  const running = step({ state: 'running' });

  it('writes the running step with its clock and the last time on the instance', () => {
    expect(pricingModelLine({ ...running, lastDurationS: 400 }, { elapsedS: 185 })).toEqual({
      mark: '●',
      text: '5 Pricing model — running for 3 min 5 s · last time on this instance: 6 min 40 s',
      tone: 'running',
    });
  });

  it('leaves the last time out when none was measured', () => {
    expect(pricingModelLine(running, { elapsedS: 5 }).text).toBe(
      '5 Pricing model — running for 5 s',
    );
  });

  it('writes waiting, kept, done, failed and cancelled', () => {
    const text = (state: RunStep['state']) =>
      pricingModelLine(step({ state }), { elapsedS: 0 }).text;
    expect(text('pending')).toBe('5 Pricing model — waiting');
    expect(text('kept')).toBe(
      '5 Pricing model — ✓ kept: these goals were already solved on this instance',
    );
    expect(text('done')).toBe('5 Pricing model — ✓ done');
    expect(text('failed')).toBe('5 Pricing model — ✕ failed');
    expect(text('cancelled')).toBe('5 Pricing model — cancelled');
    expect(
      pricingModelLine(
        step({
          state: 'done',
          startedAt: new Date('2026-11-27T10:00:00Z'),
          finishedAt: new Date('2026-11-27T10:06:40Z'),
        }),
        { elapsedS: 0 },
      ).text,
    ).toBe('5 Pricing model — ✓ done in 6 min 40 s');
  });
});

describe('the traveller simulation line', () => {
  const simulation = (state: RunStep['state']) =>
    step({ step: 'traveller_simulation', number: 6, state });
  const tail =
    "with Version C's prices, then with the flat price 1.00 CHF · placeholder rule: half price, half travel time";

  it('writes waiting, running and kept', () => {
    expect(simulationLine(simulation('pending'), { elapsedS: 0 }, 'C', 1).text).toBe(
      `5b Traveller simulation — waiting · ${tail}`,
    );
    expect(simulationLine(simulation('running'), { elapsedS: 62 }, 'C', 1)).toMatchObject({
      mark: '●',
      text: `5b Traveller simulation — running for 1 min 2 s · ${tail}`,
    });
    expect(simulationLine(simulation('kept'), { elapsedS: 0 }, 'C', 1).text).toBe(
      `5b Traveller simulation — ✓ kept: already simulated with the same prices and rule · ${tail}`,
    );
  });

  it('writes the flat price with two decimals', () => {
    expect(simulationLine(simulation('pending'), { elapsedS: 0 }, 'C', 1.5).text).toContain(
      '1.50 CHF',
    );
  });
});

describe('the previous finished version', () => {
  const version = (letter: string, state: 'result' | 'failed' | 'draft') =>
    sampleSealedPricing({ id: `iv.${letter}`, letter, state });

  it('is the finished version with the highest letter below this one', () => {
    const versions = [
      version('A', 'result'),
      version('B', 'result'),
      version('C', 'failed'),
      version('D', 'result'),
    ];
    expect(previousFinished(versions, 'D')?.letter).toBe('B');
    expect(previousFinished(versions, 'C')?.letter).toBe('B');
    expect(previousFinished(versions, 'B')?.letter).toBe('A');
  });

  it('is none when no finished version lies below', () => {
    expect(previousFinished([version('A', 'failed'), version('C', 'result')], 'B')).toBeNull();
    expect(previousFinished([], 'A')).toBeNull();
  });
});

describe('what a version changes', () => {
  it('lists the goals that differ, with the previous value', () => {
    const source = samplePricingDraft();
    const version = samplePricingDraft({ goals: { pt_fare_chf: 2.4, max_displayed_options: 8 } });

    expect(changedGoals(version, source)).toEqual([
      { name: 'Public transport fare, CHF', before: '2.00', after: '2.40' },
      { name: 'Options shown per hub pair', before: '10', after: '8' },
    ]);
  });

  it('lists nothing for equal goals and for a first version', () => {
    expect(changedGoals(samplePricingDraft(), samplePricingDraft())).toEqual([]);
    expect(changedGoals(samplePricingDraft(), null)).toEqual([]);
  });
});

describe('failures', () => {
  it.each([
    ['status INFEASIBLE', 'no set of prices meets every constraint'],
    ['status INF_OR_UNBD', 'no set of prices meets every constraint'],
    ['status TIME_LIMIT', 'the solver stopped before finding one'],
    ['no status at all', 'the solver stopped before finding one'],
  ])('writes the status of %s in words', (stored, words) => {
    expect(statusInWords(`the solver found no solution (${stored})`)).toBe(words);
  });

  it('writes every reason of the pricing run', () => {
    expect(pricingFailureReason('solver_size_limited', 'x')).toBe(
      "Gurobi's size-limited licence cannot solve this instance",
    );
    expect(
      pricingFailureReason(
        'solver_no_solution',
        'the solver found no solution (status INFEASIBLE)',
      ),
    ).toBe('the solver ended without a solution (no set of prices meets every constraint)');
    expect(
      pricingFailureReason(
        'simulation_check_failed',
        'the traveller simulation broke its check: the travellers of a pair do not add up',
      ),
    ).toBe(
      "the traveller simulation broke its check (the travellers of a pair do not add up); nothing was stored. The pricing model's result is kept.",
    );
    expect(pricingFailureReason('stage_error', 'RuntimeError: boom')).toBe(
      "an error stopped the step. The details are in the run's log.",
    );
    expect(pricingFailureReason('killed', 'x')).toBe(
      'the process was stopped by the system; the machine may be out of memory',
    );
    expect(pricingFailureReason('interrupted', 'x')).toBe(
      'the run was interrupted twice by a stop of the runner',
    );
    expect(pricingFailureReason('something_new', 'the stored reason')).toBe('the stored reason');
  });

  it('never names a time limit', () => {
    for (const code of [
      'solver_size_limited',
      'solver_no_solution',
      'simulation_check_failed',
      'stage_error',
      'killed',
      'interrupted',
    ]) {
      expect(
        pricingFailureReason(code, 'the solver found no solution (status TIME_LIMIT)'),
      ).not.toMatch(/time limit/i);
    }
  });

  it('reads the check after "check: "', () => {
    expect(checkOf('broke its check: a b.')).toBe('a b');
  });

  it('names the step to run again from', () => {
    expect(runAgainLabel('pricing_model')).toBe('Run again from Pricing model');
    expect(runAgainLabel('traveller_simulation')).toBe('Run again from Traveller simulation');
  });
});

describe('queued, cancelled and the run line', () => {
  it('writes the queued sentence with ordinals behind a build and a pricing run', () => {
    expect(queuedSentence(2, 'Geneva 3 km v2', 'build')).toBe(
      'Queued, 2nd in line: Geneva 3 km v2 is building. Runs go one at a time; this one starts when the run before it ends.',
    );
    expect(queuedSentence(2, 'Version A', 'pricing')).toBe(
      'Queued, 2nd in line: Version A is running. Runs go one at a time; this one starts when the run before it ends.',
    );
    expect(queuedSentence(3, 'Version A', 'pricing')).toContain('Queued, 3rd in line');
  });

  it('ends the pricing confirmation with "duplicate it"', () => {
    expect(cancelQuestion('Version C', false, 'pricing')).toBe(
      'Cancel this run? The running step stops and is not stored; steps already done are kept. Version C stays in the menu as cancelled: you can run it again or duplicate it.',
    );
    expect(cancelQuestion('Version C', true, 'pricing')).toBe(
      'Cancel this run? Nothing has run yet. Version C stays in the menu as cancelled: you can run it again or duplicate it.',
    );
  });

  it('writes the run line when the result is ready and names a pricing subject', () => {
    expect(runLineResultReady('Version C')).toBe('✓ Version C: result ready');
    const entries = [
      {
        id: 'geneva-3km',
        name: 'Geneva 3 km',
        datasetId: 'd',
        versions: [
          {
            id: 'geneva-3km.v1',
            number: 1,
            status: 'sealed' as const,
            state: 'ready',
            pricingVersionCount: 1,
            pricingVersionLetters: ['C'],
          },
        ],
      },
    ];
    expect(
      subjectName({ subject: { type: 'pricing_version', id: 'geneva-3km.v1.C' } }, entries),
    ).toBe('Version C');
  });
});
