import type {
  Comparison,
  ComparisonGroup,
  ComparisonRow,
  HubDifference,
  PairDifference,
  FlatReference,
} from '../../domain/comparison';
import {
  GOAL_NAMES,
  type GoalComparison,
  type GoalName,
  type HubPairResult,
  type HubResult,
  type OptionResult,
  type PricingResult,
  type ResultNumber,
  type StoredSimulation,
} from '../../domain/pricing-result';
import {
  PRICING_GOAL_NAMES,
  pricingVersionId,
  type PricingChanges,
  type PricingGoals,
  type PricingRule,
  type PricingVersion,
} from '../../domain/pricing-version';
import type { Showcase } from '../../domain/showcase';
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
    periods: [{ id: 'monday-08', key: 'mon-08', label: 'Monday 08:00–09:00' }],
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
  const outcome = (
    car: number,
    ptOnly: number,
    ptBike: number,
    displaced: number,
    bikeRides: number,
    revenue: number,
    cost: number,
  ) => ({
    ruleId: 'balanced-score',
    ruleVersion: 1,
    ruleCurrent: true,
    ruleParameters: { price_weight: 0.5, time_weight: 0.5 },
    travellers: { car, ptOnly, ptBike },
    bikeRides: simulation(bikeRides, 'bike_rides'),
    revenue: simulation(revenue, 'chf'),
    cost: simulation(cost, 'chf'),
    displaced,
    unserved: 0,
    createdAt: '2026-11-10T09:00:00+00:00',
  });
  const advancedNumber = (value: number, unit: string, source: ResultNumber['source'] = 'model') =>
    n(value, source, unit, 'advanced');
  return {
    pricingVersionId: 'geneva-3km.v1.A',
    periodId: 'monday-08',
    simulations: {
      modelPrices: outcome(30000, 30000, 12240, 1240, 12000, 11544.4, 7369),
      flat: outcome(33000, 28000, 11240, 2115, 11000, 11269.2, 7369),
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
    advanced: {
      solverStatusName: 'OPTIMAL',
      numbers: {
        solver_status: advancedNumber(2, 'status'),
        objective_value: advancedNumber(23456.4, 'objective'),
        objective_term_ridership: advancedNumber(98248, 'objective', 'derived'),
        objective_term_revenue: advancedNumber(11544, 'chf', 'derived'),
        objective_term_cost: advancedNumber(7369, 'chf', 'derived'),
        objective_term_station_balance: advancedNumber(-120.4, 'objective', 'derived'),
        gap_pct: advancedNumber(0.5, 'percent'),
        solution_time_s: advancedNumber(12.34, 's'),
        solution_count: advancedNumber(3, 'solutions'),
        time_limit_reached: advancedNumber(0, 'flag'),
        package_avg_bike_price_multimodal: advancedNumber(0.94, 'chf', 'package_summary'),
        package_avg_bike_price_offered: advancedNumber(1.02, 'chf', 'package_summary'),
        parameter_cost_bike: advancedNumber(0.6, 'chf', 'input'),
        parameter_P_bar: advancedNumber(0.6, 'chf', 'input'),
        parameter_ridership_weight: advancedNumber(8, 'weight', 'input'),
        parameter_theta: advancedNumber(0.5, 'weight', 'input'),
        parameter_pt_price: advancedNumber(2, 'chf', 'input'),
        parameter_parking_fee: advancedNumber(2.8, 'chf', 'input'),
        parameter_max_displayed_alternatives: advancedNumber(10, 'options', 'input'),
      },
    },
    coefficients: {
      ASC_PT: advancedNumber(-0.756, 'coefficient', 'input'),
      ASC_CAR: advancedNumber(0, 'coefficient', 'input'),
      B_TIME: null,
    },
    provenance: {
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
        {
          priceScheme: 'flat',
          ruleId: 'balanced-score',
          ruleVersion: 1,
          createdAt: '2026-11-10T09:00:00+00:00',
        },
      ],
    },
    ...overrides,
  };
}

