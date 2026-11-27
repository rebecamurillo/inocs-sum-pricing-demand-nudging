import { expect, test } from '../support/fixtures';
import { restartApiAndWorker } from '../support/stack';

const BUILD_TIMEOUT_MS = 60_000;
const PACKAGE_TIMEOUT_MS = 15_000;

interface RunAnswer {
  id: string;
  state: string;
}

test.describe('Lab restart', () => {
  test('Lab · after the stack restarts, instances and versions are there without recomputation', async ({
    request,
    control,
  }) => {
    const datasetId = await control.insertCityDataset();
    const create = {
      name: 'Geneva 3 km',
      dataset_id: datasetId,
      start_from: { kind: 'package_defaults' },
    };
    // The worker records the package's defaults in its first cycle after the reset.
    // The poll stops at the first 201: the instance is created once.
    await expect
      .poll(async () => (await request.post('/api/v1/city-instances', { data: create })).status(), {
        timeout: PACKAGE_TIMEOUT_MS,
        message: 'the package defaults are known',
      })
      .toBe(201);
    // The first draft of an instance named "Geneva 3 km".
    const version = 'geneva-3km.v1';
    // The package's defaults tie two distances; a build needs them apart.
    const patched = await request.patch(`/api/v1/instance-versions/${version}`, {
      data: { min_od_distance_m: 900 },
    });
    expect(patched.status()).toBe(200);
    const queued = await request.post(`/api/v1/instance-versions/${version}/builds`);
    expect(queued.status()).toBe(202);
    const run = (await queued.json()) as RunAnswer;
    await expect
      .poll(
        async () =>
          ((await (await request.get(`/api/v1/runs/${run.id}`)).json()) as RunAnswer).state,
        { timeout: BUILD_TIMEOUT_MS, message: 'the build succeeds' },
      )
      .toBe('succeeded');

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

    await restartApiAndWorker(request);

    expect(await read()).toEqual(before);
    const active = await request.get('/api/v1/runs?state=queued,running');
    expect(active.status()).toBe(200);
    expect(await active.json()).toEqual({ items: [] });
  });
});
