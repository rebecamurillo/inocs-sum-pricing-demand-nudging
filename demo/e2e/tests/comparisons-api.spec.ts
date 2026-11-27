import type { APIRequestContext } from '@playwright/test';
import { expect, test } from '../support/fixtures';
import { buildFakeInstance, queueFakeInstance } from '../support/build';
import { createPricingVersion, finishVersion, waitForRun } from '../support/pricing';

// The answer of `GET /api/v1/comparisons` that L-4 and its CSV read, on the stack. The screen's
// own scenarios are compare-versions.spec.ts; these cover the shape of the answer and the
// problems a client can meet.
const problemType = 'application/problem+json';
// Their own distances, so no other scenario's build finds these routes already computed.
const COMPARISON_DISTANCE_M = 985;
const OTHER_INSTANCE_DISTANCE_M = 995;

const SOURCES = ['model', 'package_summary', 'input', 'trip_planner', 'derived', 'simulation'];
const GOAL_NAMES = [
  'cost_bike_chf',
  'lowest_price_chf',
  'ridership_weight',
  'station_balance_weight',
  'flat_price_per_ride_chf',
  'pt_fare_chf',
  'car_parking_fee_chf',
  'max_displayed_options',
];

interface NumberAnswer {
  value: number | string;
  unit: string;
  source: string;
  group: string;
}

interface RowAnswer {
  key: string;
  values: Record<string, NumberAnswer | null>;
  changes: Record<string, NumberAnswer | null>;
  flats: Record<string, NumberAnswer | null>;
  best: string[];
}

interface ComparisonAnswer {
  instance_version: { id: string; name: string };
  period: { id: string; name: string };
  versions: {
    id: string;
    letter: string;
    name: string;
    goals: Record<string, NumberAnswer>;
    package: { fingerprint: string; commit: string | null };
    simulations: { price_scheme: string; rule_id: string; rule_current: boolean }[];
    model_split: Record<string, NumberAnswer>;
    flat_reference: string;
    solve_key: string;
  }[];
  flat_references: {
    id: string;
    simulation_key: string;
    letters: string[];
    values: Record<string, NumberAnswer>;
    cost_bike_chf: NumberAnswer;
    rule_current: boolean;
  }[];
  groups: { name: string; rows: RowAnswer[] }[];
  pair_differences: {
    a: string;
    b: string;
    pairs: { origin_hub: string; destination_hub: string; price_difference: NumberAnswer }[];
  };
  hub_differences: { hub_id: string; price_b_minus_flat: NumberAnswer | null }[];
  identical_solves: string[][];
}

const MARKED_ROWS = ['share_car', 'ridership', 'profit', 'stations_empty_or_full'];

/** The numbers present in these per-column maps (a column without a value is null). */
function presentIn(maps: Record<string, NumberAnswer | null>[]): NumberAnswer[] {
  return maps.flatMap((map) =>
    Object.values(map).filter((value): value is NumberAnswer => value !== null),
  );
}

/** The distinct sources of the numbers present in these maps. */
function sourcesOf(maps: Record<string, NumberAnswer | null>[]): string[] {
  return [...new Set(presentIn(maps).map((value) => value.source))];
}

interface Problem {
  code: string;
}

const compare = (request: APIRequestContext, ids: string[], period?: string) => {
  const query = new URLSearchParams({ pricing_versions: ids.join(',') });
  if (period !== undefined) query.set('period', period);
  return request.get(`/api/v1/comparisons?${query.toString()}`);
};

/** Every `{value, unit, source, group}` of the answer, wherever it sits. */
function numbersIn(item: unknown): NumberAnswer[] {
  if (item === null || typeof item !== 'object') return [];
  if ('source' in item && 'unit' in item && 'value' in item && 'group' in item) {
    return [item as NumberAnswer];
  }
  return Object.values(item).flatMap(numbersIn);
}

