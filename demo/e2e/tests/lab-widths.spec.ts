import type { Page } from '@playwright/test';
import { awaitPackageDefaults, buildFakeInstance, queueFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';
import { pricedPair, sameHubPair } from '../support/trips';
import {
  createPricingVersion,
  finishVersion,
  runPricingVersion,
  runToResult,
  waitForRun,
  waitForSimulationRule,
} from '../support/pricing';

const viewports = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1280, height: 720 },
];

/** Every size with and without Aa: no page scroll, and the card, map, footer and run line in view. */
async function holdsAtEverySize(
  page: Page,
  card: ReturnType<Page['getByRole']> | null,
  runLine: string | RegExp = 'No run in progress',
  // L-2 has no map: its card takes the full width.
  withMap = true,
) {
  const aa = page.getByRole('button', { name: 'Larger text for a projector' });

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    for (const large of [false, true]) {
      await expect(aa).toHaveAttribute('aria-pressed', String(large));

      const size = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight,
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        baseFont: getComputedStyle(document.body).fontSize,
        rootFont: getComputedStyle(document.documentElement).fontSize,
      }));
      expect(size.scrollWidth).toBeLessThanOrEqual(size.innerWidth);
      expect(size.scrollHeight).toBeLessThanOrEqual(size.innerHeight);
      expect(size.rootFont).toBe(large ? '20.8px' : '16px');
      expect(size.baseFont).toBe(large ? '16.9px' : '13px');
      // The body does not scroll, so clipped content would not show in the sizes above.
      await expect(page.getByRole('contentinfo')).toBeInViewport({ ratio: 1 });
      await expect(page.getByText(runLine)).toBeInViewport({ ratio: 1 });
      await expect(aa).toBeInViewport({ ratio: 1 });
      // The map pane is part of the held view (the e2e stack has no basemap file: ground colour).
      if (withMap) {
        await expect(page.getByRole('region', { name: 'Map' })).toBeInViewport({ ratio: 1 });
      }
      if (card !== null) await expect(card).toBeInViewport();
      await aa.click();
    }
  }
}

