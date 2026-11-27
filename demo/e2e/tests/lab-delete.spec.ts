import { expect, test } from '../support/fixtures';
import { buildFakeInstance, queueFakeInstance } from '../support/build';
import { createPricingVersion } from '../support/pricing';

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
});
