import { expect, test } from '../support/fixtures';

// No route creates a run before story 2-4, so on the stack the runs resource is read empty;
// the run shapes themselves are covered by the API's route tests.
const unknownRun = '01936b2e-7c4a-7000-8000-000000000000';
const problemType = 'application/problem+json';

test.describe('Runs', () => {
  test('Runs · an empty Lab lists no run, with or without a state filter', async ({ request }) => {
    for (const path of ['/api/v1/runs', '/api/v1/runs?state=queued,running']) {
      const response = await request.get(path);

      expect(response.status()).toBe(200);
      expect(await response.json()).toEqual({ items: [] });
    }
  });

  test('Runs · an unknown state in the filter is a validation problem', async ({ request }) => {
    const response = await request.get('/api/v1/runs?state=queued,paused');

    expect(response.status()).toBe(422);
    expect(response.headers()['content-type']).toContain(problemType);
    const problem = (await response.json()) as { code: string; errors: { field: string }[] };
    expect(problem.code).toBe('validation_failed');
    expect(problem.errors.map((error) => error.field)).toEqual(['state']);
  });

  test('Runs · an unknown run answers a 404 problem with the code run_not_found', async ({
    request,
  }) => {
    const answers = [
      await request.get(`/api/v1/runs/${unknownRun}`),
      await request.get(`/api/v1/runs/${unknownRun}/log`),
      await request.put(`/api/v1/runs/${unknownRun}/cancellation`),
    ];

    for (const response of answers) {
      expect(response.status()).toBe(404);
      expect(response.headers()['content-type']).toContain(problemType);
      expect(((await response.json()) as { code: string }).code).toBe('run_not_found');
    }
  });

  test('Runs · a path under the API that matches no route is a not_found problem', async ({
    request,
  }) => {
    const response = await request.get('/api/v1/no-such-resource');

    expect(response.status()).toBe(404);
    expect(response.headers()['content-type']).toContain(problemType);
    expect(((await response.json()) as { code: string }).code).toBe('not_found');
  });

  test('Runs · the worker is the runner the system status reads as alive', async ({ request }) => {
    const response = await request.get('/api/v1/system-status');

    expect(response.status()).toBe(200);
    const status = (await response.json()) as { components: { name: string; state: string }[] };
    expect(status.components.find((entry) => entry.name === 'runner')?.state).toBe('available');
  });
});