/** The stored simulations of the sample version: the current rule's pair, and with `earlier` an older pair. */
export function sampleStoredSimulations(earlier = false): StoredSimulation[] {
  const make = (
    priceScheme: StoredSimulation['priceScheme'],
    ruleVersion: number,
    ruleCurrent: boolean,
    parameters: Record<string, number>,
    createdAt: string,
  ): StoredSimulation => ({
    periodId: 'monday-08',
    priceScheme,
    ruleId: 'balanced-score',
    ruleVersion,
    ruleParameters: parameters,
    ruleCurrent,
    createdAt,
  });
  const current = { price_weight: 0.5, time_weight: 0.5 };
  return [
    ...(earlier
      ? [
          make(
            'model_prices',
            0,
            false,
            { price_weight: 1, time_weight: 0 },
            '2026-11-09T09:00:00+00:00',
          ),
          make('flat', 0, false, { price_weight: 1, time_weight: 0 }, '2026-11-09T09:00:00+00:00'),
        ]
      : []),
    make('model_prices', 1, true, current, '2026-11-10T09:00:00+00:00'),
    make('flat', 1, true, current, '2026-11-10T09:00:00+00:00'),
  ];
}

const leg = (
  mode: string,
  line: string | null,
  fromPlace: string | null,
  toPlace: string | null,
  durationS: number,
) => ({ mode, line, fromPlace, toPlace, durationS });

function sampleOption(
  arcId: string,
  price: number | null,
  riders: number | null,
  minutes: number,
  legs: OptionResult['legs'],
): OptionResult {
  return {
    arcId,
    mode: 'pt_bike',
    legs,
    duration: n(minutes * 60, 'trip_planner', 's', 'advanced'),
    bikeLegs: n(1, 'input', 'bike_legs', 'advanced'),
    bikePrice: price === null ? null : n(price, 'model', 'chf_per_bike_leg', 'advanced'),
    riders: riders === null ? null : n(riders, 'model', 'travellers', 'advanced'),
  };
}

const travellers = (car: number, ptOnly: number, ptBike: number) => ({ car, ptOnly, ptBike });

/** Three pairs, one of each row state: priced (three options), no bike rides, none offered. */
export function sampleHubPairResults(): HubPairResult[] {
  const price = (value: number) => n(value, 'derived', 'chf_per_bike_leg', 'advanced');
  return [
    {
      originHub: 'H4',
      destinationHub: 'H9',
      meanBikePrice: price(0.95),
      minBikePrice: n(0.6, 'model', 'chf_per_bike_leg', 'advanced'),
      maxBikePrice: n(1.4, 'model', 'chf_per_bike_leg', 'advanced'),
      travellers: travellers(310.4, 220, 41.6),
      options: [
        sampleOption('H4-H9-a', 1.4, 3.2, 14, [
          leg('FOOT', null, 'Start', 'Plainpalais', 60),
          leg('TRAM', '12', 'Plainpalais', 'Rive', 420),
          leg('BICYCLE', null, 'Rive', 'Eaux-Vives', 300),
        ]),
        sampleOption('H4-H9-b', 0.6, 30.8, 12, [
          leg('BUS', '1', 'Plainpalais', 'Cornavin', 300),
          leg('BICYCLE', null, 'Cornavin', 'Eaux-Vives', 400),
        ]),
        sampleOption('H4-H9-c', 0.9, 7.6, 16, [leg('BICYCLE', null, 'Plainpalais', 'Rive', 900)]),
      ],
    },
    {
      originHub: 'H9',
      destinationHub: 'H4',
      meanBikePrice: null,
      minBikePrice: n(0.7, 'model', 'chf_per_bike_leg', 'advanced'),
      maxBikePrice: n(1.2, 'model', 'chf_per_bike_leg', 'advanced'),
      travellers: travellers(120, 80, 0),
      options: [
        sampleOption('H9-H4-a', 0.7, 0, 15, [leg('TRAM', '12', 'Rive', 'Plainpalais', 500)]),
      ],
    },
    {
      originHub: 'H9',
      destinationHub: 'H12',
      meanBikePrice: null,
      minBikePrice: null,
      maxBikePrice: null,
      travellers: travellers(60, 40, 0),
      options: [sampleOption('H9-H12-a', null, null, 20, [])],
    },
  ];
}

