import type { Page } from '@playwright/test';
import { buildFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';
import { createPricingVersion, putShowcase, readShowcase, runToResult } from '../support/pricing';

// The states of Home and of L-3's "Use on the home page" that home.spec.ts does not reach:
// the showcase loading or not answering, links outside `#/lab`, the hover text naming the
// version in place, a failed `PUT /showcase` and choosing another version.
const API_ERROR = "The result could not be loaded: the demonstrator's API did not answer.";
const NOT_SET = "Not set: the demonstrator's API did not answer.";

async function expectSquareGroundVisual(page: Page) {
  const visual = page.getByTestId('home-visual');
  const box = await visual.boundingBox();
  expect(Math.abs((box?.width ?? 0) - (box?.height ?? 1))).toBeLessThanOrEqual(1);
  expect(await visual.evaluate((element) => getComputedStyle(element).backgroundColor)).toBe(
    'rgb(228, 229, 226)',
  );
}

test.describe('Home states', () => {
  test('Home · while the showcase loads the tile is a skeleton; when the API does not answer or errs, the visual keeps its size and says so', async ({
    page,
  }) => {
    // Loading: the answer is held until the skeleton has been seen.
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/api/v1/showcase', async (route) => {
      await held;
      await route.continue();
    });
    await page.goto('/#/');
    await expect(page.getByTestId('home-skeleton')).toBeVisible();
    await expectSquareGroundVisual(page);
    release();
    await expect(page.getByTestId('home-skeleton')).toHaveCount(0);
    await page.unrouteAll({ behavior: 'wait' });

    // No answer.
    await page.route('**/api/v1/showcase', (route) => route.abort('connectionrefused'));
    await page.reload();
    await expect(page.getByTestId('home-visual')).toHaveText(API_ERROR);
    await expect(page.getByTestId('home-visual')).not.toContainText('SIMULATION');
    await expectSquareGroundVisual(page);
    await page.unrouteAll({ behavior: 'wait' });

    // An error other than 404.
    await page.route('**/api/v1/showcase', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/problem+json',
        body: JSON.stringify({ type: 'about:blank', title: 'Unexpected error', status: 500 }),
      }),
    );
    await page.reload();
    await expect(page.getByTestId('home-visual')).toHaveText(API_ERROR);
    await expectSquareGroundVisual(page);
    // The rest of Home does not depend on the showcase.
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Open the Lab →' })).toBeVisible();
  });

  test('Home · links outside #/lab render Home and stay in the address bar; #/lab and #/lab/… stay the Lab', async ({
    page,
  }) => {
    for (const hash of ['#/elsewhere', '#/play/later', '#nothing', '#/laboratory']) {
      await page.goto(`/${hash}`);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(
        'Price shared bikes by the trip, and fewer people take the car.',
      );
      await expect(page.getByRole('button', { name: 'Open the Lab →' })).toBeVisible();
      expect(new URL(page.url()).hash).toBe(hash);
    }

    for (const hash of ['#/lab', '#/lab/no-such-instance.v1']) {
      await page.goto(`/${hash}`);
      await expect(page.getByText('Dynamic pricing · Lab')).toBeVisible();
      await expect(page.getByRole('link', { name: '← Home' })).toHaveAttribute('href', '#/');
      await expect(page.getByRole('button', { name: 'Open the Lab →' })).toHaveCount(0);
      expect(new URL(page.url()).hash).toBe(hash);
    }
  });

  test('Lab · "Use on the home page" names the version it replaces, keeps its place with a note when the call fails, and moves "On the home page" when another is chosen', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    const first = await createPricingVersion(request, version, { name: 'First' });
    const second = await createPricingVersion(request, version, { name: 'Second' });
    const firstResult = await runToResult(request, first.id);
    await runToResult(request, second.id);
    await putShowcase(request, first.id, firstResult.period_id);
    const main = page.getByRole('main');
    const action = main.getByRole('button', { name: 'Use on the home page' });
    const onHome = main.getByRole('link', { name: 'On the home page' });

    // The showcased version: no action, the link to Home.
    await page.goto(`/#/lab/${version}/result/${first.letter}`);
    await page.reload();
    await expect(onHome).toBeVisible();
    await expect(onHome).toHaveAttribute('href', '#/');
    await expect(action).toHaveCount(0);

    // The other one: the hover text names the version it would replace.
    await page.goto(`/#/lab/${version}/result/${second.letter}`);
    await expect(action).toHaveAttribute(
      'title',
      `Shows this version's result on the home page, in place of Version ${first.letter}'s.`,
    );
    await expect(onHome).toHaveCount(0);
    // Between "Duplicate" and "Delete…".
    const order = await main
      .getByRole('button')
      .evaluateAll((buttons) => buttons.map((button) => button.textContent.trim()));
    const at = (name: string) => order.indexOf(name);
    expect(at('Use on the home page')).toBeGreaterThan(at('Duplicate'));
    expect(at('Use on the home page')).toBeLessThan(at('Delete…'));

    // A failed call: the action stays, with the note; nothing is set.
    await page.route('**/api/v1/showcase', (route) =>
      route.request().method() === 'PUT' ? route.abort('connectionrefused') : route.continue(),
    );
    await action.click();
    await expect(main.getByText(NOT_SET)).toBeVisible();
    await expect(action).toBeVisible();
    await expect(onHome).toHaveCount(0);
    expect((await readShowcase(request)).letter).toBe(first.letter);
    await page.unrouteAll({ behavior: 'wait' });

    // One click, no confirmation: the action goes and the link shows on this version.
    await action.click();
    await expect(onHome).toBeVisible();
    await expect(action).toHaveCount(0);
    await expect(main.getByText(NOT_SET)).toHaveCount(0);
    expect((await readShowcase(request)).letter).toBe(second.letter);

    // The first version gets the action back, naming the new showcase.
    await page.goto(`/#/lab/${version}/result/${first.letter}`);
    await expect(action).toHaveAttribute(
      'title',
      `Shows this version's result on the home page, in place of Version ${second.letter}'s.`,
    );
    await expect(onHome).toHaveCount(0);

    // Home shows the version now chosen.
    await page.goto('/#/');
    await page.reload();
    await expect(page.getByTestId('home-tile')).toContainText(`Version ${second.letter} of`);
  });
});