test.describe('Comparisons · API', () => {
  test('Comparisons · three versions answer in letter order with one flat column per flat simulation, the identical solve and the differences of the last two', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, COMPARISON_DISTANCE_M);
    const a = await finishVersion(request, version, 'Baseline');
    const b = await finishVersion(request, version, 'Heavier ridership', { ridership_weight: 20 });
    // A's goals with another flat price: the solve does not read it, so A and C share one solve
    // and C is simulated against a flat column of its own.
    const c = await finishVersion(request, version, 'Dearer flat price', {
      flat_price_per_ride_chf: 1.5,
    });

    const answered = await compare(request, [c.id, a.id, b.id]);
    expect(answered.status()).toBe(200);
    const answer = (await answered.json()) as ComparisonAnswer;

    // Once at the top: the instance version and the default period.
    expect(answer.instance_version).toEqual({ id: version, name: 'Geneva 3 km v1' });
    expect(answer.period.id).toBe(`${version}.mon-08`);
    expect(answer.period.name).not.toBe('');

    // The versions in letter order, whatever the order asked, each with its eight goals as inputs
    // and its two simulations, model's prices first, with the worker's current rule.
    expect(answer.versions.map((item) => [item.letter, item.name])).toEqual([
      ['A', 'Baseline'],
      ['B', 'Heavier ridership'],
      ['C', 'Dearer flat price'],
    ]);
    for (const item of answer.versions) {
      expect(Object.keys(item.goals).sort()).toEqual([...GOAL_NAMES].sort());
      for (const goal of Object.values(item.goals)) {
        expect(goal).toMatchObject({ source: 'input', group: 'headline' });
      }
      expect(item.simulations.map((sim) => sim.price_scheme)).toEqual(['model_prices', 'flat']);
      expect(item.simulations.every((sim) => sim.rule_current)).toBe(true);
      expect(item.package.fingerprint).not.toBe('');
    }
    expect(answer.versions[2]?.goals.flat_price_per_ride_chf?.value).toBe(1.5);

    // Every number of the answer carries a known source and group.
    const numbers = numbersIn(answer);
    expect(numbers.length).toBeGreaterThan(0);
    for (const number of numbers) {
      expect(SOURCES).toContain(number.source);
      expect(['headline', 'advanced']).toContain(number.group);
    }

    // A and B share a flat simulation and cost of one ride: one column; C has its own.
    expect(answer.flat_references.map((ref) => ref.letters)).toEqual([['A', 'B'], ['C']]);
    const [shared, own] = answer.flat_references;
    expect(answer.versions.map((item) => item.flat_reference)).toEqual([
      shared?.id,
      shared?.id,
      own?.id,
    ]);
    expect(shared?.simulation_key).not.toBe(own?.simulation_key);
    for (const ref of answer.flat_references) {
      expect(ref.rule_current).toBe(true);
      expect(ref.cost_bike_chf).toMatchObject({ unit: 'chf', source: 'input' });
    }

    // The groups in the order the screen and the CSV read them.
    expect(answer.groups.map((group) => group.name)).toEqual([
      'simulated',
      'model',
      'derived',
      'goals_that_differ',
      'solver',
    ]);
    const group = (name: string) => answer.groups.find((item) => item.name === name)?.rows ?? [];

    // Simulated travellers: three modes only, a value for every version and every flat column,
    // and each version's change against its own flat column.
    const simulated = group('simulated');
    expect(simulated.map((row) => row.key).slice(0, 3)).toEqual([
      'share_car',
      'share_pt_only',
      'share_pt_bike',
    ]);
    for (const row of simulated) {
      expect(Object.keys(row.values)).toEqual(['A', 'B', 'C']);
      expect(Object.keys(row.flats).sort()).toEqual([shared?.id, own?.id].sort());
    }
    expect(sourcesOf(simulated.flatMap((row) => [row.values, row.changes]))).toEqual([
      'simulation',
    ]);
    const carChange = simulated.find((row) => row.key === 'share_car')?.changes.A;
    expect(carChange?.unit).toBe('share_points');

    // The model's rows have no flat column; its numbers are the model's.
    for (const row of group('model')) expect(row.flats).toEqual({});
    expect(sourcesOf(group('model').map((row) => row.values))).toEqual(['model']);
    expect(sourcesOf(group('derived').map((row) => row.values))).toEqual(['derived']);

    // Only the goals not the same for every version: B's ridership weight and C's flat price.
    expect(group('goals_that_differ').map((row) => row.key)).toEqual([
      'ridership_weight',
      'flat_price_per_ride_chf',
    ]);
    const solverGroups = presentIn(group('solver').map((row) => row.values)).map(
      (value) => value.group,
    );
    expect([...new Set(solverGroups)]).toEqual(['advanced']);

    // Best values are among versions only, and only on the four marked rows.
    const rows = answer.groups.flatMap((item) => item.rows);
    for (const row of rows) expect(['A', 'B', 'C']).toEqual(expect.arrayContaining(row.best));
    const unmarked = rows.filter((row) => !MARKED_ROWS.includes(row.key));
    expect(unmarked.flatMap((row) => row.best)).toEqual([]);

    // A and C are the same stored solve; the differences are C − B.
    expect(answer.identical_solves).toEqual([['A', 'C']]);
    expect(answer.versions[0]?.solve_key).toBe(answer.versions[2]?.solve_key);
    expect(answer.pair_differences.a).toBe('B');
    expect(answer.pair_differences.b).toBe('C');
    for (const pair of answer.pair_differences.pairs) {
      expect(pair.price_difference.source).toBe('derived');
    }
    const sizes = answer.pair_differences.pairs.map((pair) =>
      Math.abs(Number(pair.price_difference.value)),
    );
    expect(sizes).toEqual([...sizes].sort((x, y) => y - x));
    expect(answer.hub_differences.length).toBeGreaterThan(0);

    // Asking for the default period by its id gives the same answer.
    const byPeriod = await compare(request, [a.id, b.id, c.id], answer.period.id);
    expect(byPeriod.status()).toBe(200);
    expect(await byPeriod.json()).toEqual(answer);

    // Two versions that share one solve differ at no hub pair.
    const same = (await (await compare(request, [a.id, c.id])).json()) as ComparisonAnswer;
    expect(same.identical_solves).toEqual([['A', 'C']]);
    expect(same.pair_differences.pairs).toEqual([]);
  });

  test('Comparisons · fewer than two or more than four versions are 422, an unknown version 404, a draft 409 no_result, versions of two instances 409 different_instances', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, COMPARISON_DISTANCE_M);
    const a = await finishVersion(request, version, 'Baseline');
    const b = await finishVersion(request, version, 'Heavier ridership', { ridership_weight: 20 });

    const counted = [
      await compare(request, [a.id]),
      await compare(request, [a.id, a.id]),
      await compare(request, [a.id, b.id, 'x.v1.C', 'x.v1.D', 'x.v1.E']),
    ];
    for (const response of counted) {
      expect(response.status()).toBe(422);
      expect(response.headers()['content-type']).toContain(problemType);
      expect(((await response.json()) as Problem).code).toBe('version_count_out_of_range');
    }
    const missing = await request.get('/api/v1/comparisons');
    expect(missing.status()).toBe(422);
    expect(missing.headers()['content-type']).toContain(problemType);

    const unknown = await compare(request, [a.id, `${version}.Z`]);
    expect(unknown.status()).toBe(404);
    expect(unknown.headers()['content-type']).toContain(problemType);
    expect(((await unknown.json()) as Problem).code).toBe('pricing_version_not_found');

    const draft = await createPricingVersion(request, version, { name: 'Not run' });
    const unrun = await compare(request, [a.id, draft.id]);
    expect(unrun.status()).toBe(409);
    expect(unrun.headers()['content-type']).toContain(problemType);
    expect(((await unrun.json()) as Problem).code).toBe('no_result');

    // A period the versions do not price has no result either.
    const noPeriod = await compare(request, [a.id, b.id], `${version}.sun-03`);
    expect(noPeriod.status()).toBe(409);
    expect(((await noPeriod.json()) as Problem).code).toBe('no_result');

    const other = await queueFakeInstance(request, control, {
      name: 'Lausanne 3 km',
      minOdDistanceM: OTHER_INSTANCE_DISTANCE_M,
    });
    await waitForRun(request, other.runId, 'succeeded');
    const elsewhere = await finishVersion(request, other.version, 'Elsewhere');
    const mixed = await compare(request, [a.id, elsewhere.id]);
    expect(mixed.status()).toBe(409);
    expect(mixed.headers()['content-type']).toContain(problemType);
    expect(((await mixed.json()) as Problem).code).toBe('different_instances');
  });
});