export function sampleHubResults(): HubResult[] {
  const rides = (value: number) => n(value, 'derived', 'bike_rides', 'advanced');
  return [
    {
      hubId: 'H4',
      label: 'H4 Plainpalais',
      lat: 46.198,
      lon: 6.139,
      ridesStarting: rides(42),
      ridesEnding: rides(10),
      meanBikePrice: n(0.95, 'derived', 'chf_per_bike_leg', 'advanced'),
    },
    {
      hubId: 'H9',
      label: 'H9 Eaux-Vives',
      lat: 46.2,
      lon: 6.16,
      ridesStarting: rides(8),
      ridesEnding: rides(36),
      meanBikePrice: null,
    },
    {
      hubId: 'H12',
      label: 'H12 Cornavin',
      lat: 46.21,
      lon: 6.142,
      ridesStarting: rides(0),
      ridesEnding: rides(4),
      meanBikePrice: null,
    },
  ];
}

/** What a fake comparison varies per version id: the package commit and the rule of its simulations. */
export interface FakeComparisonDetails {
  /** The package commit of a version's solve; `aaaaaaa0000` for the others, null for none. */
  readonly commits?: Readonly<Record<string, string | null>>;
  /** Versions whose simulations used an older rule, with its version number. */
  readonly olderRule?: Readonly<Record<string, number>>;
  /** The hub pairs of the difference table, largest first; a few over the sample hubs by default. */
  readonly pairDifferences?: readonly PairDifference[];
  /** Letters of versions sharing one stored solve; none by default. */
  readonly identicalSolves?: readonly (readonly string[])[];
}

/** A hub pair's figures in the two compared versions: `a` at `priceA`, `b` at `priceB`. */
export function samplePairDifference(
  originHub: string,
  destinationHub: string,
  priceA: number,
  priceB: number,
  travellersA = 100,
  travellersB = 120,
): PairDifference {
  const money = (value: number) => n(value, 'derived', 'chf_per_bike_leg');
  const people = (value: number) => n(value, 'model', 'travellers');
  return {
    originHub,
    destinationHub,
    meanPriceA: money(priceA),
    meanPriceB: money(priceB),
    priceDifference: money(priceB - priceA),
    travellersA: people(travellersA),
    travellersB: people(travellersB),
    travellersDifference: people(travellersB - travellersA),
  };
}

const sim = (value: number, unit: string): ResultNumber => n(value, 'simulation', unit);

/**
 * A comparison of finished versions in the shape of the API's: the figures follow the letter
 * (A has the highest car share, each later letter 8 points less), flat columns are one per
 * (flat price, fare, parking fee, cost of one ride, rule), `best` is the lowest or highest per row.
 */
