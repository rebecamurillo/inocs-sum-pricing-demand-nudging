import type { Page } from '@playwright/test';
import { expect, test } from '../support/fixtures';

const noShowcase =
  'No result on this page yet. In the Lab, open the result of a pricing version and choose "Use on the home page".';

const texts = [
  'Dynamic pricing',
  'For cities and public transport operators',
  'A research model from the SUM project sets the bike price of each trip, to nudge travellers from the car to shared bikes and public transport.',
  'The problem',
  'For each trip, people compare time, price and changes. Too often the car wins, and a flat bike price is the same on every trip.',
  'The idea',
  "You say what matters: more riders, the operator's profit, bikes where they are needed. The model chooses a price for each trip, lower where a bike can replace a car. Nobody is forced: travellers still choose.",
  'A familiar lever, a different goal',
  'Plane tickets move with demand to fill the plane. Here the price moves with the trip, to take cars off the street.',
  'Two ways in. Choose by what you want to do.',
  '5 minutes · for everyone',
  "Play: take the operator's seat",
  'One mission: get travellers out of their cars without losing revenue. Three choices, three tries, then watch your prices at work over one day.',
  'Coming after the proof of concept',
  'For analysts and researchers',
  'Lab: run the model yourself',
  'Prepare a city instance, set the pricing goals, run the model live for one morning hour, then compare versions and the price of any trip.',
];

const sizes = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1280, height: 720 },
  { width: 390, height: 844 },
];

async function expectHomeTexts(page: Page) {
  // The header: blue, 56 px, with "Try it" as a button.
  const header = page.getByRole('banner');
  expect((await header.boundingBox())?.height).toBe(56);
  expect(await header.evaluate((element) => getComputedStyle(element).backgroundColor)).toBe(
    'rgb(0, 68, 148)',
  );
  await expect(header.getByRole('button', { name: 'Try it' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Price shared bikes by the trip, and fewer people take the car.',
  );
  for (const text of texts) await expect(page.getByText(text, { exact: true })).toBeVisible();
  await expect(
    page.getByText(
      "A research model by placeholder, Inria INOCS, run on one zone of Geneva with simulated demand. The figure above comes from the model's prices and a simulation of travellers, not from a trial in the street.",
    ),
  ).toBeVisible();
  await expect(page.getByRole('contentinfo')).toContainText(
    'Funded by the European Union under Horizon Europe, project SUM.',
  );
  await expect(page.getByRole('contentinfo')).toContainText(
    'Pricing model: placeholder, Inria INOCS.',
  );
  await expect(page.getByRole('contentinfo')).not.toContainText('Run unmodified');
  await expect(page.getByText('[Q-28]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Larger text for a projector' })).toHaveCount(0);
  const play = page.getByRole('button', { name: 'Play the game →' });
  await expect(play).toHaveAttribute('aria-disabled', 'true');
  await expect(play).toHaveAttribute(
    'title',
    'Play is designed and is built after the proof of concept.',
  );
  await expect(page.getByRole('button', { name: 'Open the Lab →' })).toHaveAttribute(
    'data-primary',
    'true',
  );
}

test.describe('Home', () => {
  test('Home · with no showcase set, Home shows its no-showcase state', async ({ page }) => {
    const apiRequests: string[] = [];
    page.on('request', (request) => {
      if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url());
    });

    await page.goto('/#/');

    await expect(page.getByTestId('home-visual')).toContainText(noShowcase);
    await expect(page.getByTestId('home-visual')).not.toContainText('SIMULATION');
    expect(apiRequests).toHaveLength(1);
    expect(new URL(apiRequests[0] ?? '').pathname).toBe('/api/v1/showcase');
    // The visual keeps its size: square above 900 px.
    const box = await page.getByTestId('home-visual').boundingBox();
    expect(Math.abs((box?.width ?? 0) - (box?.height ?? 1))).toBeLessThanOrEqual(1);
    const ground = await page
      .getByTestId('home-visual')
      .evaluate((element) => getComputedStyle(element).backgroundColor);
    expect(ground).toBe('rgb(228, 229, 226)');
  });

  test('Home · `#/` shows the two sections, the Play card "Coming after the proof of concept", the headline from the showcase, and "Open the Lab →" opens the Lab, whose "← Home" returns', async ({
    page,
    browser,
    baseURL,
  }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page).toHaveURL(/\/$/);
    await page.goto('/#/play');
    await expectHomeTexts(page);
    await expect(page).toHaveURL(/#\/play$/);

    await page.goto('/#/');
    await expectHomeTexts(page);

    await page.getByRole('button', { name: 'Try it' }).click();
    await expect(page.getByRole('region', { name: 'Try it' })).toBeInViewport();
    await expect(page).toHaveURL(/#\/$/);

    await page.getByRole('button', { name: 'Play the game →' }).dispatchEvent('click');
    await expect(page).toHaveURL(/#\/$/);

    await page.getByRole('button', { name: 'Open the Lab →' }).click();
    await expect(page).toHaveURL(/#\/lab$/);
    await expect(page.getByText('Dynamic pricing · Lab')).toBeVisible();
    await page.getByRole('link', { name: '← Home' }).click();
    await expect(page).toHaveURL(/#\/$/);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    for (const size of sizes) {
      await page.setViewportSize(size);
      await page.goto('/#/');
      const widths = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        inner: window.innerWidth,
      }));
      expect(widths.scroll).toBeLessThanOrEqual(widths.inner);
      await page.getByRole('button', { name: 'Try it' }).click();
      await expect(page.getByRole('button', { name: 'Open the Lab →' })).toBeInViewport();
    }

    // At 390 px the Lab card sits below the Play card and the visual is 5:4.
    await page.setViewportSize({ width: 390, height: 844 });
    const play = await page.getByRole('article').first().boundingBox();
    const lab = await page.getByRole('article').last().boundingBox();
    expect(lab?.y ?? 0).toBeGreaterThan((play?.y ?? 0) + (play?.height ?? 0) - 1);
    const visual = await page.getByTestId('home-visual').boundingBox();
    expect(Math.abs((visual?.width ?? 0) / (visual?.height ?? 1) - 5 / 4)).toBeLessThan(0.02);

    // Reduced motion: no transition or animation time, and the scroll is not smooth.
    const context = await browser.newContext({ reducedMotion: 'reduce', baseURL });
    const reduced = await context.newPage();
    await reduced.goto('/#/');
    await expect(reduced.getByRole('heading', { level: 1 })).toBeVisible();
    const durations = await reduced.evaluate(() =>
      Array.from(document.querySelectorAll('body *')).flatMap((element) => {
        const style = getComputedStyle(element);
        return [style.transitionDuration, style.animationDuration];
      }),
    );
    expect(durations.length).toBeGreaterThan(0);
    for (const duration of durations) {
      expect(duration.split(',').every((part) => part.trim() === '0s')).toBe(true);
    }
    // Home scrolls inside its root (the parent of <main>): read its position at once and later.
    const scrollTop = () =>
      reduced.evaluate(() => document.querySelector('main')?.parentElement?.scrollTop ?? 0);
    await reduced.getByRole('button', { name: 'Try it' }).click();
    const atOnce = await scrollTop();
    await expect(reduced.getByRole('region', { name: 'Try it' })).toBeInViewport();
    await reduced.waitForTimeout(600);
    expect(atOnce).toBeGreaterThan(0);
    expect(await scrollTop()).toBe(atOnce);
    await expect(reduced).toHaveURL(/#\/$/);
    await context.close();
  });
});
