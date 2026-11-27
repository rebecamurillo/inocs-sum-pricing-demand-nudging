import { describe, expect, it } from 'vitest';
import {
  isShowcaseNote,
  olderRule,
  olderRuleBox,
  olderRuleSuffix,
  pricingDeleteAction,
  pricingDeleteQuestion,
  simulateAgainLabel,
  SIMULATING,
  SIMULATION_OFF,
  simulationOffReason,
  simulatingLine,
  STORED_RESULTS_STAY,
} from './older-rule-text';
import type { PricingResult, SimulationOutcome } from './pricing-result';

const current = { id: 'balanced-score', version: 2 };

const outcome = (overrides: Partial<SimulationOutcome> = {}): SimulationOutcome => ({
  ruleId: 'balanced-score',
  ruleVersion: 2,
  ruleCurrent: true,
  ruleParameters: { price_weight: 0.5, time_weight: 0.5 },
  travellers: { car: 1, ptOnly: 1, ptBike: 1 },
  bikeRides: { value: 1, unit: 'bike_rides', source: 'simulation', group: 'headline' },
  revenue: { value: 1, unit: 'chf', source: 'simulation', group: 'headline' },
  cost: { value: 1, unit: 'chf', source: 'simulation', group: 'headline' },
  displaced: 0,
  unserved: 0,
  createdAt: '2026-11-10T09:00:00+00:00',
  ...overrides,
});

function withRules(
  modelPrices: Partial<SimulationOutcome>,
  flat: Partial<SimulationOutcome> = {},
): Pick<PricingResult, 'simulations'> {
  return { simulations: { modelPrices: outcome(modelPrices), flat: outcome(flat) } };
}

describe('olderRule', () => {
  it('is null when both simulations used the current rule', () => {
    expect(olderRule(withRules({}), current)).toBeNull();
  });

  it('names the stored rule version and the current one', () => {
    const result = withRules({ ruleCurrent: false, ruleVersion: 1 });

    expect(olderRule(result, current)).toEqual({ old: 1, new: 2 });
  });

  it('reads the flat simulation when only it is older', () => {
    const result = withRules({}, { ruleCurrent: false, ruleVersion: 0 });

    expect(olderRule(result, current)).toEqual({ old: 0, new: 2 });
  });

  it('is null when the current rule is not known', () => {
    const result = withRules({ ruleCurrent: false, ruleVersion: 1 });

    expect(olderRule(result, null)).toBeNull();
  });
});

describe('the texts', () => {
  it('writes the box verbatim', () => {
    expect(olderRuleBox(1, 2)).toBe(
      "Simulated with an older rule. These simulations used the placeholder rule v1; the Lab now simulates with v2. The pricing model's numbers do not change.",
    );
  });

  it('writes the action, the source suffix and the menu state', () => {
    expect(simulateAgainLabel(2)).toBe('Simulate again with v2');
    expect(olderRuleSuffix(1)).toBe(' · older rule (v1)');
    expect(SIMULATING).toBe('● simulating');
  });

  it('writes the running line with the elapsed time', () => {
    expect(simulatingLine(42)).toBe('Traveller simulation · running for 42 s');
    expect(simulatingLine(252)).toBe('Traveller simulation · running for 4 min 12 s');
  });

  it('writes the off state: the runner sentence, or the API reason of another component', () => {
    expect(SIMULATION_OFF).toBe('Simulation is off: the runner is not running.');
    expect(STORED_RESULTS_STAY).toBe('Stored results stay available.');
    expect(
      simulationOffReason({
        allowed: false,
        reasons: [{ component: 'runner', reason: 'No worker.' }],
      }),
    ).toBe(SIMULATION_OFF);
    expect(
      simulationOffReason({
        allowed: false,
        reasons: [{ component: 'storage', reason: 'The database is unreachable.' }],
      }),
    ).toBe('Simulation is off: The database is unreachable.');
  });

  it('writes the deletion question, action and showcase note verbatim', () => {
    expect(pricingDeleteQuestion('B', 'Version B', 'Geneva 3 km v1')).toBe(
      'Delete Version B · Version B? This removes its goals and its result. Other versions of Geneva 3 km v1 stay. This cannot be undone.',
    );
    expect(pricingDeleteAction('B')).toBe('Delete Version B');
    expect(isShowcaseNote('B')).toBe(
      "Version B is the home page's result: choose another one first.",
    );
  });

  it('carries no bracketed reference and no time limit', () => {
    const all = [
      olderRuleBox(1, 2),
      simulateAgainLabel(2),
      simulatingLine(1),
      SIMULATION_OFF,
      STORED_RESULTS_STAY,
      pricingDeleteQuestion('A', 'a', 'b'),
      isShowcaseNote('A'),
    ].join(' ');

    expect(all).not.toMatch(/\[Q-|time limit/);
  });
});
