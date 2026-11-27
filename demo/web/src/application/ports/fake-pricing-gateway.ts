import {
  GOAL_NAMES,
  type GoalComparison,
  type GoalName,
  type PricingResult,
  type ResultNumber,
} from '../../domain/pricing-result';
import {
  PRICING_GOAL_NAMES,
  pricingVersionId,
  type PricingChanges,
  type PricingGoals,
  type PricingRule,
  type PricingVersion,
} from '../../domain/pricing-version';
import type { PricingGateway } from './pricing-gateway';

export const samplePricingGoals: PricingGoals = {
  cost_bike_chf: 0.6,
  lowest_price_chf: 0.6,
  ridership_weight: 8,
  station_balance_weight: 0.5,
  pt_fare_chf: 2,
  car_parking_fee_chf: 2.8,
  max_displayed_options: 10,
  flat_price_per_ride_chf: 1,
};

const AMOUNT_NAMES: Readonly<Record<string, string>> = {
  cost_bike_chf: 'Cost of one ride',
  lowest_price_chf: 'Lowest price of a ride',
  ridership_weight: 'Ridership weight',
  station_balance_weight: 'Station balance weight',
  pt_fare_chf: 'Public transport fare',
  car_parking_fee_chf: 'Car parking fee',
  flat_price_per_ride_chf: 'Flat price per ride',
};

/** The rules the API reports: every amount 0 or more, options shown at least 1. */
export function pricingRulesOf(goals: PricingGoals): PricingRule[] {
  const amounts = Object.entries(AMOUNT_NAMES).map(([field, name]) => {
    const value = goals[field as keyof PricingGoals];
    return {
      rule: `${field}_zero_or_more`,
      field,
      passed: value >= 0,
      message: `${name} must be 0 or more: now ${String(value)}`,
    };
  });
  const options = goals.max_displayed_options;
  return [
    ...amounts,
    {
      rule: 'options_shown_at_least_1',
      field: 'max_displayed_options',
      passed: options >= 1,
      message: `Options shown per hub pair must be at least 1: now ${String(options)}`,
    },
  ];
}

/** A draft of the sample instance version, its goals the defaults (or `goals` on top of them). */
export function samplePricingDraft(
  overrides: Partial<Omit<PricingVersion, 'goals'>> & { goals?: Partial<PricingGoals> } = {},
): PricingVersion {
  const { goals: changed, ...rest } = overrides;
  const goals = { ...samplePricingGoals, ...changed };
  return {
    id: 'geneva-3km.v1.D',
    instanceVersionId: 'geneva-3km.v1',
    letter: 'D',
    name: 'Version D',
    status: 'draft',
    state: 'draft',
    basedOnId: null,
    runId: null,
    keptFrom: { id: 'geneva-3km.v1.C', letter: 'C' },
    goals,
    rules: pricingRulesOf(goals),
    lastDurationS: null,
    ...rest,
  };
}

/** The sealed version with its result: what a finished run leaves. */
export function sampleSealedPricing(
  overrides: Partial<Omit<PricingVersion, 'goals'>> & { goals?: Partial<PricingGoals> } = {},
): PricingVersion {
  return samplePricingDraft({
    id: 'geneva-3km.v1.A',
    letter: 'A',
    name: 'Version A',
    status: 'sealed',
    state: 'result',
    keptFrom: null,
    ...overrides,
  });
}

const n = (
  value: number,
  source: ResultNumber['source'],
  unit: string,
  group: ResultNumber['group'] = 'headline',
): ResultNumber => ({ value, unit, source, group });

const simulation = (value: number, unit: string) => n(value, 'simulation', unit);

function goal(unit: string, model: number | null, version: number, flat: number): GoalComparison {
  return {
    model: model === null ? null : n(model, 'model', unit),
    modelPrices: simulation(version, unit),
    flat: simulation(flat, unit),
    change: simulation(version - flat, unit),
  };
}