export function fakeComparison(
  versions: readonly PricingVersion[],
  details: FakeComparisonDetails = {},
): Comparison {
  const sorted = [...versions].sort((a, b) => a.letter.localeCompare(b.letter));
  const letters = sorted.map((version) => version.letter);
  const older = (version: PricingVersion) => details.olderRule?.[version.id];
  const referenceId = (version: PricingVersion) =>
    [
      version.goals.flat_price_per_ride_chf,
      version.goals.pt_fare_chf,
      version.goals.car_parking_fee_chf,
      version.goals.cost_bike_chf,
      older(version) ?? 'current',
    ].join('|');
  const referenceIds = [...new Set(sorted.map(referenceId))];
  const flatReferences: FlatReference[] = referenceIds.map((id) => {
    const served = sorted.filter((version) => referenceId(version) === id);
    const [first] = served as [PricingVersion, ...PricingVersion[]];
    return {
      id,
      letters: served.map((version) => version.letter),
      flatPrice: first.goals.flat_price_per_ride_chf,
      fare: first.goals.pt_fare_chf,
      parkingFee: first.goals.car_parking_fee_chf,
      costBike: first.goals.cost_bike_chf,
      ruleCurrent: older(first) === undefined,
      ruleVersion: older(first) ?? 2,
    };
  });
  const at = (letter: string) => letter.charCodeAt(0) - 'A'.charCodeAt(0);
  const best = (values: Record<string, number>, direction: 'lowest' | 'highest') => {
    const list = Object.values(values);
    const target = direction === 'lowest' ? Math.min(...list) : Math.max(...list);
    return list.every((value) => value === target)
      ? []
      : Object.keys(values).filter((letter) => values[letter] === target);
  };
  /** The simulated rows: the unit, the flat value, the value of a letter and which end is best. */
  const simulatedSpecs: readonly (readonly [
    string,
    string,
    number,
    (k: number) => number,
    'lowest' | 'highest' | null,
  ])[] = [
    ['share_car', 'share', 0.55, (k) => 0.5 - 0.08 * k, 'lowest'],
    ['share_pt_only', 'share', 0.3, () => 0.3, null],
    ['share_pt_bike', 'share', 0.15, (k) => 0.2 + 0.08 * k, null],
    ['ridership', 'travellers', 11000, (k) => 12000 + 500 * k, 'highest'],
    ['profit', 'chf', 3900, (k) => 4000 + (k % 2 === 0 ? 100 : 300) * (k + 1), 'highest'],
    ['mean_bike_price', 'chf_per_bike_leg', 1, (k) => 1 - 0.05 * k, null],
    ['stations_empty_or_full', 'stations', 26, (k) => 22 - 2 * k, 'lowest'],
    ['displaced', 'travellers', 45, (k) => 40 + k, null],
  ];
  const simulatedRows: ComparisonRow[] = simulatedSpecs.map(([key, unit, flat, own, direction]) => {
    const shares = unit === 'share';
    const values = Object.fromEntries(letters.map((letter) => [letter, own(at(letter))]));
    return {
      key,
      values: Object.fromEntries(
        Object.entries(values).map(([letter, value]) => [letter, sim(value, unit)]),
      ),
      changes: Object.fromEntries(
        Object.entries(values).map(([letter, value]) => [
          letter,
          sim((value - flat) * (shares ? 100 : 1), shares ? 'share_points' : unit),
        ]),
      ),
      flats: Object.fromEntries(referenceIds.map((id) => [id, sim(flat, unit)])),
      best: direction === null ? [] : best(values, direction),
    };
  });
  const model = (value: number, unit: string, group: ResultNumber['group'] = 'headline') =>
    n(value, 'model', unit, group);
  const modelRow = (key: string, make: (letter: string) => ResultNumber): ComparisonRow => {
    const values = Object.fromEntries(letters.map((letter) => [letter, make(letter)]));
    const numeric = Object.fromEntries(
      Object.entries(values).map(([letter, item]) => [letter, item.value]),
    );
    return {
      key,
      values,
      changes: {},
      flats: {},
      best: key === 'ridership' ? best(numeric, 'highest') : [],
    };
  };
  const goalNumber = (version: PricingVersion, name: keyof PricingGoals): ResultNumber =>
    n(version.goals[name], 'input', name.endsWith('_chf') ? 'chf' : 'none');
  const goalRows: ComparisonRow[] = (
    [
      'cost_bike_chf',
      'lowest_price_chf',
      'ridership_weight',
      'station_balance_weight',
      'flat_price_per_ride_chf',
    ] as const
  )
    .filter((name) => new Set(sorted.map((version) => version.goals[name])).size > 1)
    .map((name) => ({
      key: name,
      values: Object.fromEntries(
        sorted.map((version) => [version.letter, goalNumber(version, name)]),
      ),
      changes: {},
      flats: {},
      best: [],
    }));
  const plain = modelRow;
  const groups: ComparisonGroup[] = [
    { name: 'simulated', rows: simulatedRows },
    {
      name: 'model',
      rows: [
        plain('share_car', (letter) => model(0.45 - 0.05 * at(letter), 'share')),
        plain('share_pt_only', () => model(0.3, 'share')),
        plain('share_pt_bike', (letter) => model(0.25 + 0.05 * at(letter), 'share')),
        plain('ridership', (letter) => model(12281 + 100 * at(letter), 'travellers')),
        plain('bike_price_min', () => model(0.6, 'chf_per_bike_leg')),
        plain('bike_price_max', (letter) => model(2.4 + 0.1 * at(letter), 'chf_per_bike_leg')),
      ],
    },
    {
      name: 'derived',
      rows: [
        plain('profit', (letter) => n(4175 + 10 * at(letter), 'derived', 'chf')),
        plain('revenue', () => n(9000, 'derived', 'chf')),
        plain('cost', () => n(4800, 'derived', 'chf')),
        plain('mean_bike_price', () => n(1.1, 'derived', 'chf_per_bike_leg')),
        plain('rides_under_cost', () => n(120, 'derived', 'bike_rides')),
        plain('stations_empty_or_full', (letter) => n(20 - at(letter), 'derived', 'stations')),
      ],
    },
    { name: 'goals_that_differ', rows: goalRows },
    {
      name: 'solver',
      rows: [
        plain('objective_value', () => model(5100, 'none', 'advanced')),
        plain('solution_time_s', () => model(12.34, 'seconds', 'advanced')),
        plain('gap_pct', () => model(0.5, 'percent', 'advanced')),
        plain('solver_status', () => model(2, 'none', 'advanced')),
        plain('hub_pairs_with_bike_option', () => model(60, 'hub_pairs', 'advanced')),
        plain('bike_options_offered', () => model(240, 'options', 'advanced')),
      ],
    },
  ];
  return {
    instanceVersion: { id: sorted[0]?.instanceVersionId ?? '', name: 'Geneva 3 km v1' },
    period: { id: 'monday-0800', name: 'Monday 08:00–09:00' },
    versions: sorted.map((version) => ({
      id: version.id,
      letter: version.letter,
      name: version.name,
      goals: Object.fromEntries(
        PRICING_GOAL_NAMES.map((name) => [name, goalNumber(version, name)]),
      ),
      flatReference: referenceId(version),
      packageCommit:
        version.id in (details.commits ?? {})
          ? (details.commits?.[version.id] ?? null)
          : 'aaaaaaa0000',
      packageFingerprint: 'fingerprint',
      simulations: (['model_prices', 'flat'] as const).map((priceScheme) => ({
        priceScheme,
        ruleCurrent: older(version) === undefined,
        ruleVersion: older(version) ?? 2,
      })),
      solveKey: `solve-${version.letter}`,
    })),
    flatReferences,
    groups,
    identicalSolves: details.identicalSolves ?? [],
    pairDifferences: {
      a: letters.at(-2) ?? '',
      b: letters.at(-1) ?? '',
      pairs: details.pairDifferences ?? [
        samplePairDifference('H4', 'H9', 0.95, 1.25, 1234, 2100),
        samplePairDifference('H9', 'H4', 1.1, 0.9),
        samplePairDifference('H4', 'H12', 1, 1),
      ],
    },
    hubDifferences: sampleHubResults().map((hub, at): HubDifference => {
      const price = (value: number) => n(value, 'derived', 'chf_per_bike_leg');
      const rides = (value: number) => n(value, 'derived', 'bike_rides');
      const priced = hub.meanBikePrice !== null;
      return {
        hubId: hub.hubId,
        meanPriceA: priced ? price(0.9) : null,
        meanPriceB: priced ? price(1.05) : null,
        priceDifference: priced ? price(0.15) : null,
        priceBMinusFlat: priced ? price(0.05) : null,
        ridesStartingA: rides(hub.ridesStarting.value),
        ridesStartingB: rides(hub.ridesStarting.value + 5 * (at - 1)),
        ridesStartingDifference: rides(5 * (at - 1)),
      };
    }),
  };
}

