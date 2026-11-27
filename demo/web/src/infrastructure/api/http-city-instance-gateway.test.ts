import { describe, expect, it, vi } from 'vitest';
import { ApiProblemError } from '../../application/errors';
import { HttpCityInstanceGateway } from './http-city-instance-gateway';

const number = (value: number) => ({ value, unit: 'n', source: 'input', group: 'headline' });

const versionWire = {
  id: 'geneva-3km.v1',
  instance_id: 'geneva-3km',
  number: 1,
  based_on_id: null,
  status: 'sealed',
  sealed_at: '2026-11-12T10:00:00Z',
  state: 'ready',
  parameters: {
    center_lat: 46.2057,
    center_lon: 6.1489,
    radius_m: 3000,
    clustering_threshold_m: 500,
    clustering_buffer_m: 100,
    min_od_distance_m: 900,
    min_demand: 10,
    max_demand: 70,
    fixed_capacity: 20,
    min_inventory_pct: 0,
    max_inventory_pct: 100,
    min_park_time_min: 1,
    max_park_time_min: 5,
    seed: 42,
  },
  periods: [
    {
      id: 'geneva-3km.v1.mon-08',
      key: 'mon-08',
      label: 'Monday 08:00–09:00',
      weekday: 1,
      start_time: '08:00:00',
      end_time: '09:00:00',
      routing_date: '2025-03-10',
      routing_time: '08:30:00',
      arrive_by: true,
      routing_date_provisional: true,
    },
  ],
  rules: [],
  changes: [],
  counts: {
    stops: number(30),
    bike_stations: number(12),
    hubs: number(6),
    hub_pairs_with_routes: number(24),
    travellers: number(1000),
  },
  routes: {
    queries: 48,
    queries_failed: 2,
    failure_pct: 4.17,
    pairs_without_public_transport: 1,
    pairs_without_car: 1,
    retries: 3,
    run_id: 'run-1',
  },
  build_plan: { steps: [], build_verdict: { allowed: true, reasons: [] } },
};

function gatewayAnswering(answer: Response | Error) {
  const fetchFake = vi.fn<typeof fetch>(() =>
    answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer),
  );
  return { gateway: new HttpCityInstanceGateway(fetchFake), fetchFake };
}

async function failureOf(promise: Promise<unknown>): Promise<ApiProblemError> {
  const error = await promise.then(
    () => undefined,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiProblemError);
  return error as ApiProblemError;
}

