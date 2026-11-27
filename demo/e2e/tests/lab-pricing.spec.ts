import { expect, test } from '../support/fixtures';
import { buildFakeInstance, queueFakeInstance } from '../support/build';
import {
  createPricingVersion,
  runPricingVersion,
  simulatePricingVersion,
  waitForRun,
  waitForSimulationRule,
} from '../support/pricing';

// Running a pricing version through the API (the screens that start it are stories 3.7 and 3.8).
const SOLVER_REASON = 'Size-limited Gurobi licence: a model of 2001 variables is refused.';
// Its own distance, so no other scenario's build finds this one's routes already computed.
const PRICING_DISTANCE_M = 940;
const KEPT_REASON = 'kept: these goals were already solved on this instance';

interface Problem {
  code: string;
  reasons?: { component: string; reason: string }[];
}

test.describe('Pricing · run', () => {
  test('L-2 · with a size-limited licence, Run is disabled with its reason; builds still start', async ({
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, PRICING_DISTANCE_M);
    const draft = await createPricingVersion(request, built.version);

    await control.makeLimited('solver', SOLVER_REASON);

    const refused = await runPricingVersion(request, draft.id);
    expect(refused.status()).toBe(503);
    const problem = (await refused.json()) as Problem;
    expect(problem.code).toBe('component_unavailable');
    expect(problem.reasons).toEqual([{ component: 'solver', reason: SOLVER_REASON }]);
    // Nothing was sealed or queued by the refusal.
    const stillDraft = (await (
      await request.get(`/api/v1/pricing-versions/${draft.id}`)
    ).json()) as { status: string };
    expect(stillDraft.status).toBe('draft');

    // A build needs no solver: another instance starts and builds with the licence limited.
    const second = await queueFakeInstance(request, control, {
      name: 'Geneva second',
      minOdDistanceM: PRICING_DISTANCE_M,
    });
    await waitForRun(request, second.runId, 'succeeded');
  });

  test('Pricing · a run seals the version, runs the pricing model then the traveller simulation; a version differing only in its flat price keeps the pricing model', async ({
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, PRICING_DISTANCE_M);
    const first = await createPricingVersion(request, built.version);

    const queued = await runPricingVersion(request, first.id);

    expect(queued.status()).toBe(202);
    const run = (await queued.json()) as { id: string; kind: string; state: string };
    expect(queued.headers().location).toBe(`/api/v1/runs/${run.id}`);
    expect(run).toMatchObject({ kind: 'pricing', state: 'queued' });
    const sealed = (await (await request.get(`/api/v1/pricing-versions/${first.id}`)).json()) as {
      status: string;
    };
    expect(sealed.status).toBe('sealed');

    const done = await waitForRun(request, run.id, 'succeeded');
    expect(done.subject).toEqual({ type: 'pricing_version', id: first.id });
    expect(done.steps.map((step) => [step.step, step.state])).toEqual([
      ['pricing_model', 'done'],
      ['traveller_simulation', 'done'],
    ]);
    const result = (await (await request.get(`/api/v1/pricing-versions/${first.id}`)).json()) as {
      state: string;
    };
    expect(result.state).toBe('result');
    expect((await runPricingVersion(request, first.id)).status()).toBe(409);

    // The same goals but the flat price: the solver's inputs are the same, so its result is kept.
    const second = await createPricingVersion(request, built.version, { based_on: first.id });
    const changed = await request.patch(`/api/v1/pricing-versions/${second.id}`, {
      data: { flat_price_per_ride_chf: 2.5 },
    });
    expect(changed.status()).toBe(200);
    const rerun = (await (await runPricingVersion(request, second.id)).json()) as { id: string };

    const kept = await waitForRun(request, rerun.id, 'succeeded');
    expect(kept.steps[0]).toMatchObject({
      step: 'pricing_model',
      state: 'kept',
      reason: KEPT_REASON,
    });
    expect(kept.steps[1]).toMatchObject({ step: 'traveller_simulation', state: 'done' });
  });

  test('Pricing · simulating a stored version again with a staged rule adds the new rule’s simulations without solving', async ({
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, PRICING_DISTANCE_M);
    const version = await createPricingVersion(request, built.version);
    const queued = (await (await runPricingVersion(request, version.id)).json()) as { id: string };
    await waitForRun(request, queued.id, 'succeeded');
    await waitForSimulationRule(request, 1);

    // A new rule version, with the solver unavailable: a simulation reads the stored solve.
    await control.setPricingModel({
      simulation_rule: { version: 2, price_weight: 0.6, time_weight: 0.4 },
    });
    await control.makeUnavailable('solver', SOLVER_REASON);
    await waitForSimulationRule(request, 2);

    const simulate = await simulatePricingVersion(request, version.id);

    expect(simulate.status()).toBe(202);
    const run = (await simulate.json()) as { id: string; kind: string; state: string };
    expect(simulate.headers().location).toBe(`/api/v1/runs/${run.id}`);
    expect(run).toMatchObject({ kind: 'simulation', state: 'queued' });
    const done = await waitForRun(request, run.id, 'succeeded');
    expect(done.steps.map((step) => [step.step, step.state])).toEqual([
      ['traveller_simulation', 'done'],
    ]);

    const listed = (await (
      await request.get(`/api/v1/pricing-versions/${version.id}/simulations`)
    ).json()) as {
      items: { price_scheme: string; rule_version: number; rule_current: boolean }[];
    };
    expect(
      listed.items.map((item) => [item.price_scheme, item.rule_version, item.rule_current]),
    ).toEqual([
      ['flat', 1, false],
      ['flat', 2, true],
      ['model_prices', 1, false],
      ['model_prices', 2, true],
    ]);
    const stored = (await (await request.get(`/api/v1/pricing-versions/${version.id}`)).json()) as {
      state: string;
    };
    expect(stored.state).toBe('result');

    const again = await simulatePricingVersion(request, version.id);
    expect(again.status()).toBe(409);
    expect(((await again.json()) as Problem).code).toBe('simulation_current');
  });
});