export interface FakePricing {
  readonly gateway: PricingGateway;
  /** The versions as stored, in creation order. */
  readonly versions: () => readonly PricingVersion[];
  /** The ids of the versions a simulation run was queued for, in order. */
  readonly simulated: () => readonly string[];
}

/**
 * An in-memory gateway in the style of the API: letters run on, a patch keeps the values as sent and
 * reports the rules, a run seals the draft and queues `run-pricing-{letter}`.
 */
export function fakePricing(
  initial: readonly PricingVersion[] = [],
  results: Readonly<Record<string, PricingResult | null>> = {},
  details: {
    readonly hubPairs?: Readonly<Record<string, HubPairResult[] | null>>;
    readonly hubs?: Readonly<Record<string, HubResult[] | null>>;
    readonly simulations?: Readonly<Record<string, StoredSimulation[] | null>>;
    /** Versions whose deletion the API refuses, with the code it answers. */
    readonly removeRefusals?: Readonly<Record<string, 'run_active' | 'is_showcase'>>;
    /** The reason the API gives for refusing every simulation run; none: they are queued. */
    readonly simulateRefusal?: string;
    /** What the fake comparison varies per version id. */
    readonly comparison?: FakeComparisonDetails;
    /** The home page's showcase: none (default), one, or a failure it rejects with. */
    readonly showcase?: Showcase | null | Error;
  } = {},
): FakePricing {
  let stored = [...initial];
  const simulated: string[] = [];
  const replace = (next: PricingVersion) => {
    stored = stored.map((version) => (version.id === next.id ? next : version));
    return next;
  };
  const gateway: PricingGateway = {
    list: (instanceVersionId) =>
      Promise.resolve(stored.filter((version) => version.instanceVersionId === instanceVersionId)),
    get: (id) => Promise.resolve(stored.find((version) => version.id === id) ?? null),
    getShowcase: () => {
      const showcase = details.showcase ?? null;
      return showcase instanceof Error ? Promise.reject(showcase) : Promise.resolve(showcase);
    },
    result: (id) => {
      if (id in results) return Promise.resolve(results[id] ?? null);
      const found = stored.find((version) => version.id === id);
      return Promise.resolve(
        found?.state === 'result' ? samplePricingResult({ pricingVersionId: id }) : null,
      );
    },
    hubPairResults: (id) => {
      if (details.hubPairs !== undefined && id in details.hubPairs) {
        return Promise.resolve(details.hubPairs[id] ?? null);
      }
      const found = stored.find((version) => version.id === id);
      return Promise.resolve(found?.state === 'result' ? sampleHubPairResults() : null);
    },
    hubResults: (id) => {
      if (details.hubs !== undefined && id in details.hubs) {
        return Promise.resolve(details.hubs[id] ?? null);
      }
      const found = stored.find((version) => version.id === id);
      return Promise.resolve(found?.state === 'result' ? sampleHubResults() : null);
    },
    simulations: (id) => {
      if (details.simulations !== undefined && id in details.simulations) {
        return Promise.resolve(details.simulations[id] ?? null);
      }
      const found = stored.find((version) => version.id === id);
      return Promise.resolve(found?.state === 'result' ? sampleStoredSimulations() : null);
    },
    compare: (ids) => {
      const found = ids.map((id) => stored.find((version) => version.id === id));
      const missing = ids.filter((_, at) => found[at] === undefined);
      if (missing.length > 0) {
        return Promise.reject(new Error(`No pricing version ${missing.join(', ')}.`));
      }
      return Promise.resolve(
        fakeComparison(
          found.filter((version): version is PricingVersion => version !== undefined),
          details.comparison,
        ),
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
    simulate: (id) => {
      const found = stored.find((version) => version.id === id);
      if (found === undefined) return Promise.reject(new Error(`No pricing version ${id}.`));
      if (details.simulateRefusal !== undefined) {
        return Promise.resolve({ kind: 'refused', detail: details.simulateRefusal });
      }
      simulated.push(id);
      return Promise.resolve({ kind: 'queued', runId: `run-simulation-${found.letter}` });
    },
    remove: (id) => {
      const refusal = details.removeRefusals?.[id];
      if (refusal !== undefined) return Promise.resolve({ kind: refusal });
      stored = stored.filter((version) => version.id !== id);
      return Promise.resolve({ kind: 'deleted' });
    },
  };
  return { gateway, versions: () => stored, simulated: () => simulated };
}

/** The gateway with no pricing version at all. */
export function fakePricingGateway(initial: readonly PricingVersion[] = []): PricingGateway {
  return fakePricing(initial).gateway;
}
