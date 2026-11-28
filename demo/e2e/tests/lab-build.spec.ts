import { queueFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';

// Not the 900 m of the other scenarios: artefacts outlive a reset and are keyed by parameters, so
// a scenario that follows a build takes a distance of its own and the steps really run.
const PACED_DISTANCE_M = 960;
const FAILING_DISTANCE_M = 970;
const HELD_DISTANCE_M = 980;
const BUILD_TIMEOUT_MS = 60_000;

const KEPT = '(kept: already computed with the same inputs · )?';

test.describe('Lab', () => {
  test('L-1 · routes show hub pairs done out of the total while the build runs', async ({
    page,
    request,
    control,
  }) => {
    await control.setPricingModel({ routes_pace_ms: 500 });
    const { version } = await queueFakeInstance(request, control, {
      minOdDistanceM: PACED_DISTANCE_M,
    });

    await page.goto(`/#/lab/${version}`);

    const progress = page.getByText(
      /^3 Routes — \d+ of 24 hub pairs · \d+ quer(y|ies) gave no route so far$/,
    );
    await expect(progress).toBeVisible({ timeout: BUILD_TIMEOUT_MS });
    const done = async () =>
      Number(/— (\d+) of 24/.exec((await progress.textContent()) ?? '')?.[1] ?? -1);
    const first = await done();
    await expect.poll(done, { timeout: 30_000, message: 'pairs done grow' }).toBeGreaterThan(first);
    const bar = page.getByRole('progressbar', { name: 'Hub pairs routed' });
    await expect(bar).toHaveAttribute('aria-valuemax', '24');
    await expect(page.getByText('waiting')).toBeVisible();

    await expect(page.getByText(/^Ready · saved/)).toBeVisible({ timeout: BUILD_TIMEOUT_MS });
  });

  test("L-1 · the trip planner stops before a build: Routes fails with its reason, steps 1–2 kept; 'Run again from Routes' finishes", async ({
    page,
    request,
    control,
  }) => {
    await control.setPricingModel({
      fail_at: { step: 'routes', code: 'trip_planner_unreachable' },
    });
    const { version } = await queueFakeInstance(request, control, {
      minOdDistanceM: FAILING_DISTANCE_M,
    });

    await page.goto(`/#/lab/${version}`);

    await expect(
      page.getByText('✕ Routes failed: the trip planner did not answer. Steps before it are kept.'),
    ).toBeVisible({ timeout: BUILD_TIMEOUT_MS });
    await expect(
      page.getByText(new RegExp(`^✓ ${KEPT}30 stops and platforms · 12 bike stations$`)),
    ).toBeVisible();
    await expect(page.getByText(new RegExp(`^✓ ${KEPT}6 hubs$`))).toBeVisible();
    await expect(page.getByRole('button', { name: 'Geneva 3 km v1 ✕ failed' })).toBeVisible();

    // The trip planner is back; the second run stops before its last step to show the first two kept.
    await control.setPricingModel({ hold_at: 'travellers_and_bikes' });
    await page.getByRole('button', { name: 'Run again from Routes' }).click();

    await expect(
      page.getByText(
        /^✓ kept: already computed with the same inputs · 30 stops and platforms · 12 bike stations$/,
      ),
    ).toBeVisible({ timeout: BUILD_TIMEOUT_MS });
    await expect(
      page.getByText(/^✓ kept: already computed with the same inputs · 6 hubs$/),
    ).toBeVisible();
    await expect(page.getByText(new RegExp(`^✓ ${KEPT}24 hub pairs with routes$`))).toBeVisible();
    const [runId] = await control.activeRunIds();
    await control.releaseRun(runId ?? '');

    await expect(page.getByText(/^Ready · saved/)).toBeVisible({ timeout: BUILD_TIMEOUT_MS });
  });

  test('Lab · a reload during a run reopens the same view with the run still running', async ({
    page,
    request,
    control,
  }) => {
    await control.setPricingModel({ hold_at: 'routes' });
    const { version, runId } = await queueFakeInstance(request, control, {
      minOdDistanceM: HELD_DISTANCE_M,
    });
    await page.goto(`/#/lab/${version}`);
    const building = page.getByText(
      /^Building for \d+ s\. It continues if you open another page\.$/,
    );
    const runLine = page.getByText(/^● Geneva 3 km v1 building · /);
    await expect(building).toBeVisible({ timeout: BUILD_TIMEOUT_MS });
    await expect(runLine).toBeVisible();

    await page.reload();

    await expect(building).toBeVisible({ timeout: BUILD_TIMEOUT_MS });
    await expect(runLine).toBeVisible();
    await expect(page.getByRole('button', { name: 'Geneva 3 km v1 ● building' })).toBeVisible();
    await expect(page.getByText('Available when the instance is built.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel run' })).toBeVisible();

    await control.releaseRun(runId);

    await expect(page.getByText(/^Ready · saved/)).toBeVisible({ timeout: BUILD_TIMEOUT_MS });
    await expect(page.getByText('No run in progress')).toBeVisible();
  });
});
