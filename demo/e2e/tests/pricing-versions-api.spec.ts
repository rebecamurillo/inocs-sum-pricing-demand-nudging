import { expect, test } from '../support/fixtures';
import { buildFakeInstance } from '../support/build';
import {
  createPricingVersion,
  putShowcase,
  runPricingVersion,
  runToResult,
  simulatePricingVersion,
  waitForRun,
} from '../support/pricing';

// The answers of the pricing-version resources the L-2 and L-3 screens read and write, on the
// stack. The screens' own scenarios are lab-pricing.spec.ts and lab-result.spec.ts; these cover
// the problems a client can meet.
const problemType = 'application/problem+json';
// Its own distance, so no other scenario's build finds this one's routes already computed.
const API_DISTANCE_M = 975;

interface Problem {
  code: string;
  run_id?: string | null;
  errors?: { field: string }[];
  pricing_failures?: { field: string; value: number; passed: boolean; message: string }[];
}

interface RuleResult {
  rule: string;
  passed: boolean;
  field: string;
  value: number;
  message: string;
}

interface PricingVersion {
  id: string;
  instance_version_id: string;
  letter: string;
  name: string;
  status: string;
  state: string;
  based_on_id: string | null;
  run_id: string | null;
  goals: Record<string, number | string>;
  periods: { id: string; key: string; label: string }[];
  rules: RuleResult[];
}

const versionOf = async (response: { json: () => Promise<unknown> }) =>
  (await response.json()) as PricingVersion;

