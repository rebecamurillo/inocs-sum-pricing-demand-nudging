import { expect, test } from '../support/fixtures';
import { buildFakeInstance } from '../support/build';
import { restartApiAndWorker } from '../support/stack';

test.describe('Lab restart', () => {
  test('Lab · after the stack restarts, instances and versions are there without recomputation', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);

    const paths = [
      '/api/v1/city-instances',
      `/api/v1/instance-versions/${version}`,
      `/api/v1/instance-versions/${version}/stations`,
      `/api/v1/instance-versions/${version}/hubs`,
      `/api/v1/instance-versions/${version}/hub-pairs`,
    ];
    const read = async (): Promise<unknown[]> =>
      Promise.all(
        paths.map(async (path) => {
          const response = await request.get(path);
          expect(response.status(), path).toBe(200);
          return response.json() as Promise<unknown>;
        }),
      );
    const before = await read();
    const [, built, stations, hubs, pairs] = before as [
      unknown,
      { counts: Record<string, { value: number }> | null },
      { items: unknown[] },
      { items: unknown[] },
      { items: unknown[] },
    ];
    expect(built.counts).not.toBeNull();
    expect(built.counts?.stops?.value).toBe(30);
    expect(built.counts?.bike_stations?.value).toBe(12);
    expect([stations.items.length, hubs.items.length, pairs.items.length]).toEqual([42, 6, 24]);
    expect(built.counts?.hubs?.value).toBe(6);
    expect(built.counts?.hub_pairs_with_routes?.value).toBe(24);

    const grouped = (value: number | undefined) =>
      String(value ?? Number.NaN).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    const expectedCounts = [
      ['Stops and platforms', grouped(built.counts?.stops?.value)],
      ['Bike stations', grouped(built.counts?.bike_stations?.value)],
      ['Hubs', grouped(built.counts?.hubs?.value)],
      ['Hub pairs with routes', grouped(built.counts?.hub_pairs_with_routes?.value)],
      ['Travellers in the period', grouped(built.counts?.travellers?.value)],
    ];
    const lab = async () => {
      // A blank page first: the Lab loads again and reads the API, not the page's cache.
      await page.goto('about:blank');
      await page.goto(`/#/lab/${version}`);
      // The menu row of the instance: its name, the version tag and its state.
      await expect(page.getByRole('button', { name: 'Geneva 3 km v1 ready' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Instance set-up' })).toHaveAttribute(
        'aria-current',
        'page',
      );
      const shown: string[][] = [];
      for (const [at, [label]] of expectedCounts.entries()) {
        await expect(page.getByRole('term').nth(at)).toHaveText(label ?? '');
        shown.push([
          (await page.getByRole('term').nth(at).textContent()) ?? '',
          (await page.getByRole('definition').nth(at).textContent()) ?? '',
        ]);
      }
      return shown;
    };
    const countsBefore = await lab();
    expect(countsBefore).toEqual(expectedCounts);

    await restartApiAndWorker(request);

    expect(await read()).toEqual(before);
    expect(await lab()).toEqual(countsBefore);
    const active = await request.get('/api/v1/runs?state=queued,running');
    expect(active.status()).toBe(200);
    expect(await active.json()).toEqual({ items: [] });
  });
});