describe('HttpCityInstanceGateway', () => {
  it('reads the menu', async () => {
    const { gateway, fetchFake } = gatewayAnswering(
      Response.json({
        items: [
          {
            id: 'geneva-3km',
            name: 'Geneva 3 km',
            dataset_id: 'geneva-2026-11-26',
            versions: [
              {
                id: 'geneva-3km.v1',
                number: 1,
                status: 'sealed',
                state: 'ready',
                pricing_version_count: 0,
              },
            ],
          },
        ],
      }),
    );

    expect(await gateway.menu()).toEqual([
      {
        id: 'geneva-3km',
        name: 'Geneva 3 km',
        datasetId: 'geneva-2026-11-26',
        versions: [
          {
            id: 'geneva-3km.v1',
            number: 1,
            status: 'sealed',
            state: 'ready',
            pricingVersionCount: 0,
          },
        ],
      },
    ]);
    expect(fetchFake).toHaveBeenCalledWith('/api/v1/city-instances', {
      headers: { Accept: 'application/json' },
    });
  });

  it('maps a built version: parameters, periods, counts, routes and the save instant', async () => {
    const { gateway, fetchFake } = gatewayAnswering(Response.json(versionWire));

    const version = await gateway.version('geneva-3km.v1');

    expect(fetchFake.mock.calls[0]?.[0]).toBe('/api/v1/instance-versions/geneva-3km.v1');
    expect(version).toMatchObject({
      id: 'geneva-3km.v1',
      instanceId: 'geneva-3km',
      number: 1,
      status: 'sealed',
      state: 'ready',
      parameters: { centerLat: 46.2057, clusteringThresholdM: 500, minParkTimeMin: 1, seed: 42 },
      periods: [
        {
          label: 'Monday 08:00–09:00',
          startTime: '08:00:00',
          routingDate: '2025-03-10',
          routingTime: '08:30:00',
          arriveBy: true,
          provisional: true,
        },
      ],
      counts: { stops: 30, bikeStations: 12, hubs: 6, hubPairsWithRoutes: 24, travellers: 1000 },
      routes: {
        queries: 48,
        queriesFailed: 2,
        failurePct: 4.17,
        pairsWithoutPublicTransport: 1,
        pairsWithoutCar: 1,
        retries: 3,
        runId: 'run-1',
      },
    });
    expect(version?.sealedAt?.toISOString()).toBe('2026-11-12T10:00:00.000Z');
  });

  it('maps a draft: no save instant, no counts, no routes', async () => {
    const { gateway } = gatewayAnswering(
      Response.json({
        ...versionWire,
        status: 'draft',
        sealed_at: null,
        counts: null,
        routes: null,
      }),
    );

    expect(await gateway.version('geneva-3km.v1')).toMatchObject({
      sealedAt: null,
      counts: null,
      routes: null,
    });
  });

  it('answers null for a version that does not exist and fails for another status', async () => {
    expect(
      await gatewayAnswering(new Response('{}', { status: 404 })).gateway.version('x.v1'),
    ).toBeNull();
    const failure = await failureOf(
      gatewayAnswering(new Response('x', { status: 500 })).gateway.version('x.v1'),
    );
    expect(failure.code).toBe('unexpected_response');
  });

  it('reads the data set by id', async () => {
    const wire = {
      items: [
        {
          id: 'a',
          name: 'Geneva',
          gtfs_valid_from: '2024-12-15',
          gtfs_valid_to: '2025-12-13',
          gbfs_fetched_at: '2026-11-10T09:30:00Z',
        },
      ],
    };

    expect(await gatewayAnswering(Response.json(wire)).gateway.dataset('a')).toEqual({
      id: 'a',
      name: 'Geneva',
      timetableValidFrom: '2024-12-15',
      timetableValidTo: '2025-12-13',
      bikeStationsFetchedAt: '2026-11-10T09:30:00Z',
    });
    expect(await gatewayAnswering(Response.json(wire)).gateway.dataset('b')).toBeNull();
  });

  it('maps the stations, the hubs with their outline ring and the hub pairs', async () => {
    const stations = gatewayAnswering(
      Response.json({ items: [{ station_id: 'p1', kind: 'pt', name: 'P', lat: 46.2, lon: 6.1 }] }),
    );
    expect(await stations.gateway.stations('v.v1')).toEqual([
      { id: 'p1', kind: 'pt', lat: 46.2, lon: 6.1 },
    ]);
    expect(stations.fetchFake.mock.calls[0]?.[0]).toBe('/api/v1/instance-versions/v.v1/stations');

    const hubs = gatewayAnswering(
      Response.json({
        items: [
          {
            hub_id: 'H1',
            label: 'Rive',
            lat: 46.2,
            lon: 6.1,
            outline: {
              type: 'Polygon',
              coordinates: [
                [
                  [6.1, 46.1],
                  [6.2, 46.1],
                  [6.1, 46.1],
                ],
              ],
            },
          },
          { hub_id: 'H2', label: 'Plainpalais', lat: 46.3, lon: 6.2, outline: null },
        ],
      }),
    );
    expect(await hubs.gateway.hubs('v.v1')).toEqual([
      {
        id: 'H1',
        label: 'Rive',
        lat: 46.2,
        lon: 6.1,
        outline: [
          [6.1, 46.1],
          [6.2, 46.1],
          [6.1, 46.1],
        ],
      },
      { id: 'H2', label: 'Plainpalais', lat: 46.3, lon: 6.2, outline: null },
    ]);

    const pairs = gatewayAnswering(
      Response.json({
        items: [{ origin_hub: 'H1', destination_hub: 'H2', demand: 1, euclid_dist_m: 2 }],
      }),
    );
    expect(await pairs.gateway.hubPairs('v.v1')).toEqual([
      { originHub: 'H1', destinationHub: 'H2' },
    ]);
  });

  it('maps the route failures of a run', async () => {
    const { gateway, fetchFake } = gatewayAnswering(
      Response.json({
        items: [
          {
            origin_hub: 'H1',
            destination_hub: 'H2',
            query: 'pt_bike',
            kind: 'technical',
            message: 'timeout',
            attempts: 4,
            period: null,
          },
        ],
      }),
    );

    expect(await gateway.routeFailures('run-1')).toEqual([
      {
        originHub: 'H1',
        destinationHub: 'H2',
        query: 'pt_bike',
        kind: 'technical',
        message: 'timeout',
        attempts: 4,
      },
    ]);
    expect(fetchFake.mock.calls[0]?.[0]).toBe('/api/v1/runs/run-1/route-failures');
  });

  it('reports an unreachable API and an answer that is not JSON', async () => {
    const unreachable = await failureOf(gatewayAnswering(new Error('offline')).gateway.menu());
    expect(unreachable.code).toBe('api_unreachable');
    expect(unreachable.detail).toBe('offline');

    const notJson = await failureOf(
      gatewayAnswering(new Response('<html>', { status: 200 })).gateway.menu(),
    );
    expect(notJson.detail).toBe('The answer is not JSON.');
  });
});
