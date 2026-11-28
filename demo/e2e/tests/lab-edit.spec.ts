import type { Page } from '@playwright/test';
import { awaitPackageDefaults, builtCounts, buildFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';

const grouped = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

const COUNT_LABELS = [
  ['stops', 'Stops and platforms'],
  ['bike_stations', 'Bike stations'],
  ['hubs', 'Hubs'],
  ['hub_pairs_with_routes', 'Hub pairs with routes'],
  ['travellers', 'Travellers in the period'],
] as const;

/** The five counts of the saved card, as the API gave them. */
async function expectCounts(page: Page, counts: Record<string, number>) {
  for (const [key, label] of COUNT_LABELS) {
    const count = counts[key];
    expect(count).toBeDefined();
    await expect(
      page.getByRole('term').filter({ hasText: new RegExp(`^${label}$`) }),
    ).toBeVisible();
    await expect(
      page
        .getByRole('definition')
        .filter({ hasText: new RegExp(`^${grouped(count ?? 0)}$`) })
        .first(),
    ).toBeVisible();
  }
}

const input = (page: Page, name: string) => page.getByRole('textbox', { name, exact: true });

test.describe('Lab', () => {
  test('L-1 · creating an instance from the defaults builds it and shows the four steps with their counts', async ({
    page,
    request,
    control,
  }) => {
    const datasetId = await control.insertCityDataset();
    await awaitPackageDefaults(request, datasetId);
    await page.goto('/#/lab');

    await page.getByRole('button', { name: '+ New city instance' }).click();
    await expect(page.getByRole('heading', { name: 'New city instance' })).toBeVisible();
    await expect(page.getByRole('rowgroup')).toHaveCount(0);
    await input(page, 'Name').fill('Geneva 3 km');
    await input(page, 'Name').press('Enter');

    // The draft: the heading, Name read-only, the groups, and the package's tie as a broken rule.
    await expect(
      page.getByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeVisible();
    await expect(page).toHaveURL(/#\/lab\/geneva-3km\.v1$/);
    await expect(input(page, 'Name')).toHaveAttribute('readonly', '');
    await expect(
      page.getByText(
        'Minimum trip distance is greater than the grouping distance: now 500 m against 500 m',
      ),
    ).toBeVisible();
    await expect(page.getByText('One rule is not met.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save as v1 and build' })).toBeDisabled();

    // Moving the minimum trip distance above the grouping distance clears the rule.
    await input(page, 'Minimum trip distance').fill('930');
    await expect(page.getByText(/^Draft saved · \d{2}:\d{2}$/)).toBeVisible();
    await expect(page.getByText('One rule is not met.')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Save as v1 and build' })).toBeEnabled();
    // The fake holds the build before its last step: the steps show with what they counted.
    await control.setPricingModel({ hold_at: 'travellers_and_bikes' });
    await page.getByRole('button', { name: 'Save as v1 and build' }).click();

    const kept = '(kept: already computed with the same inputs · )?';
    await expect(page.getByRole('list', { name: 'Build steps' })).toBeVisible({
      timeout: 30_000,
    });
    await expect(
      page.getByText(new RegExp(`^✓ ${kept}30 stops and platforms · 12 bike stations$`)),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(new RegExp(`^✓ ${kept}6 hubs$`))).toBeVisible();
    await expect(page.getByText(new RegExp(`^✓ ${kept}24 hub pairs with routes$`))).toBeVisible();
    await expect(
      page.getByRole('listitem').filter({ hasText: '4 Travellers and bikes' }),
    ).toContainText(/\d+ s$/);
    const [heldRun] = await control.activeRunIds();
    await control.releaseRun(heldRun ?? '');

    // The build runs in the worker; the saved card reads its five counts.
    const counts = await builtCounts(request, 'geneva-3km.v1');
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Geneva 3 km' })).toBeVisible();
    await expect(page.getByText(/^Ready · saved/)).toBeVisible();
    await expectCounts(page, counts);
    await expect(page.getByLabel('Breadcrumb')).toHaveText('Geneva 3 km v1 › Instance set-up');
  });

  test('L-1 · a broken rule names both values and blocks saving', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    await page.goto(`/#/lab/${version}`);
    await page.getByRole('button', { name: 'Edit as a new version' }).click();

    await expect(
      page.getByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeVisible();
    await expect(page).toHaveURL(/#\/lab\/geneva-3km\.v2$/);
    await expect(input(page, 'Name')).toHaveCount(0);
    await expect(page.getByText('Nothing differs from v1 yet.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save and build' })).toBeDisabled();

    // A grouping distance above the minimum trip distance (900 m).
    await input(page, 'Grouping distance').fill('1000');

    await expect(
      page.getByText(
        'Minimum trip distance is greater than the grouping distance: now 900 m against 1000 m',
      ),
    ).toBeVisible();
    await expect(input(page, 'Grouping distance')).toHaveAttribute('aria-invalid', 'true');
    await expect(input(page, 'Minimum trip distance')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByText('One rule is not met.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save and build' })).toBeDisabled();
    // The previous value stays beside the changed one.
    await expect(page.getByText('500 m', { exact: true }).first()).toBeVisible();

    await input(page, 'Grouping distance').fill('420');

    await expect(page.getByText('One rule is not met.')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Save and build' })).toBeEnabled();
  });

  test('L-1 · saving an edit creates v2; v1 and its versions stay; step 1 shows as kept', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    const v1Counts = await builtCounts(request, version);
    await page.goto(`/#/lab/${version}`);
    await page.getByRole('button', { name: 'Edit as a new version' }).click();
    await expect(
      page.getByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeVisible();

    await input(page, 'Grouping distance').fill('410');

    await expect(page.getByText(/^Draft saved · \d{2}:\d{2}$/)).toBeVisible();
    await expect(
      page.getByText(
        /^Saving creates Geneva 3 km v2\. v1 and its 0 pricing versions stay as they are\. Will rebuild: 2 Hubs, 3 Routes, 4 Travellers and bikes; step 1 is kept\./,
      ),
    ).toBeVisible();
    const changes = page.getByRole('table');
    await expect(changes.getByRole('columnheader', { name: 'What v2 changes' })).toBeVisible();
    await expect(changes.getByRole('cell', { name: 'Grouping distance' })).toBeVisible();
    // The fake holds the build at step 2, which a changed grouping distance rebuilds.
    await control.setPricingModel({ hold_at: 'hubs' });
    await page.getByRole('button', { name: 'Save and build' }).click();

    await expect(page).toHaveURL(/#\/lab\/geneva-3km\.v2$/);
    await expect(
      page.getByText('✓ kept from v1 · 30 stops and platforms · 12 bike stations'),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('columnheader', { name: 'What v2 changes' })).toBeVisible();
    const [heldBuild] = await control.activeRunIds();
    await control.releaseRun(heldBuild ?? '');
    await builtCounts(request, 'geneva-3km.v2');
    await page.reload();
    // Both versions are in the menu; v2 is the open one.
    await expect(
      page.getByRole('button', { name: /^Geneva 3 km v1 /, exact: false }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /^Geneva 3 km v2 /, exact: false }),
    ).toBeVisible();
    await expect(page.getByLabel('Breadcrumb')).toHaveText('Geneva 3 km v2 › Instance set-up');

    // v1 is as it was: its values and its counts.
    await page.goto(`/#/lab/${version}`);
    await expect(page.getByLabel('Breadcrumb')).toHaveText('Geneva 3 km v1 › Instance set-up');
    await expect(
      page
        .getByRole('definition')
        .filter({ hasText: /^500 m$/ })
        .first(),
    ).toBeVisible();
    await expectCounts(page, v1Counts);
  });
});
