import { expect, test } from '../support/fixtures';
import { buildFakeInstance } from '../support/build';
import {
  createPricingVersion,
  runPricingVersion,
  waitForRun,
  waitForSimulationRule,
} from '../support/pricing';
import { restartApiAndWorker } from '../support/stack';

test.describe('Lab restart', () => {
  test('Lab · after the stack restarts, instances and versions are there without recomputation', async ({
    page,
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control);
    // A pricing version with its result: the pricing run and both simulations are stored.
    const pricing = await createPricingVersion(request, version);
    const queued = await runPricingVersion(request, pricing.id);
    expect(queued.status()).toBe(202);
    const pricingRun = (await queued.json()) as { id: string };
    expect((await waitForRun(request, pricingRun.id, 'succeeded')).failure).toBeNull();
    await waitForSimulationRule(request, 1);

    const paths = [
      '/api/v1/city-instances',
      `/api/v1/instance-versions/${version}`,
      `/api/v1/instance-versions/${version}/stations`,
      `/api/v1/instance-versions/${version}/hubs`,
      `/api/v1/instance-versions/${version}/hub-pairs`,
      `/api/v1/pricing-versions/${pricing.id}`,
      `/api/v1/pricing-versions/${pricing.id}/result`,
      `/api/v1/pricing-versions/${pricing.id}/hub-pair-results`,
      `/api/v1/pricing-versions/${pricing.id}/hub-results`,
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
    const [, built, stations, hubs, pairs, , result, pairResults, hubResults] = before as [
      unknown,
      { counts: Record<string, { value: number }> | null },
      { items: unknown[] },
      { items: unknown[] },
      { items: unknown[] },
      unknown,
      { headline: Record<string, { source: string; group: string }> },
      { items: unknown[] },
      { items: unknown[] },
    ];
    expect(result.headline.ridership?.source).toBe('model');
    expect(pairResults.items).toHaveLength(24);
    expect(hubResults.items).toHaveLength(6);
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

    // The runs the stack knows: a restart adds none.
    const runIds = async (): Promise<string[]> => {
      const response = await request.get('/api/v1/runs');
      expect(response.status()).toBe(200);
      const { items } = (await response.json()) as { items: { id: string; state: string }[] };
      return items.map((item) => `${item.id} ${item.state}`);
    };
    const runsBefore = await runIds();
    expect(runsBefore.length).toBeGreaterThan(1);

    await restartApiAndWorker(request);
    // `rule_current` of the result reads the live worker's heartbeat: wait for the new one.
    await waitForSimulationRule(request, 1);

    expect(await read()).toEqual(before);
    expect(await runIds()).toEqual(runsBefore);
    expect(await lab()).toEqual(countsBefore);
    const active = await request.get('/api/v1/runs?state=queued,running');
    expect(active.status()).toBe(200);
    expect(await active.json()).toEqual({ items: [] });
  });
});
