import type { APIRequestContext } from '@playwright/test';
import { expect, test } from '../support/fixtures';

const components = ['storage', 'runner', 'solver', 'package', 'trip_planner', 'city_data'];

interface Verdict {
  allowed: boolean;
  reasons: { component: string; reason: string }[];
}

interface StatusAnswer {
  components: { name: string; state: string; reason: string | null }[];
  can_build_instances: Verdict;
  can_run_pricing: Verdict;
  can_simulate: Verdict;
}

async function readStatus(request: APIRequestContext): Promise<StatusAnswer> {
  const response = await request.get('/api/v1/system-status');
  expect(response.status()).toBe(200);
  return (await response.json()) as StatusAnswer;
}

function component(status: StatusAnswer, name: string) {
  const found = status.components.find((candidate) => candidate.name === name);
  if (found === undefined) throw new Error(`The status has no component ${name}.`);
  return found;
}

test.describe('System status', () => {
  test('every component available: all six components read available and builds, pricing runs and simulations can start', async ({
    request,
    control,
  }) => {
    await control.insertCityDataset();
    const status = await readStatus(request);

    expect(status.components.map((entry) => entry.name)).toEqual(components);
    for (const name of components) {
      expect(component(status, name).state).toBe('available');
    }
    expect(status.can_build_instances.allowed).toBe(true);
    expect(status.can_run_pricing.allowed).toBe(true);
    expect(status.can_simulate.allowed).toBe(true);
  });

  test('NFR-2 · an unavailable trip planner is shown with its reason and refuses builds only', async ({
    request,
    control,
  }) => {
    const reason = 'No answer from http://otp:8080/otp/gtfs/v1 within 2 s.';
    await control.insertCityDataset();
    await control.makeUnavailable('trip_planner', reason);

    const status = await readStatus(request);

    const tripPlanner = component(status, 'trip_planner');
    expect(tripPlanner.state).toBe('unavailable');
    expect(tripPlanner.reason).toContain(reason);
    expect(status.can_build_instances.allowed).toBe(false);
    expect(status.can_build_instances.reasons).toEqual([{ component: 'trip_planner', reason }]);
    expect(status.can_run_pricing.allowed).toBe(true);
    expect(status.can_simulate.allowed).toBe(true);
  });

  test('NFR-2 · with the solver limited, pricing runs are refused with its reason; builds and simulations are not', async ({
    request,
    control,
  }) => {
    const reason = 'Size-limited Gurobi licence: a model of 2001 variables is refused.';
    await control.insertCityDataset();
    await control.makeLimited('solver', reason);

    const status = await readStatus(request);

    const solver = component(status, 'solver');
    expect(solver.state).toBe('limited');
    expect(solver.reason).toContain(reason);
    expect(status.can_run_pricing.allowed).toBe(false);
    expect(status.can_run_pricing.reasons).toEqual([{ component: 'solver', reason }]);
    expect(status.can_build_instances.allowed).toBe(true);
    expect(status.can_simulate.allowed).toBe(true);
  });

  test('a reset leaves no city data: city_data is unavailable with its reason and builds are refused until a data set is inserted', async ({
    request,
    control,
  }) => {
    const reason = 'No city data is imported yet';

    const empty = await readStatus(request);

    expect(component(empty, 'city_data').state).toBe('unavailable');
    expect(component(empty, 'city_data').reason).toBe(reason);
    expect(empty.can_build_instances.allowed).toBe(false);
    expect(empty.can_build_instances.reasons).toEqual([{ component: 'city_data', reason }]);
    expect(empty.can_run_pricing.allowed).toBe(true);
    expect(empty.can_simulate.allowed).toBe(true);

    const id = await control.insertCityDataset();

    expect(id).toMatch(/^geneva-\d{4}-\d{2}-\d{2}$/);
    const filled = await readStatus(request);
    expect(component(filled, 'city_data').state).toBe('available');
    expect(component(filled, 'city_data').reason).toBeNull();
    expect(filled.can_build_instances.allowed).toBe(true);
  });
});