test.describe('Pricing versions · API', () => {
  test('Pricing versions · a draft on a built version is A with the Monday 08:00 period and every rule passing; an unbuilt version is 409 instance_not_built', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, API_DISTANCE_M);

    const created = await request.post(`/api/v1/instance-versions/${version}/pricing-versions`, {
      data: {},
    });
    expect(created.status()).toBe(201);
    const draft = await versionOf(created);
    expect(created.headers().location).toBe(`/api/v1/pricing-versions/${draft.id}`);
    expect(draft).toMatchObject({
      id: `${version}.A`,
      instance_version_id: version,
      letter: 'A',
      status: 'draft',
      state: 'draft',
      based_on_id: null,
      run_id: null,
    });
    expect(draft.periods).toEqual([expect.objectContaining({ id: `${version}.mon-08` })]);
    expect(draft.rules.length).toBeGreaterThan(0);
    expect(draft.rules.every((rule) => rule.passed)).toBe(true);

    const listed = await request.get(`/api/v1/instance-versions/${version}/pricing-versions`);
    expect(listed.status()).toBe(200);
    const items = ((await listed.json()) as { items: PricingVersion[] }).items;
    expect(items.map((item) => item.id)).toEqual([draft.id]);

    // A new draft of the instance is not built yet: no pricing version starts on it.
    const instanceId = version.replace(/\.v1$/, '');
    const unbuilt = await request.post(`/api/v1/city-instances/${instanceId}/versions`, {
      data: { based_on_id: version },
    });
    expect(unbuilt.status()).toBe(201);
    const unbuiltId = ((await unbuilt.json()) as { id: string }).id;
    const refused = await request.post(`/api/v1/instance-versions/${unbuiltId}/pricing-versions`, {
      data: {},
    });
    expect(refused.status()).toBe(409);
    expect(refused.headers()['content-type']).toContain(problemType);
    expect(((await refused.json()) as Problem).code).toBe('instance_not_built');
  });

  test('Pricing versions · an unknown id answers a 404 problem with its code; an unknown based_on is 422 unknown_based_on', async ({
    request,
    control,
  }) => {
    const unknownPricing = [
      await request.get('/api/v1/pricing-versions/nowhere.v1.A'),
      await request.patch('/api/v1/pricing-versions/nowhere.v1.A', { data: { pt_fare_chf: 3 } }),
      await request.delete('/api/v1/pricing-versions/nowhere.v1.A'),
      await request.post('/api/v1/pricing-versions/nowhere.v1.A/runs'),
      await request.post('/api/v1/pricing-versions/nowhere.v1.A/simulations'),
      await request.get('/api/v1/pricing-versions/nowhere.v1.A/simulations'),
    ];
    for (const response of unknownPricing) {
      expect(response.status()).toBe(404);
      expect(response.headers()['content-type']).toContain(problemType);
      expect(((await response.json()) as Problem).code).toBe('pricing_version_not_found');
    }

    const unknownInstance = [
      await request.get('/api/v1/instance-versions/nowhere.v1/pricing-versions'),
      await request.post('/api/v1/instance-versions/nowhere.v1/pricing-versions', { data: {} }),
    ];
    for (const response of unknownInstance) {
      expect(response.status()).toBe(404);
      expect(((await response.json()) as Problem).code).toBe('instance_version_not_found');
    }

    const { version } = await buildFakeInstance(request, control, API_DISTANCE_M);
    const copy = await request.post(`/api/v1/instance-versions/${version}/pricing-versions`, {
      data: { based_on: `${version}.Z` },
    });
    expect(copy.status()).toBe(422);
    expect(copy.headers()['content-type']).toContain(problemType);
    expect(((await copy.json()) as Problem).code).toBe('unknown_based_on');
  });

  test('Pricing versions · a broken goal is saved and reported with its value; running the draft is 409 rule_broken; a non-number or a blank name is 422', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, API_DISTANCE_M);
    const { id } = await createPricingVersion(request, version);

    const patched = await request.patch(`/api/v1/pricing-versions/${id}`, {
      data: { lowest_price_chf: -1, max_displayed_options: 0 },
    });
    expect(patched.status()).toBe(200);
    const draft = await versionOf(patched);
    expect(draft.goals).toMatchObject({ lowest_price_chf: -1, max_displayed_options: 0 });
    const failed = draft.rules.filter((rule) => !rule.passed);
    expect(failed).toEqual([
      expect.objectContaining({
        field: 'lowest_price_chf',
        value: -1,
        message: 'Lowest price of a ride must be 0 or more: now -1',
      }),
      expect.objectContaining({
        field: 'max_displayed_options',
        value: 0,
        message: 'Options shown per hub pair must be at least 1: now 0',
      }),
    ]);

    const run = await runPricingVersion(request, id);
    expect(run.status()).toBe(409);
    expect(run.headers()['content-type']).toContain(problemType);
    const problem = (await run.json()) as Problem;
    expect(problem.code).toBe('rule_broken');
    expect(problem.pricing_failures?.map((failure) => failure.field)).toEqual([
      'lowest_price_chf',
      'max_displayed_options',
    ]);
    expect((await versionOf(await request.get(`/api/v1/pricing-versions/${id}`))).status).toBe(
      'draft',
    );

    const invalid: Record<string, unknown>[] = [{ pt_fare_chf: 'three' }, { name: '   ' }];
    for (const data of invalid) {
      const response = await request.patch(`/api/v1/pricing-versions/${id}`, { data });
      expect(response.status()).toBe(422);
      expect(response.headers()['content-type']).toContain(problemType);
    }
  });

  test('Pricing versions · a draft has no result: the result lists are 404 no_result, its simulations an empty list, simulating it 409 no_result', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, API_DISTANCE_M);
    const { id } = await createPricingVersion(request, version);

    for (const path of ['result', 'hub-pair-results', 'hub-results']) {
      const response = await request.get(`/api/v1/pricing-versions/${id}/${path}`);
      expect(response.status()).toBe(404);
      expect(response.headers()['content-type']).toContain(problemType);
      expect(((await response.json()) as Problem).code).toBe('no_result');
    }

    const simulations = await request.get(`/api/v1/pricing-versions/${id}/simulations`);
    expect(simulations.status()).toBe(200);
    expect(await simulations.json()).toEqual({ items: [] });

    const simulate = await simulatePricingVersion(request, id);
    expect(simulate.status()).toBe(409);
    expect(((await simulate.json()) as Problem).code).toBe('no_result');
  });

  test('Pricing versions · while its run is running a version is 409 run_active to run or delete; once run it is sealed and already_run', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, API_DISTANCE_M);
    const { id } = await createPricingVersion(request, version);
    await control.setPricingModel({ hold_at: 'pricing_model' });

    const queued = await runPricingVersion(request, id);
    expect(queued.status()).toBe(202);
    const runId = ((await queued.json()) as { id: string }).id;
    expect(queued.headers().location).toBe(`/api/v1/runs/${runId}`);
    await waitForRun(request, runId, 'running');

    for (const response of [
      await runPricingVersion(request, id),
      await request.delete(`/api/v1/pricing-versions/${id}`),
    ]) {
      expect(response.status()).toBe(409);
      const problem = (await response.json()) as Problem;
      expect(problem.code).toBe('run_active');
      expect(problem.run_id).toBe(runId);
    }
    const sealedPatch = await request.patch(`/api/v1/pricing-versions/${id}`, {
      data: { pt_fare_chf: 4 },
    });
    expect(sealedPatch.status()).toBe(409);
    expect(((await sealedPatch.json()) as Problem).code).toBe('version_sealed');

    await control.setPricingModel({});
    await control.releaseRun(runId);
    await waitForRun(request, runId, 'succeeded');

    const finished = await versionOf(await request.get(`/api/v1/pricing-versions/${id}`));
    expect(finished).toMatchObject({ status: 'sealed', state: 'result', run_id: runId });
    const again = await runPricingVersion(request, id);
    expect(again.status()).toBe(409);
    expect(((await again.json()) as Problem).code).toBe('already_run');
  });

  test('Pricing versions · a finished version is duplicated as a draft with its goals; the showcase is 409 is_showcase; a deleted letter is not given again', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, API_DISTANCE_M);
    const first = await createPricingVersion(request, version);
    const patched = await request.patch(`/api/v1/pricing-versions/${first.id}`, {
      data: { pt_fare_chf: 3.5 },
    });
    expect(patched.status()).toBe(200);
    const result = await runToResult(request, first.id);
    const source = await versionOf(await request.get(`/api/v1/pricing-versions/${first.id}`));

    const copy = await request.post(`/api/v1/instance-versions/${version}/pricing-versions`, {
      data: { based_on: first.id },
    });
    expect(copy.status()).toBe(201);
    const duplicate = await versionOf(copy);
    expect(duplicate).toMatchObject({
      letter: 'B',
      status: 'draft',
      based_on_id: first.id,
      run_id: null,
      goals: source.goals,
    });

    await putShowcase(request, first.id, result.period_id);
    const showcase = await request.delete(`/api/v1/pricing-versions/${first.id}`);
    expect(showcase.status()).toBe(409);
    expect(((await showcase.json()) as Problem).code).toBe('is_showcase');

    const discarded = await request.delete(`/api/v1/pricing-versions/${duplicate.id}`);
    expect(discarded.status()).toBe(204);
    expect((await request.get(`/api/v1/pricing-versions/${duplicate.id}`)).status()).toBe(404);

    const next = await createPricingVersion(request, version);
    expect(next.letter).toBe('C');
    const listed = (await (
      await request.get(`/api/v1/instance-versions/${version}/pricing-versions`)
    ).json()) as { items: PricingVersion[] };
    expect(listed.items.map((item) => item.letter)).toEqual(['A', 'C']);
  });
});
