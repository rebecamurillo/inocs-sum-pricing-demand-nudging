import { expect, type APIRequestContext } from '@playwright/test';
import type { TestControl } from './test-control';

const BUILD_TIMEOUT_MS = 60_000;
const PACKAGE_TIMEOUT_MS = 15_000;

interface RunAnswer {
  id: string;
  state: string;
}

export interface BuiltInstance {
  /** The version's id, `geneva-3km.v1`. */
  version: string;
  runId: string;
}

/**
 * Insert a fake city data set, create the instance "Geneva 3 km", move the minimum trip distance
 * apart from the grouping distance, queue the build and wait until it succeeded.
 */
export async function buildFakeInstance(
  request: APIRequestContext,
  control: TestControl,
  // The routes step is kept by the parameters it reads, not by what the fake was told to fail:
  // a scenario that makes queries fail takes its own distance, so no other build reuses its routes.
  minOdDistanceM = 900,
): Promise<BuiltInstance> {
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
    data: { min_od_distance_m: minOdDistanceM },
  });
  expect(patched.status()).toBe(200);
  const queued = await request.post(`/api/v1/instance-versions/${version}/builds`);
  expect(queued.status()).toBe(202);
  const run = (await queued.json()) as RunAnswer;
  await expect
    .poll(
      async () => ((await (await request.get(`/api/v1/runs/${run.id}`)).json()) as RunAnswer).state,
      { timeout: BUILD_TIMEOUT_MS, message: 'the build succeeds' },
    )
    .toBe('succeeded');
  return { version, runId: run.id };
}

/**
 * Wait until the worker has recorded the package's defaults, which a new instance starts from.
 * A throwaway instance is created and discarded: its draft is the only version, so discarding it
 * removes the instance too.
 */
export async function awaitPackageDefaults(
  request: APIRequestContext,
  datasetId: string,
): Promise<void> {
  const probe = {
    name: 'Probe',
    dataset_id: datasetId,
    start_from: { kind: 'package_defaults' },
  };
  await expect
    .poll(async () => (await request.post('/api/v1/city-instances', { data: probe })).status(), {
      timeout: PACKAGE_TIMEOUT_MS,
      message: 'the package defaults are known',
    })
    .toBe(201);
  const discarded = await request.delete('/api/v1/instance-versions/probe.v1');
  expect(discarded.status()).toBe(204);
}

interface CountsAnswer {
  counts: Record<
    'stops' | 'bike_stations' | 'hubs' | 'hub_pairs_with_routes' | 'travellers',
    { value: number }
  > | null;
}

/** Wait until a version is built and return its five headline counts as the API gives them. */
export async function builtCounts(
  request: APIRequestContext,
  version: string,
): Promise<Record<string, number>> {
  let found: Record<string, number> = {};
  await expect
    .poll(
      async () => {
        const answer = (await (
          await request.get(`/api/v1/instance-versions/${version}`)
        ).json()) as CountsAnswer;
        if (answer.counts === null) return false;
        found = Object.fromEntries(
          Object.entries(answer.counts).map(([name, number]) => [name, number.value]),
        );
        return true;
      },
      { timeout: BUILD_TIMEOUT_MS, message: `${version} is built` },
    )
    .toBe(true);
  return found;
}
