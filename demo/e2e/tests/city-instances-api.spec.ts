import { expect, test } from '../support/fixtures';
import { awaitPackageDefaults, buildFakeInstance } from '../support/build';

// The answers of the city-instance resources the L-1 screens read and write, on the stack.
// The screens' own scenarios are lab-*.spec.ts; these cover the problems a client can meet.
const problemType = 'application/problem+json';
// Its own distance, so no other scenario's build finds this one's routes already computed.
const API_DISTANCE_M = 930;

interface Problem {
  code: string;
  draft_id?: string;
  errors?: { field: string }[];
}

interface Version {
  id: string;
  instance_id: string;
  number: number;
  based_on_id: string | null;
  status: string;
  counts: unknown;
}

interface Menu {
  items: { id: string; name: string; versions: { id: string; status: string }[] }[];
}

test.describe('City instances · API', () => {
  test('City instances · the data set is listed and a new instance starts as a draft v1 in the menu', async ({
    request,
    control,
  }) => {
    const datasetId = await control.insertCityDataset();
    await awaitPackageDefaults(request, datasetId);

    const datasets = await request.get('/api/v1/city-datasets');
    expect(datasets.status()).toBe(200);
    const ids = ((await datasets.json()) as { items: { id: string }[] }).items.map((d) => d.id);
    expect(ids).toContain(datasetId);

    const created = await request.post('/api/v1/city-instances', {
      data: { name: 'Geneva API', dataset_id: datasetId, start_from: { kind: 'package_defaults' } },
    });
    expect(created.status()).toBe(201);
    const draft = (await created.json()) as Version;
    expect(created.headers().location).toBe(`/api/v1/instance-versions/${draft.id}`);
    expect(draft).toMatchObject({ number: 1, status: 'draft', based_on_id: null, counts: null });

    const menu = (await (await request.get('/api/v1/city-instances')).json()) as Menu;
    expect(menu.items).toEqual([
      expect.objectContaining({
        id: draft.instance_id,
        name: 'Geneva API',
        versions: [expect.objectContaining({ id: draft.id, status: 'draft' })],
      }),
    ]);
  });

  test('City instances · a taken name is 409 name_taken, an unknown data set 422, an empty name a validation problem', async ({
    request,
    control,
  }) => {
    const datasetId = await control.insertCityDataset();
    await awaitPackageDefaults(request, datasetId);
    const body = {
      name: 'Geneva API',
      dataset_id: datasetId,
      start_from: { kind: 'package_defaults' },
    };
    expect((await request.post('/api/v1/city-instances', { data: body })).status()).toBe(201);

    const cases: [Record<string, unknown>, number, string][] = [
      [body, 409, 'name_taken'],
      [{ ...body, name: 'Other', dataset_id: 'no-such-dataset' }, 422, 'unknown_city_dataset'],
      [{ ...body, name: '' }, 422, 'validation_failed'],
    ];
    for (const [data, status, code] of cases) {
      const response = await request.post('/api/v1/city-instances', { data });
      expect(response.status()).toBe(status);
      expect(response.headers()['content-type']).toContain(problemType);
      expect(((await response.json()) as Problem).code).toBe(code);
    }
  });

  test('City instances · an unknown version or instance answers a 404 problem with its code', async ({
    request,
  }) => {
    const unknownVersion = [
      await request.get('/api/v1/instance-versions/nowhere.v1'),
      await request.get('/api/v1/instance-versions/nowhere.v1/hubs'),
      await request.patch('/api/v1/instance-versions/nowhere.v1', { data: { seed: 1 } }),
      await request.delete('/api/v1/instance-versions/nowhere.v1'),
      await request.post('/api/v1/instance-versions/nowhere.v1/builds'),
    ];
    for (const response of unknownVersion) {
      expect(response.status()).toBe(404);
      expect(response.headers()['content-type']).toContain(problemType);
      expect(((await response.json()) as Problem).code).toBe('instance_version_not_found');
    }

    const unknownInstance = [
      await request.delete('/api/v1/city-instances/nowhere'),
      await request.post('/api/v1/city-instances/nowhere/versions', {
        data: { based_on_id: 'nowhere.v1' },
      }),
    ];
    for (const response of unknownInstance) {
      expect(response.status()).toBe(404);
      expect(((await response.json()) as Problem).code).toBe('city_instance_not_found');
    }
  });

  test('City instances · a draft is not built: its stations, hubs and routed pairs are empty lists', async ({
    request,
    control,
  }) => {
    const datasetId = await control.insertCityDataset();
    await awaitPackageDefaults(request, datasetId);
    const draft = (await (
      await request.post('/api/v1/city-instances', {
        data: {
          name: 'Geneva API',
          dataset_id: datasetId,
          start_from: { kind: 'package_defaults' },
        },
      })
    ).json()) as Version;

    for (const list of ['stations', 'hubs', 'route-pairs']) {
      const response = await request.get(`/api/v1/instance-versions/${draft.id}/${list}`);

      expect(response.status()).toBe(200);
      expect(await response.json()).toEqual({ items: [] });
    }
  });

  test('City instances · a built version is sealed; a new draft is based on it, only one at a time; deleting the instance removes both', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, API_DISTANCE_M);
    const built = (await (
      await request.get(`/api/v1/instance-versions/${version}`)
    ).json()) as Version;
    expect(built.status).toBe('sealed');

    const sealedPatch = await request.patch(`/api/v1/instance-versions/${version}`, {
      data: { seed: 7 },
    });
    expect(sealedPatch.status()).toBe(409);
    expect(((await sealedPatch.json()) as Problem).code).toBe('version_sealed');
    const rebuild = await request.post(`/api/v1/instance-versions/${version}/builds`);
    expect(rebuild.status()).toBe(409);
    expect(((await rebuild.json()) as Problem).code).toBe('already_built');

    const versions = `/api/v1/city-instances/${built.instance_id}/versions`;
    const created = await request.post(versions, { data: { based_on_id: version } });
    expect(created.status()).toBe(201);
    const draft = (await created.json()) as Version;
    expect(draft).toMatchObject({ number: 2, status: 'draft', based_on_id: version });

    const second = await request.post(versions, { data: { based_on_id: version } });
    expect(second.status()).toBe(409);
    const problem = (await second.json()) as Problem;
    expect(problem.code).toBe('draft_exists');
    expect(problem.draft_id).toBe(draft.id);

    const deleted = await request.delete(`/api/v1/city-instances/${built.instance_id}`);
    expect(deleted.status()).toBe(204);
    for (const id of [version, draft.id]) {
      expect((await request.get(`/api/v1/instance-versions/${id}`)).status()).toBe(404);
    }
    const menu = (await (await request.get('/api/v1/city-instances')).json()) as Menu;
    expect(menu.items).toEqual([]);
  });
});
