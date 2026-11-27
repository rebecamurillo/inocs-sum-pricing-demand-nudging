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

const escaped = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

interface Problem {
  code: string;
  reasons?: { component: string; reason: string }[];
}

test.describe('Pricing · run', () => {
  test('L-2 · with a size-limited licence, Run is disabled with its reason; builds still start', async ({
    page,
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

    // The screen: L-1 of the built instance starts a draft, and L-2 says why it cannot run.
    await page.goto(`/#/lab/${built.version}`);
    await page.reload();
    await page.getByRole('main').getByRole('button', { name: '+ New pricing version' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/${escaped(built.version)}/pricing/[A-Z]+$`));
    await expect(page.getByRole('heading', { name: 'Pricing goals' })).toBeVisible();
    const sentence =
      "Pricing runs are off: this machine has Gurobi's size-limited licence, which cannot solve a city instance.";
    await expect(page.getByText(`${sentence} Stored results stay available.`)).toBeVisible();
    // The same reason is the note of the disabled primary.
    await expect(page.getByText(sentence, { exact: true })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    ).toBeDisabled();

    // A build needs no solver: an edit of the built instance still starts its build.
    await page.goto(`/#/lab/${built.version}`);
    await page.getByRole('main').getByRole('button', { name: 'Edit as a new version' }).click();
    await expect(
      page.getByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeVisible();
    await page.getByRole('textbox', { name: 'Travellers per hub pair, highest' }).fill('75');
    await expect(page.getByRole('button', { name: 'Save and build' })).toBeEnabled();
    await page.getByRole('button', { name: 'Save and build' }).click();
    await expect(page).toHaveURL(/#\/lab\/geneva-3km\.v2$/);
    await expect(page.getByRole('list', { name: 'Build steps' })).toBeVisible({ timeout: 30_000 });
  });

  test('L-2 · the goals explain themselves, autosave and run', async ({
    page,
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, 945);
    await page.goto(`/#/lab/${built.version}`);
    await page.reload();
    const menu = page.getByRole('complementary', { name: 'Menu' });
    await menu.getByRole('button', { name: '+ New pricing version' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/${escaped(built.version)}/pricing/A$`));

    // The defaults say what each goal means: break-even, and the order the model favours.
    await expect(page.getByText('Pricing version · pipeline step 5')).toBeVisible();
    await expect(page.getByText(/^Break-even at the lowest price\./)).toBeVisible();
    await expect(
      page.getByText(
        'The model favours, in this order: 1 Ridership · 2 Profit · 3 Station balance',
      ),
    ).toBeVisible();
    await expect(page.getByRole('region', { name: 'Default values' })).toBeVisible();
    await expect(menu.getByRole('button', { name: 'New version draft' })).toHaveAttribute(
      'aria-current',
      'page',
    );

    // Typing shows the change at once and is saved 500 ms after the last change.
    const lowest = page.getByRole('textbox', { name: 'Lowest price of a ride' });
    await lowest.fill('0.40');
    await expect(
      page.getByText(/On a ride sold at CHF 0\.40 the operator loses CHF 0\.20\./),
    ).toBeVisible();
    await expect(page.getByText(/^Draft saved · \d{2}:\d{2}$/)).toBeVisible();
    await page.reload();
    await expect(lowest).toHaveValue('0.40');

    // "ⓘ Explain" opens the details panel on that step's tab.
    await page.getByRole('button', { name: 'ⓘ Explain step 3' }).click();
    const panel = page.getByRole('complementary', { name: 'How the model reads these values' });
    await expect(panel.getByRole('tab', { name: '3 Weights' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(panel.getByText('What one bike ride is worth to the model')).toBeVisible();
    await panel.getByRole('button', { name: 'Close the details' }).click();
    await expect(panel).toHaveCount(0);

    // A broken rule names its value and disables the primary; restoring the value enables it.
    const options = page.getByRole('textbox', { name: 'Options shown per hub pair' });
    const run = page.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' });
    await options.fill('0');
    await expect(
      page.getByText('Options shown per hub pair must be at least 1: now 0'),
    ).toBeVisible();
    await expect(run).toBeDisabled();
    await options.fill('10');
    await expect(run).toBeEnabled();

    // The run waits for the pending save, seals the version and queues the pricing run.
    await run.click();
    await expect(
      menu.getByRole('button', { name: /^Version A (◷ queued|● running|✓ result)/ }),
    ).toBeVisible();
    await expect(menu.getByRole('button', { name: 'New version draft' })).toHaveCount(0);
    await expect(lowest).toHaveAttribute('readonly', '');

    // "Discard draft" on another draft asks, deletes it and opens L-1.
    await menu.getByRole('button', { name: '+ New pricing version' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/${escaped(built.version)}/pricing/B$`));
    await page.getByRole('button', { name: 'Discard draft' }).click();
    await expect(
      page.getByText('Discard this draft? Its values are removed; Version A stays as it is.'),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Discard draft' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/${escaped(built.version)}$`));
    await expect(menu.getByRole('button', { name: 'New version draft' })).toHaveCount(0);
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