/** A stored result in which the version's prices take fewer travellers to the car than the flat price. */
export function samplePricingResult(overrides: Partial<PricingResult> = {}): PricingResult {
  const empty: GoalComparison = { model: null, modelPrices: null, flat: null, change: null };
  const goals = Object.fromEntries(GOAL_NAMES.map((name) => [name, empty])) as Record<
    GoalName,
    GoalComparison
  >;
  Object.assign(goals, {
    profit: goal('chf', null, 4175.4, 3900.2),
    ridership: goal('travellers', 12281, 12000, 11000),
    stations_empty: goal('stations', null, 10, 12),
    stations_full: goal('stations', null, 12, 14),
    mean_bike_price: goal('chf_per_bike_leg', null, 0.945, 1),
  });
  const outcome = (car: number, ptOnly: number, ptBike: number, displaced: number) => ({
    ruleId: 'balanced-score',
    ruleVersion: 1,
    ruleCurrent: true,
    travellers: { car, ptOnly, ptBike },
    displaced,
    unserved: 0,
  });
  return {
    pricingVersionId: 'geneva-3km.v1.A',
    periodId: 'monday-08',
    simulations: {
      modelPrices: outcome(30000, 30000, 12240, 1240),
      flat: outcome(33000, 28000, 11240, 2115),
    },
    modelSplit: { car: 31000, ptOnly: 29000, ptBike: 12240 },
    goals,
    headline: {
      profit: n(4175, 'derived', 'chf'),
      revenue: n(11544, 'derived', 'chf'),
      cost: n(7369, 'derived', 'chf'),
      bike_price_min: n(0.4, 'model', 'chf_per_bike_leg'),
      bike_price_max: n(2.1, 'model', 'chf_per_bike_leg'),
      mean_bike_price: n(0.94, 'derived', 'chf_per_bike_leg'),
      rides_under_cost: n(4667, 'derived', 'bike_rides'),
      rides_under_cost_share: n(0.38, 'derived', 'share'),
      stations_empty_end: n(10, 'derived', 'stations'),
      stations_full_end: n(12, 'derived', 'stations'),
      stations_empty_start: n(3, 'input', 'stations'),
      stations_full_start: n(4, 'input', 'stations'),
    },
    ...overrides,
  };
}

export interface FakePricing {
  readonly gateway: PricingGateway;
  /** The versions as stored, in creation order. */
  readonly versions: () => readonly PricingVersion[];
}

/**
 * An in-memory gateway in the style of the API: letters run on, a patch keeps the values as sent and
 * reports the rules, a run seals the draft and queues `run-pricing-{letter}`.
 */
export function fakePricing(
  initial: readonly PricingVersion[] = [],
  results: Readonly<Record<string, PricingResult | null>> = {},
): FakePricing {
  let stored = [...initial];
  const replace = (next: PricingVersion) => {
    stored = stored.map((version) => (version.id === next.id ? next : version));
    return next;
  };
  const gateway: PricingGateway = {
    list: (instanceVersionId) =>
      Promise.resolve(stored.filter((version) => version.instanceVersionId === instanceVersionId)),
    get: (id) => Promise.resolve(stored.find((version) => version.id === id) ?? null),
    result: (id) => {
      if (id in results) return Promise.resolve(results[id] ?? null);
      const found = stored.find((version) => version.id === id);
      return Promise.resolve(
        found?.state === 'result' ? samplePricingResult({ pricingVersionId: id }) : null,
      );
    },
    create: (instanceVersionId, basedOn) => {
      const used = new Set(stored.map((version) => version.letter));
      let at = 0;
      while (used.has(String.fromCharCode('A'.charCodeAt(0) + at))) at += 1;
      const letter = String.fromCharCode('A'.charCodeAt(0) + at);
      const sealed = stored.filter((version) => version.status === 'sealed');
      const kept = sealed[sealed.length - 1];
      const source = basedOn === undefined ? undefined : stored.find((item) => item.id === basedOn);
      const created = samplePricingDraft({
        id: pricingVersionId(instanceVersionId, letter),
        instanceVersionId,
        letter,
        name: `Version ${letter}`,
        basedOnId: source?.id ?? null,
        keptFrom: kept === undefined ? null : { id: kept.id, letter: kept.letter },
        ...(source === undefined ? {} : { goals: source.goals }),
      });
      stored = [...stored, created];
      return Promise.resolve(created);
    },
    patch: (id, changes: PricingChanges) => {
      const found = stored.find((version) => version.id === id);
      if (found === undefined) return Promise.reject(new Error(`No pricing version ${id}.`));
      if (found.status === 'sealed') return Promise.reject(new Error('The version is saved.'));
      const goals: Record<string, number> = { ...found.goals };
      for (const name of PRICING_GOAL_NAMES) {
        const value = changes[name];
        if (value !== undefined) goals[name] = value;
      }
      const next = {
        ...found,
        name: changes.name?.trim() ?? found.name,
        goals: goals as unknown as PricingGoals,
      };
      return Promise.resolve(replace({ ...next, rules: pricingRulesOf(next.goals) }));
    },
    discard: (id) => {
      stored = stored.filter((version) => version.id !== id);
      return Promise.resolve();
    },
    run: (id) => {
      const found = stored.find((version) => version.id === id);
      if (found === undefined) return Promise.reject(new Error(`No pricing version ${id}.`));
      if (found.rules.some((rule) => !rule.passed)) {
        return Promise.resolve({ kind: 'refused', detail: 'The draft breaks a rule.' });
      }
      const runId = `run-pricing-${found.letter}`;
      replace({ ...found, status: 'sealed', state: 'queued', runId });
      return Promise.resolve({ kind: 'queued', runId });
    },
  };
  return { gateway, versions: () => stored };
}

/** The gateway with no pricing version at all. */
export function fakePricingGateway(initial: readonly PricingVersion[] = []): PricingGateway {
  return fakePricing(initial).gateway;
}
