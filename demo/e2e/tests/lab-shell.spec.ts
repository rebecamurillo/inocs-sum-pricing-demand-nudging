import { expect, test } from '../support/fixtures';

const emptyLabSentence =
  'No city instance yet. Create one from the Geneva data: it prepares the area, the hubs, the routes and the travellers of one period.';

function present<T>(value: T | null): T {
  if (value === null) throw new Error('The element has no box.');
  return value;
}

test.describe('Lab', () => {
  test('Lab · the shell opens on #/lab with its menu, footer and no Home link', async ({
    page,
    baseURL,
  }) => {
    const requested: string[] = [];
    page.on('request', (request) => requested.push(request.url()));

    await page.goto('/');

    await expect(page).toHaveURL(/#\/lab$/);
    await expect(page.getByText('Dynamic pricing · Lab')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Hide the menu' })).toBeVisible();
    await expect(page.getByText('Operator view')).toBeVisible();
    await expect(page.getByRole('button', { name: 'City instances' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(page.getByText('No instance yet')).toBeVisible();
    await expect(page.getByText('Traveller view')).toBeVisible();
    await expect(page.getByText('No run in progress')).toBeVisible();
    await expect(page.getByText(emptyLabSentence)).toBeVisible();
    await expect(page.getByRole('region', { name: 'Map' })).toBeVisible();
    await expect(
      page.getByText('Funded by the European Union under Horizon Europe, project SUM.'),
    ).toBeVisible();
    await expect(page.getByRole('contentinfo')).toContainText(
      'Pricing model: placeholder, Inria INOCS.',
    );
    for (const absent of ['← Home', 'Next version', 'Simulation', 'Run unmodified']) {
      await expect(page.getByText(absent)).toHaveCount(0);
    }
    await expect(page.getByRole('link')).toHaveCount(0);
    // The menu's "+ New" and the card's primary, which a Lab without city data disables.
    await expect(page.getByRole('button', { name: '+ New', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '+ New city instance' })).toBeDisabled();
    await expect(
      page.getByText(
        "No city data is imported yet. A city instance needs a timetable and bike stations; the maintainer imports Geneva's with one command (demo/README.md).",
      ),
    ).toBeVisible();

    // Every request goes to the stack's own host.
    const origin = new URL(baseURL ?? '').origin;
    expect(requested.length).toBeGreaterThan(0);
    for (const url of requested) expect(new URL(url).origin).toBe(origin);
  });

  test('Lab · a hash that is not a Lab route is replaced by #/lab', async ({ page }) => {
    await page.goto('/#/play');

    await expect(page).toHaveURL(/#\/lab$/);
    await expect(page.getByText(emptyLabSentence)).toBeVisible();
  });

  test('Lab · a link naming an instance version reads "Nothing at this link"', async ({ page }) => {
    await page.goto('/#/lab/geneva-3km.v1');

    await expect(
      page.getByText('Nothing at this link: geneva-3km has no v1. It may have been deleted.'),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Compare versions' }).click();
    await expect(
      page.getByText('Compare needs two pricing versions of this city instance.'),
    ).toBeVisible();
  });

  test('Lab · menu, map, share, Advanced view and Aa survive a reload', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Hide the menu' }).click();
    await page.getByRole('button', { name: 'Hide map' }).click();
    await page.getByRole('button', { name: 'Larger text for a projector' }).click();

    await page.reload();

    await expect(page.getByRole('button', { name: '☰ Menu' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Show map' })).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.style.fontSize))
      .toBe('130%');

    await page.getByRole('button', { name: 'Show map' }).click();
    await page.getByRole('button', { name: '☰ Menu' }).click();
    await page.getByRole('separator').focus();
    await page.keyboard.press('ArrowLeft');
    await page.getByRole('switch', { name: 'Advanced view' }).click();

    await page.reload();

    await expect(page.getByRole('separator')).toHaveAttribute('aria-valuenow', '52');
    await expect(page.getByRole('switch', { name: 'Advanced view' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  test('Lab · dragging the grip changes the map share, clamped at 80 %', async ({ page }) => {
    await page.goto('/');
    const grip = page.getByRole('separator');
    await expect(grip).toHaveAttribute('aria-valuenow', '50');

    const box = present(await grip.boundingBox());
    const y = box.y + box.height / 2;
    await page.mouse.move(box.x + box.width / 2, y);
    await page.mouse.down();
    await page.mouse.move(box.x - 100, y, { steps: 5 });
    const widened = Number(await grip.getAttribute('aria-valuenow'));
    expect(widened).toBeGreaterThan(50);
    await page.mouse.move(0, y, { steps: 5 });
    await page.mouse.up();

    await expect(grip).toHaveAttribute('aria-valuenow', '80');
  });
});