test.describe('Lab', () => {
  test('Lab · every built view holds at 1440, 1280 and 1280 × 720 with Aa', async ({
    page,
    request,
    control,
  }) => {
    await page.goto('/');
    await expect(page.getByRole('main')).toBeVisible();

    await holdsAtEverySize(page, null);

    // The new-instance form, then the edit and rule-broken states of a built instance.
    const datasetId = await control.insertCityDataset();
    await awaitPackageDefaults(request, datasetId);
    await page.goto('/');
    await page.getByRole('button', { name: '+ New', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'New city instance' })).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));

    const name = page.getByRole('textbox', { name: 'Name', exact: true });
    await name.fill('Geneva 2 km');
    await name.press('Enter');
    await expect(
      page.getByRole('heading', { name: 'Geneva 2 km · new version (draft)' }),
    ).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));

    const { version } = await buildFakeInstance(request, control);
    await page.goto(`/#/lab/${version}`);
    // The page was loaded before this instance existed: read the menu again.
    await page.reload();
    await page.getByRole('button', { name: 'Edit as a new version' }).click();
    await expect(
      page.getByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));

    await page.getByRole('textbox', { name: 'Grouping distance', exact: true }).fill('1000');
    await expect(page.getByText('One rule is not met.')).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));

    // The building, queued, failed and cancelled states: one run held at its routes step, a
    // second instance queued behind it.
    await control.setPricingModel({ hold_at: 'routes' });
    const first = await queueFakeInstance(request, control, {
      name: 'Geneva 4 km',
      minOdDistanceM: 990,
    });
    await queueFakeInstance(request, control, {
      name: 'Geneva 5 km',
      minOdDistanceM: 995,
      datasetId: first.datasetId,
    });
    const buildingLine = /^● Geneva 4 km v1 building · /;
    await page.goto(`/#/lab/${first.version}`);
    await page.reload();
    await expect(page.getByRole('list', { name: 'Build steps' })).toBeVisible({
      timeout: 30_000,
    });
    await holdsAtEverySize(page, page.getByRole('main'), buildingLine);

    await page.goto('/#/lab/geneva-5km.v1');
    await page.reload();
    await expect(
      page.getByText(/^Queued, 2nd in line: Geneva 4 km v1 is building\./),
    ).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), buildingLine);

    await page.getByRole('button', { name: 'Remove from the queue' }).click();
    await page.getByRole('button', { name: 'Remove from the queue' }).click();
    await expect(
      page.getByText(
        /^Run cancelled during Area on \d{1,2} [A-Z][a-z]{2} \d{4}\. Steps before it are kept\.$/,
      ),
    ).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), buildingLine);

    // The held run goes on to a failure at its routes step.
    await control.setPricingModel({ fail_at: { step: 'routes', code: 'stage_error' } });
    await control.releaseRun(first.runId);
    await page.goto(`/#/lab/${first.version}`);
    await expect(
      page.getByText(
        /^✕ Routes failed: an error stopped the step\. The details are in the run's log\./,
      ),
    ).toBeVisible({ timeout: 30_000 });
    await holdsAtEverySize(page, page.getByRole('main'));

    // The two delete confirmations, open: L-1's (this version) and the menu row's (the instance).
    await page.getByRole('main').getByRole('button', { name: 'Delete…' }).click();
    await expect(
      page.getByText(/^Delete Geneva 4 km v1\? This removes the instance version\./),
    ).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));
    await page.getByRole('button', { name: 'Keep' }).click();

    const menu = page.getByRole('complementary', { name: 'Menu' });
    await menu.getByRole('button', { name: 'Delete…' }).click();
    await expect(
      page.getByText('Delete Geneva 4 km? This removes its 1 version (v1). This cannot be undone.'),
    ).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));
    await page.getByRole('button', { name: 'Keep' }).click();

    // The same confirmation on a version used by pricing versions.
    await createPricingVersion(request, version);
    await createPricingVersion(request, version);
    await page.goto(`/#/lab/${version}`);
    await page.reload();
    await page.getByRole('main').getByRole('button', { name: 'Delete…' }).click();
    await expect(
      page.getByText(
        /^Delete Geneva 3 km v1\? This removes the instance version and its 2 pricing versions with their results \(A, B\)\./,
      ),
    ).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));
    await page.getByRole('button', { name: 'Keep' }).click();

    // L-2: a new version, the lowest price under the cost, and the details panel open.
    await page.goto(`/#/lab/${version}/pricing/A`);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Pricing goals' })).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), 'No run in progress', false);

    await page.getByRole('textbox', { name: 'Lowest price of a ride' }).fill('0.40');
    await expect(page.getByText('Incentive: the lowest price is under the cost.')).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), 'No run in progress', false);

    await page.getByRole('button', { name: 'ⓘ Explain step 2' }).click();
    await expect(page.getByRole('tab', { name: '2 Cost and price' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await holdsAtEverySize(page, page.getByRole('main'), 'No run in progress', false);
    await page.getByRole('tab', { name: '3 Weights' }).click();
    await holdsAtEverySize(page, page.getByRole('main'), 'No run in progress', false);

    // L-3: the result of a finished version, and its loading state (the answer held until the
    // skeleton has been checked).
    const finished = await createPricingVersion(request, version);
    await runToResult(request, finished.id);
    let release: (() => void) | undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/api/v1/pricing-versions/*/result', async (route) => {
      await held;
      await route.continue();
    });
    await page.goto(`/#/lab/${version}/result/${finished.letter}`);
    await page.reload();
    await expect(page.getByRole('status', { name: 'Loading' })).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), 'No run in progress', false);
    release?.();
    await expect(page.getByText('Result · pipeline step 6')).toBeVisible();
    await expect(page.getByRole('status', { name: 'Loading' })).toHaveCount(0);
    await holdsAtEverySize(page, page.getByRole('main'));
    // The five-second test at 1280 × 720 without Aa: the insight title and both simulated bars
    // are in view without scrolling the card.
    await page.setViewportSize({ width: 1280, height: 720 });
    const simulation = page.getByTestId('simulation-group');
    await expect(simulation.getByRole('heading', { level: 2 })).toBeInViewport({ ratio: 1 });
    for (const bar of await simulation.getByRole('img').all()) {
      await expect(bar).toBeInViewport({ ratio: 1 });
    }
  });

  // A third scenario for L-3's hub pairs: the first holds every other built view and already
  // fills its time budget.
  test('Lab · L-3 hub pairs and the hidden map hold at 1440, 1280 and 1280 × 720 with Aa', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    const finished = await createPricingVersion(request, version);
    await runToResult(request, finished.id);
    await page.goto(`/#/lab/${version}/result/${finished.letter}`);
    await page.reload();
    await expect(page.getByText('Result · pipeline step 6')).toBeVisible();

    // L-3 hub pairs: the table open with a row open, then the map hidden.
    await page.getByRole('button', { name: /^Price and flow per hub pair \(/ }).click();
    const pairRows = page.getByRole('row', { expanded: false });
    await expect(pairRows.first()).toBeVisible();
    await pairRows.first().click();
    await expect(page.getByRole('table', { name: 'Offered bike options' })).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));
    await page.getByRole('button', { name: 'Hide map' }).click();
    await holdsAtEverySize(page, page.getByRole('main'), 'No run in progress', false);
    await page.getByRole('button', { name: 'Show map' }).click();

    // L-3 with Advanced view on: the card scrolls, the page does not. Off again for what follows.
    const advanced = page.getByRole('switch', { name: 'Advanced view' });
    await advanced.click();
    await expect(page.getByRole('heading', { level: 2, name: 'Advanced view' })).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'));
    await advanced.click();
    await expect(page.getByRole('heading', { level: 2, name: 'Advanced view' })).toHaveCount(0);
  });

  // A sibling scenario for L-4: the first holds every other built view and already fills its
  // time budget (the states are added to the same family, one scenario per screen).
  test('Lab · every L-4 state holds at 1440, 1280 and 1280 × 720 with Aa', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, 920);
    const main = page.getByRole('main');

    // The off state: one finished version only, the menu item opens it in place.
    await finishVersion(request, version, 'Baseline');
    await page.goto(`/#/lab/${version}`);
    await page.reload();
    await page.getByRole('button', { name: 'Compare versions', exact: true }).click();
    await expect(
      main.getByText('Compare needs two pricing versions of this city instance.'),
    ).toBeVisible();
    await holdsAtEverySize(page, main);

    // Two versions.
    await finishVersion(request, version, 'Heavier ridership', { ridership_weight: 20 });
    await page.goto(`/#/lab/${version}/compare/A,B`);
    await page.reload();
    await expect(main.getByTestId('compare-table')).toBeVisible();
    await expect(main.getByRole('heading', { level: 2 })).toHaveText(/^In the simulation, /);
    await holdsAtEverySize(page, main);

    // Three versions.
    await finishVersion(request, version, 'Higher floor', { lowest_price_chf: 0.9 });
    await page.goto(`/#/lab/${version}/compare/A,B,C`);
    await page.reload();
    await expect(main.getByTestId('compare-table').getByRole('columnheader')).toHaveCount(5);
    await holdsAtEverySize(page, main);

    // Two versions with the same pricing model result: the sentence takes the table's place.
    await finishVersion(request, version, 'Dearer flat price', {
      ridership_weight: 20,
      flat_price_per_ride_chf: 1.5,
    });
    await page.goto(`/#/lab/${version}/compare/B,D`);
    await page.reload();
    await expect(
      main.getByText(
        'Versions B and D have the same pricing model result: no hub pair price differs.',
      ),
    ).toBeVisible();
    await holdsAtEverySize(page, main);

    // Three versions again, with the difference table and the map's panel.
    await page.goto(`/#/lab/${version}/compare/A,B,C`);
    await page.reload();
    await expect(
      main.getByRole('heading', { name: /^Hub pairs where the mean bike price differs most/ }),
    ).toBeVisible();
    await expect(page.getByRole('group', { name: 'Map legend' })).toBeVisible();
    const exportButton = main.getByRole('button', { name: 'Export the table (CSV)' });
    await expect(exportButton).toBeVisible();
    await expect(exportButton).toBeEnabled();
    await holdsAtEverySize(page, main);

    // Advanced view on: the solver's rows join the table; the page still does not scroll.
    const advanced = main.getByRole('switch', { name: 'Advanced view' });
    await advanced.click();
    await expect(main.getByText('= Objective value')).toBeVisible();
    await holdsAtEverySize(page, main);
    await advanced.click();
    await expect(main.getByText('= Objective value')).toHaveCount(0);

    // Four versions with two flat columns: the table scrolls sideways inside the card, the bars
    // wrap, the page does not scroll.
    await page.goto(`/#/lab/${version}/compare/A,B,C,D`);
    await page.reload();
    const table = main.getByTestId('compare-table');
    await expect(table.getByRole('columnheader')).toHaveCount(7);
    await expect(table.getByRole('columnheader').nth(1)).toHaveText(/^Flat price 1\.00 CHF · for /);
    await holdsAtEverySize(page, main);

    await page.setViewportSize({ width: 1280, height: 720 });
    // Every size ends with Aa off: switch it on for the last check.
    await page.getByRole('button', { name: 'Larger text for a projector' }).click();
    const scrolled = await table.evaluate((element) => ({
      scrollable: element.scrollWidth > element.clientWidth,
      page: document.documentElement.scrollWidth <= window.innerWidth,
    }));
    expect(scrolled).toEqual({ scrollable: true, page: true });
    // The row labels stay fixed while the table scrolls sideways.
    const label = table.getByTestId('row-label-simulated-share_car');
    const before = await label.boundingBox();
    await table.evaluate((element) => {
      element.scrollLeft = element.scrollWidth;
    });
    const after = await label.boundingBox();
    expect(after?.x).toBe(before?.x);
    // The bars wrap into rows instead of leaving the card.
    const tops = await main
      .getByRole('list', { name: 'Simulated split of the travellers' })
      .getByRole('img')
      .evaluateAll(
        (bars) => new Set(bars.map((bar) => Math.round(bar.getBoundingClientRect().top))).size,
      );
    expect(tops).toBeGreaterThan(1);
  });

  // A second scenario for the run states of L-2: the first holds every other built view and
  // already fills its time budget.
  // A sibling scenario for L-5: the first holds every other built view and already fills its
  // time budget (the states pick and switched are added to the same family).
  test('Lab · every L-5 state holds at 1440, 1280 and 1280 × 720 with Aa', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, 912);
    const main = page.getByRole('main');
    await finishVersion(request, version, 'Baseline');
    await finishVersion(request, version, 'Incentive', {
      pt_fare_chf: 3,
      lowest_price_chf: 0.8,
    });

    // Pick: the form, no prices yet.
    await page.goto(`/#/lab/traveller/${version}/A`);
    await page.reload();
    await expect(main.getByRole('combobox', { name: 'Pricing version' })).toHaveValue(
      `${version}.A`,
    );
    await expect(main.getByRole('combobox', { name: 'Point A' })).toBeVisible();
    await holdsAtEverySize(page, main);

    // Switched: two points priced by version A, then version B with the previous prices struck
    // through. The points are the first two stops of different hubs the API prices.
    const [from, to] = await pricedPair(request, version, `${version}.A`);
    const fieldA = main.getByRole('combobox', { name: 'Point A' });
    const fieldB = main.getByRole('combobox', { name: 'Point B' });
    await fieldA.fill(from.name);
    await main.getByRole('listbox').getByRole('option').first().click();
    await fieldB.fill(to.name);
    await main.getByRole('listbox').getByRole('option').first().click();
    await expect(main.getByText('Monday 08:00–09:00 · Version A')).toBeVisible();
    await main.getByRole('combobox', { name: 'Pricing version' }).selectOption(`${version}.B`);
    await expect(main.getByText('Monday 08:00–09:00 · Version B')).toBeVisible();
    await expect(main.getByRole('deletion').first()).toBeVisible();
    await holdsAtEverySize(page, main);

    // Options: the three cards and the notes under them (the fake city offers one bike option
    // per pair, so the list of other bike options cannot be opened here).
    await expect(main.getByText(/^Durations and legs are those of the hub pair/)).toBeVisible();
    await holdsAtEverySize(page, main);

    // No price: two stops of one hub.
    const [sameA, sameB] = await sameHubPair(request, version);
    await fieldA.fill(sameA.name);
    await main.getByRole('listbox').getByRole('option').first().click();
    await fieldB.fill(sameB.name);
    await main.getByRole('listbox').getByRole('option').first().click();
    await expect(main.getByRole('status')).toContainText('both points are in hub');
    await holdsAtEverySize(page, main);
  });

  test('Lab · every L-2 run state holds at 1440, 1280 and 1280 × 720 with Aa', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    await createPricingVersion(request, version);
    await createPricingVersion(request, version);

    // L-2 running, queued, the cancel confirmation, cancelled and failed: Version A held at its
    // pricing model step, Version B queued behind it.
    await control.setPricingModel({ hold_at: 'pricing_model' });
    const [versionA, versionB] = [`${version}.A`, `${version}.B`];
    const runA = (await (await runPricingVersion(request, versionA)).json()) as { id: string };
    expect((await runPricingVersion(request, versionB)).status()).toBe(202);
    const runningLine = /^● Version A running · /;
    await page.goto(`/#/lab/${version}/pricing/A`);
    await page.reload();
    await expect(page.getByText(/5 Pricing model — running for/)).toBeVisible({ timeout: 30_000 });
    await holdsAtEverySize(page, page.getByRole('main'), runningLine, false);

    await page.getByRole('button', { name: 'Cancel run' }).click();
    await expect(page.getByRole('button', { name: 'Cancel the run' })).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), runningLine, false);
    await page.getByRole('button', { name: 'Keep running' }).click();

    await page.goto(`/#/lab/${version}/pricing/B`);
    await page.reload();
    await expect(page.getByText(/^Queued, 2nd in line: Version A is running\./)).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), runningLine, false);
    await page.getByRole('button', { name: 'Remove from the queue' }).click();
    await expect(page.getByRole('button', { name: 'Keep', exact: true })).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), runningLine, false);
    await page.getByRole('button', { name: 'Remove from the queue' }).click();
    await expect(
      page.getByText(/^Run cancelled during Pricing model on \d{1,2} [A-Z][a-z]{2} \d{4}\./),
    ).toBeVisible();
    await holdsAtEverySize(page, page.getByRole('main'), runningLine, false);

    // Version A's held step fails once it is released.
    await control.setPricingModel({
      fail_at: { step: 'pricing_model', code: 'solver_no_solution' },
    });
    await control.releaseRun(runA.id);
    await page.goto(`/#/lab/${version}/pricing/A`);
    await expect(page.getByText(/^Pricing model failed: /)).toBeVisible({ timeout: 30_000 });
    await holdsAtEverySize(page, page.getByRole('main'), 'No run in progress', false);
  });

  // A sibling scenario for L-3 with the older rule: the first scenario's time budget is spent.
  test('Lab · L-3 older rule, simulating and delete hold at 1440, 1280 and 1280 × 720 with Aa', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    const draft = await createPricingVersion(request, version);
    await runToResult(request, draft.id);
    await waitForSimulationRule(request, 1);
    await control.setPricingModel({
      simulation_rule: { version: 2, price_weight: 0.6, time_weight: 0.4 },
      hold_at: 'traveller_simulation',
    });
    await waitForSimulationRule(request, 2);
    await page.goto(`/#/lab/${version}/result/A`);
    await page.reload();
    const main = page.getByRole('main');
    const box = page.getByTestId('older-rule');
    await expect(box).toBeVisible();

    // The older rule: the box above the simulation group and its action.
    await holdsAtEverySize(page, main);

    // The delete confirmation.
    await main.getByRole('button', { name: 'Delete…' }).click();
    await expect(main.getByRole('button', { name: 'Delete Version A' })).toBeVisible();
    await holdsAtEverySize(page, main);
    await main.getByRole('button', { name: 'Keep' }).click();

    // The off state: the runner is reported as not running.
    await page.route('**/api/v1/system-status', async (route) => {
      const answer = (await (await route.fetch()).json()) as Record<string, unknown>;
      await route.fulfill({
        json: {
          ...answer,
          can_simulate: {
            allowed: false,
            reasons: [{ component: 'runner', reason: 'No worker has reported.' }],
          },
        },
      });
    });
    await page.reload();
    await expect(
      box.getByText(/^Simulation is off: the runner is not running\./).first(),
    ).toBeVisible();
    await expect(box.getByRole('button', { name: 'Simulate again with v2' })).toBeDisabled();
    await holdsAtEverySize(page, main);
    await page.unroute('**/api/v1/system-status');
    await page.reload();

    // Simulating: the held simulation run.
    await box.getByRole('button', { name: 'Simulate again with v2' }).click();
    await expect(box.getByText(/Traveller simulation · running for \d+ s/)).toBeVisible({
      timeout: 30_000,
    });
    await holdsAtEverySize(page, main, /^● Version A running · /);

    // The held run ends before the scenario does: a reset right after a release would wipe the
    // release before the worker saw it.
    const [simulationRun] = await control.activeRunIds();
    await control.releaseRun(simulationRun ?? '');
    await waitForRun(request, simulationRun ?? '', 'succeeded');
  });

  test('Lab · L-1 saved holds at 1440, 1280 and 1280 × 720 with Aa', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    await page.goto(`/#/lab/${version}`);
    await expect(page.getByText('City instance · pipeline steps 1 to 4')).toBeVisible();

    // The card is the scrolling region: it sits inside the viewport at every size.
    await holdsAtEverySize(page, page.getByRole('main'));
  });

  test('Lab · under reduced motion the shell has no transition or animation time', async ({
    browser,
    baseURL,
    request,
    control,
  }) => {
    const context = await browser.newContext({ reducedMotion: 'reduce', baseURL });
    const page = await context.newPage();
    await page.goto('/');
    await expect(page.getByText('Dynamic pricing · Lab')).toBeVisible();

    const noTime = async () => {
      const durations = await page.evaluate(() =>
        Array.from(document.querySelectorAll('body *')).flatMap((element) => {
          const style = getComputedStyle(element);
          return [style.transitionDuration, style.animationDuration];
        }),
      );
      expect(durations.length).toBeGreaterThan(0);
      for (const duration of durations) {
        expect(duration.split(',').every((part) => part.trim() === '0s')).toBe(true);
      }
    };
    await noTime();

    // The details panel of L-2 opens without a transition.
    const { version } = await buildFakeInstance(request, control);
    await createPricingVersion(request, version);
    await page.goto(`/#/lab/${version}/pricing/A`);
    await page.reload();
    await page.getByRole('button', { name: 'ⓘ Explain step 3' }).click();
    await expect(
      page.getByRole('complementary', { name: 'How the model reads these values' }),
    ).toBeVisible();
    await noTime();

    // L-2 running: the spinner stops, the elapsed clock stays.
    await control.setPricingModel({ hold_at: 'pricing_model' });
    expect((await runPricingVersion(request, `${version}.A`)).status()).toBe(202);
    await page.goto(`/#/lab/${version}/pricing/A`);
    await page.reload();
    const step5 = page.getByText(/5 Pricing model — running for \d+ s/);
    await expect(step5).toBeVisible({ timeout: 30_000 });
    await noTime();
    const clock = async () => /running for (\d+) s/.exec((await step5.textContent()) ?? '')?.[1];
    const before = await clock();
    await expect.poll(clock, { message: 'the elapsed clock still ticks' }).not.toBe(before);

    // L-3: the held run is released and its result opens without a transition or animation.
    const running = (await control.activeRunIds())[0] ?? '';
    expect(running).not.toBe('');
    await control.releaseRun(running);
    await waitForRun(request, running, 'succeeded');
    await page.goto(`/#/lab/${version}/result/A`);
    await page.reload();
    await expect(page.getByText('Result · pipeline step 6')).toBeVisible();
    await noTime();
    // L-3 hub pairs: the table, a row and the map open without a transition.
    await page.getByRole('button', { name: /^Price and flow per hub pair \(/ }).click();
    await page.getByRole('row', { expanded: false }).first().click();
    await expect(page.getByRole('table', { name: 'Offered bike options' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Map' })).toBeVisible();
    await noTime();
    // L-3 with Advanced view on: the section appears without a transition or animation.
    await page.getByRole('switch', { name: 'Advanced view' }).click();
    await expect(page.getByRole('heading', { level: 2, name: 'Advanced view' })).toBeVisible();
    await noTime();
    // L-3 simulating again: the mark stops pulsing, the elapsed clock still ticks.
    await waitForSimulationRule(request, 1);
    await control.setPricingModel({
      simulation_rule: { version: 2, price_weight: 0.6, time_weight: 0.4 },
      hold_at: 'traveller_simulation',
    });
    await waitForSimulationRule(request, 2);
    await page.reload();
    await page.getByRole('button', { name: 'Simulate again with v2' }).click();
    const simulating = page.getByText(/Traveller simulation · running for \d+ s/);
    await expect(simulating).toBeVisible({ timeout: 30_000 });
    await noTime();
    const seconds = async () =>
      /running for (\d+) s/.exec((await simulating.textContent()) ?? '')?.[1];
    const first = await seconds();
    await expect.poll(seconds, { message: 'the simulation clock still ticks' }).not.toBe(first);
    // Released here: a reset right after the teardown's release would wipe it unseen.
    const [simulationRun] = await control.activeRunIds();
    await control.releaseRun(simulationRun ?? '');
    await waitForRun(request, simulationRun ?? '', 'succeeded');
    // L-5: the form and its prices have no transition or animation either.
    await page.goto(`/#/lab/traveller/${version}/A`);
    await page.reload();
    await expect(page.getByRole('combobox', { name: 'Point A' })).toBeVisible();
    await noTime();
    await context.close();
  });
});
