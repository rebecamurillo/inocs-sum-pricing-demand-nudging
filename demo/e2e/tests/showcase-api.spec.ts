import type { APIResponse } from '@playwright/test';
import { buildFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';
import { createPricingVersion, finishVersion, putShowcase, runToResult } from '../support/pricing';

// The answers of `GET` and `PUT /api/v1/showcase` and the deletions the showcase refuses, on
// the stack. Home's and L-3's scenarios are home.spec.ts and home-states.spec.ts; these cover
// the shape Home draws and the problems a client can meet.
const problemType = 'application/problem+json';

interface Problem {
  code: string;
}

interface NumberResource {
  value: number;
  unit: string;
  source: string;
  group: string;
}

interface Point {
  lat: NumberResource;
  lon: NumberResource;
}

interface Showcase {
  pricing_version_id: string;
  period_id: string;
  marked_at: string;
  letter: string;
  instance_version_id: string;
  instance_version_name: string;
  headline: Record<string, NumberResource>;
  scope: { dataset_id: string; city: string; radius_km: NumberResource; period_label: string };
  car_share_flat: NumberResource;
  car_share_version: NumberResource;
  car_share_difference: NumberResource;
  flat_price: NumberResource;
  rule: { id: string; version: number; rule_current: boolean };
  study_circle: { centre: Point; radius_m: NumberResource };
  hubs: { id: string; centre: Point; outline: Record<string, unknown> | null }[];
  hub_pairs: {
    origin_hub: string;
    destination_hub: string;
    origin: Point;
    destination: Point;
    mean_bike_price: NumberResource;
    bike_rides: NumberResource;
  }[];
}

async function expectProblem(response: APIResponse, status: number, code: string) {
  expect(response.status()).toBe(status);
  expect(response.headers()['content-type']).toContain(problemType);
  expect(((await response.json()) as Problem).code).toBe(code);
}

/** Every `{value, unit, source, group}` in an answer, wherever it sits. */
function numbersIn(value: unknown): NumberResource[] {
  if (Array.isArray(value)) return value.flatMap(numbersIn);
  if (value === null || typeof value !== 'object') return [];
  const record = value as Record<string, unknown>;
  if ('value' in record && 'unit' in record && 'source' in record && 'group' in record) {
    return [record as unknown as NumberResource];
  }
  return Object.values(record).flatMap(numbersIn);
}

test.describe('Showcase API', () => {
  test('Showcase · none is set: GET answers 404 no_showcase; PUT refuses an unknown version, a draft and a malformed body', async ({
    request,
    control,
  }) => {
    await expectProblem(await request.get('/api/v1/showcase'), 404, 'no_showcase');

    const { version } = await buildFakeInstance(request, control);
    await expectProblem(
      await request.put('/api/v1/showcase', {
        data: { pricing_version_id: `${version}.Z` },
      }),
      404,
      'pricing_version_not_found',
    );

    const draft = await createPricingVersion(request, version);
    await expectProblem(
      await request.put('/api/v1/showcase', { data: { pricing_version_id: draft.id } }),
      409,
      'no_result',
    );

    const malformed = await request.put('/api/v1/showcase', { data: { period_id: 'p' } });
    expect(malformed.status()).toBe(422);

    // A refused PUT sets nothing.
    await expectProblem(await request.get('/api/v1/showcase'), 404, 'no_showcase');
  });

  test('Showcase · PUT on a finished version answers what Home draws, every number {value, unit, source, group} in the headline group', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    const { id, letter } = await finishVersion(request, version, 'Showcased');
    const result = (await (await request.get(`/api/v1/pricing-versions/${id}/result`)).json()) as {
      period_id: string;
    };

    // Without a period, the version's first one is shown.
    const marked = await request.put('/api/v1/showcase', { data: { pricing_version_id: id } });
    expect(marked.status()).toBe(200);
    const answer = (await marked.json()) as Showcase;
    const read = await request.get('/api/v1/showcase');
    expect(read.status()).toBe(200);
    expect((await read.json()) as Showcase).toEqual(answer);

    expect(answer).toMatchObject({
      pricing_version_id: id,
      period_id: result.period_id,
      letter,
      instance_version_id: version,
    });
    expect(Number.isNaN(Date.parse(answer.marked_at))).toBe(false);
    expect(answer.instance_version_name).not.toBe('');
    expect(answer.scope.city).toBe('Geneva');
    expect(answer.scope.dataset_id).not.toBe('');
    expect(answer.scope.period_label).not.toBe('');
    expect(answer.scope.radius_km).toMatchObject({ unit: 'km', source: 'input' });
    expect(answer.rule.id).toBe('balanced-score');
    expect(answer.rule.version).toBeGreaterThanOrEqual(1);
    expect(typeof answer.rule.rule_current).toBe('boolean');

    // Sources: the car shares come from the simulation, the flat price is an input, the pairs'
    // price and rides are derived from the model's flows.
    for (const share of [answer.car_share_flat, answer.car_share_version]) {
      expect(share.source).toBe('simulation');
      expect(share.value).toBeGreaterThanOrEqual(0);
      expect(share.value).toBeLessThanOrEqual(100);
    }
    expect(answer.car_share_difference.source).toBe('simulation');
    expect(answer.car_share_difference.value).toBeCloseTo(
      answer.car_share_flat.value - answer.car_share_version.value,
      6,
    );
    expect(answer.flat_price.source).toBe('input');
    expect(answer.flat_price.value).toBeGreaterThan(0);

    expect(answer.study_circle.radius_m.value).toBeGreaterThan(0);
    expect(answer.hubs.length).toBeGreaterThan(0);
    expect(answer.hub_pairs.length).toBeGreaterThan(0);
    const hubIds = new Set(answer.hubs.map((hub) => hub.id));
    for (const pair of answer.hub_pairs) {
      expect(hubIds.has(pair.origin_hub)).toBe(true);
      expect(hubIds.has(pair.destination_hub)).toBe(true);
      expect(pair.mean_bike_price.source).toBe('derived');
      expect(pair.bike_rides.source).toBe('derived');
      expect(pair.bike_rides.value).toBeGreaterThan(0);
    }
    // Ordered by origin, then destination hub.
    const keys = answer.hub_pairs.map((pair) => [pair.origin_hub, pair.destination_hub]);
    const sorted = [...keys].sort(([a, b], [c, d]) =>
      a === c ? (b ?? '').localeCompare(d ?? '') : (a ?? '').localeCompare(c ?? ''),
    );
    expect(keys).toEqual(sorted);

    const numbers = numbersIn(answer);
    expect(numbers.length).toBeGreaterThan(5);
    for (const number of numbers) {
      expect(number.group).toBe('headline');
      expect(typeof number.value).toBe('number');
      expect(number.unit).not.toBe('');
    }
  });

  test('Showcase · choosing another version replaces it; what holds the showcase is refused 409 is_showcase on its three DELETE routes', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    const first = await createPricingVersion(request, version, { name: 'First' });
    const second = await createPricingVersion(request, version, { name: 'Second' });
    const firstResult = await runToResult(request, first.id);
    const secondResult = await runToResult(request, second.id);

    await putShowcase(request, first.id, firstResult.period_id);
    expect(((await (await request.get('/api/v1/showcase')).json()) as Showcase).letter).toBe(
      first.letter,
    );

    // A period the version does not price is refused, and the showcase stays.
    await expectProblem(
      await request.put('/api/v1/showcase', {
        data: { pricing_version_id: second.id, period_id: 'no-such-period' },
      }),
      409,
      'no_result',
    );
    expect(((await (await request.get('/api/v1/showcase')).json()) as Showcase).letter).toBe(
      first.letter,
    );

    await putShowcase(request, second.id, secondResult.period_id);
    const showcase = (await (await request.get('/api/v1/showcase')).json()) as Showcase;
    expect(showcase.pricing_version_id).toBe(second.id);

    const built = (await (await request.get(`/api/v1/instance-versions/${version}`)).json()) as {
      instance_id: string;
    };
    await expectProblem(
      await request.delete(`/api/v1/pricing-versions/${second.id}`),
      409,
      'is_showcase',
    );
    await expectProblem(
      await request.delete(`/api/v1/instance-versions/${version}`),
      409,
      'is_showcase',
    );
    await expectProblem(
      await request.delete(`/api/v1/instance-versions/${version}?including_pricing_versions=true`),
      409,
      'is_showcase',
    );
    await expectProblem(
      await request.delete(`/api/v1/city-instances/${built.instance_id}`),
      409,
      'is_showcase',
    );
    expect((await request.get(`/api/v1/pricing-versions/${second.id}`)).status()).toBe(200);
    expect((await request.get(`/api/v1/instance-versions/${version}`)).status()).toBe(200);

    // The version that is no longer the showcase can go.
    expect((await request.delete(`/api/v1/pricing-versions/${first.id}`)).status()).toBe(204);
    expect((await request.get(`/api/v1/pricing-versions/${first.id}`)).status()).toBe(404);
    expect(
      ((await (await request.get('/api/v1/showcase')).json()) as Showcase).pricing_version_id,
    ).toBe(second.id);
  });
});
