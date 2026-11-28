import { describe, expect, it, vi } from 'vitest';
import { ApiProblemError } from '../../application/errors';
import { HttpCityDatasetGateway } from './http-city-dataset-gateway';

const wire = {
  items: [
    {
      id: 'geneva-2026-11-26',
      name: 'Geneva',
      available_area: {
        type: 'Polygon',
        coordinates: [
          [
            [5.9, 46.1],
            [6.3, 46.1],
            [6.3, 46.4],
            [5.9, 46.4],
            [5.9, 46.1],
          ],
        ],
      },
      preset: { centre_lat: 46.2, centre_lon: 6.14, radius_m: 3000 },
    },
  ],
};

function gatewayAnswering(answer: Response | Error) {
  const fetchFake = vi.fn<typeof fetch>(() =>
    answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer),
  );
  return { gateway: new HttpCityDatasetGateway(fetchFake), fetchFake };
}

async function failureOf(promise: Promise<unknown>): Promise<ApiProblemError> {
  const error = await promise.then(
    () => undefined,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiProblemError);
  return error as ApiProblemError;
}

describe('HttpCityDatasetGateway', () => {
  it('reads the data sets and maps the preset and the area box', async () => {
    const { gateway, fetchFake } = gatewayAnswering(Response.json(wire));

    expect(await gateway.list()).toEqual([
      {
        id: 'geneva-2026-11-26',
        centre: { lat: 46.2, lon: 6.14 },
        radiusM: 3000,
        availableArea: [5.9, 46.1, 6.3, 46.4],
      },
    ]);
    expect(fetchFake).toHaveBeenCalledWith('/api/v1/city-datasets', {
      headers: { Accept: 'application/json' },
    });
  });

  it('reports an unreachable API', async () => {
    const { gateway } = gatewayAnswering(new Error('offline'));

    const failure = await failureOf(gateway.list());

    expect(failure.code).toBe('api_unreachable');
    expect(failure.detail).toBe('offline');
  });

  it('reports a status that is not ok', async () => {
    const { gateway } = gatewayAnswering(new Response('x', { status: 502 }));

    expect((await failureOf(gateway.list())).code).toBe('unexpected_response');
  });

  it('reports an answer that is not JSON', async () => {
    const { gateway } = gatewayAnswering(new Response('<html>', { status: 200 }));

    expect((await failureOf(gateway.list())).detail).toBe('The answer is not JSON.');
  });
});
