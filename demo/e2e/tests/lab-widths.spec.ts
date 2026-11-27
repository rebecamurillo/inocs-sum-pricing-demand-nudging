import { expect, test } from '../support/fixtures';

const viewports = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1280, height: 720 },
];

test.describe('Lab', () => {
  test('Lab · every built view holds at 1440, 1280 and 1280 × 720 with Aa', async ({ page }) => {
    await page.goto('/');
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
        await expect(page.getByText('No run in progress')).toBeInViewport({ ratio: 1 });
        await expect(aa).toBeInViewport({ ratio: 1 });
        // The map pane is part of the held view (the e2e stack has no basemap file: ground colour).
        await expect(page.getByRole('region', { name: 'Map' })).toBeInViewport({ ratio: 1 });
        await aa.click();
      }
    }
  });

  test('Lab · under reduced motion the shell has no transition or animation time', async ({
    browser,
    baseURL,
  }) => {
    const context = await browser.newContext({ reducedMotion: 'reduce', baseURL });
    const page = await context.newPage();
    await page.goto('/');
    await expect(page.getByText('Dynamic pricing · Lab')).toBeVisible();

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
    await context.close();
  });
});
