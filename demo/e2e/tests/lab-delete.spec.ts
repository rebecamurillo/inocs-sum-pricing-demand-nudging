import { expect, test } from '../support/fixtures';
import { queueFakeInstance } from '../support/build';

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
});
