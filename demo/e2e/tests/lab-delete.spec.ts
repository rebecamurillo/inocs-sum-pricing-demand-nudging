import { expect, test } from '../support/fixtures';
import { buildFakeInstance, queueFakeInstance } from '../support/build';
import { createPricingVersion, putShowcase, runToResult } from '../support/pricing';

const BUILD_TIMEOUT_MS = 60_000;
// Its own distance: the artefacts of a build outlive a reset, so no other scenario's build may
// find this one's routes already computed (the build would then not stop at the held step).
const DELETE_DISTANCE_M = 990;

test.describe('Lab · deleting a version', () => {
  test('L-1 · deleting a version is refused while its build runs, and removes it once the build ended', async ({
    page,
    request,
    control,
  }) => {
    await control.setPricingModel({ hold_at: 'routes' });
    const { version, runId } = await queueFakeInstance(request, control, {
      minOdDistanceM: DELETE_DISTANCE_M,
    });
    await page.goto(`/#/lab/${version}`);
    await page.reload();
    await expect(page.getByRole('list', { name: 'Build steps' })).toBeVisible({
      timeout: BUILD_TIMEOUT_MS,
    });
    const main = page.getByRole('main');
    const menu = page.getByRole('complementary', { name: 'Menu' });

    await main.getByRole('button', { name: 'Delete…' }).click();
    await expect(
      main.getByText(
        'Delete Geneva 3 km v1? This removes the instance version. Other versions of Geneva 3 km stay. This cannot be undone.',
      ),
    ).toBeVisible();
    await main.getByRole('button', { name: 'Delete v1' }).click();

    await expect(main.getByText('A run of this version is queued or running.')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`#/lab/${version}$`));
    await expect(menu.getByRole('button', { name: /^Geneva 3 km v1 / })).toBeVisible();
    expect((await request.get(`/api/v1/instance-versions/${version}`)).status()).toBe(200);

    await control.releaseRun(runId);
    await expect(page.getByText(/^Ready · saved/)).toBeVisible({ timeout: BUILD_TIMEOUT_MS });

    await main.getByRole('button', { name: 'Delete…' }).click();
    await main.getByRole('button', { name: 'Delete v1' }).click();

    await expect(page).toHaveURL(/#\/lab$/);
    await expect(menu.getByRole('button', { name: /^Geneva 3 km v1/ })).toHaveCount(0);
    expect((await request.get(`/api/v1/instance-versions/${version}`)).status()).toBe(404);
  });

  test('L-1 · deleting a version used by pricing versions is refused until they are included', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, DELETE_DISTANCE_M + 1);
    await createPricingVersion(request, version);
    await createPricingVersion(request, version, { name: 'Cheaper' });
    const path = `/api/v1/instance-versions/${version}`;

    const refused = await request.delete(path);
    expect(refused.status()).toBe(409);
    expect(await refused.json()).toMatchObject({
      code: 'has_pricing_versions',
      pricing_version_ids: [`${version}.A`, `${version}.B`],
    });

    await page.goto(`/#/lab/${version}`);
    await page.reload();
    const main = page.getByRole('main');
    const menu = page.getByRole('complementary', { name: 'Menu' });
    await main.getByRole('button', { name: 'Delete…' }).click();
    await expect(
      main.getByText(
        'Delete Geneva 3 km v1? This removes the instance version and its 2 pricing versions with their results (A, B). Other versions of Geneva 3 km stay. This cannot be undone.',
      ),
    ).toBeVisible();
    await main.getByRole('button', { name: 'Delete v1 and its 2 pricing versions' }).click();

    await expect(page).toHaveURL(/#\/lab$/);
    await expect(menu.getByRole('button', { name: /^Geneva 3 km v1/ })).toHaveCount(0);
    expect((await request.get(path)).status()).toBe(404);
    expect((await request.get(`/api/v1/pricing-versions/${version}.A`)).status()).toBe(404);
  });

  test("L-3 · deleting a version with a result opens L-1 and removes its row; the home page's result is refused with its reason", async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, DELETE_DISTANCE_M + 2);
    const first = await createPricingVersion(request, version);
    const second = await createPricingVersion(request, version, { name: 'Cheaper' });
    const firstResult = await runToResult(request, first.id);
    await runToResult(request, second.id);
    await putShowcase(request, second.id, firstResult.period_id);
    await page.goto(`/#/lab/${version}/result/B`);
    await page.reload();
    const main = page.getByRole('main');
    const menu = page.getByRole('complementary', { name: 'Menu' });

    // The showcase version stays, with the reason as the note.
    await main.getByRole('button', { name: 'Delete…' }).click();
    await main.getByRole('button', { name: 'Delete Version B' }).click();
    await expect(
      main.getByText("Version B is the home page's result: choose another one first."),
    ).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`#/lab/${version}/result/B$`));
    expect((await request.get(`/api/v1/pricing-versions/${second.id}`)).status()).toBe(200);

    // The other one goes: L-1 opens and its row leaves the menu.
    await page.goto(`/#/lab/${version}/result/A`);
    await main.getByRole('button', { name: 'Delete…' }).click();
    await expect(
      main.getByText(
        'Delete Version A · Version A? This removes its goals and its result. Other versions of Geneva 3 km v1 stay. This cannot be undone.',
      ),
    ).toBeVisible();
    await main.getByRole('button', { name: 'Delete Version A' }).click();

    await expect(page).toHaveURL(new RegExp(`#/lab/${version}$`));
    await expect(menu.getByRole('button', { name: /^Version A ✓ result$/ })).toHaveCount(0);
    await expect(menu.getByRole('button', { name: /^Cheaper B ✓ result$/ })).toBeVisible();
    expect((await request.get(`/api/v1/pricing-versions/${first.id}`)).status()).toBe(404);
  });
});
