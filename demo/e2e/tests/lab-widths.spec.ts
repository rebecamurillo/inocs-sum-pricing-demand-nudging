import type { Page } from '@playwright/test';
import { awaitPackageDefaults, buildFakeInstance, queueFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';
import { createPricingVersion } from '../support/pricing';

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
    await context.close();
  });
});
