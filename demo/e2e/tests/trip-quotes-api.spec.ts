import { buildFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';
import { createPricingVersion, finishVersion } from '../support/pricing';

// The answers of the three routes the traveller view (L-5) reads, on the stack: trip quotes,
// place names and route options. The screen's own scenario is traveller-view.spec.ts; these
// cover every no-price status and the problems a client can meet.
const problemType = 'application/problem+json';
// Their own distances, so no other scenario's build finds these routes already computed; the
// second build makes route queries fail.
const QUOTES_DISTANCE_M = 905;
const FAILURES_DISTANCE_M = 907;

interface NumberResource {
  value: number;
  unit: string;
  source: string;
  group: string;
}

interface QuotedPoint {
  status: string;
  hub_id: string | null;
  hub_name: string | null;
  nearest_stop_name: string | null;
  nearest_hub_id: string | null;
  distance_to_hub_centre_m: NumberResource | null;
  distance_from_outline_m: NumberResource | null;
}

interface QuotedOption {
  arc_id: string;
  mode: string;
  most_taken: boolean;
  price: NumberResource;
  pt_fare: NumberResource | null;
  bike_price: NumberResource | null;
  bike_legs: NumberResource;
  car_cost: NumberResource | null;
  car_parking_fee: NumberResource | null;
  duration_s: NumberResource;
  transfers: NumberResource;
  flow: NumberResource | null;
  legs: { mode: string; duration_s: NumberResource }[];
}

interface TripQuote {
  status: string;
  from_point: QuotedPoint | null;
  to_point: QuotedPoint | null;
  origin_hub: { hub_id: string; hub_name: string } | null;
  destination_hub: { hub_id: string; hub_name: string } | null;
  min_trip_distance_m: NumberResource | null;
  no_car_option: boolean | null;
  options: QuotedOption[];
}

interface Hub {
  hub_id: string;
  lat: number;
  lon: number;
}

interface PlaceLine {
  name: string;
  kind: string;
  hub_id: string;
  lat: number;
  lon: number;
}

interface RouteOptions {
  bus_shapes: boolean;
  items: { arc_id: string; mode: string; legs: { line_kind: string; geometry: unknown }[] }[];
}

type Request = Parameters<Parameters<typeof test>[2]>[0]['request'];

const at = (point: { lat: number; lon: number }) => `${String(point.lat)},${String(point.lon)}`;

async function hubsOf(request: Request, version: string): Promise<Map<string, Hub>> {
  const answer = await request.get(`/api/v1/instance-versions/${version}/hubs`);
  expect(answer.status()).toBe(200);
  const items = ((await answer.json()) as { items: Hub[] }).items;
  return new Map(items.map((hub) => [hub.hub_id, hub]));
}

async function quote(
  request: Request,
  pricingVersion: string,
  from: string | null,
  to: string | null,
): Promise<TripQuote> {
  const params: Record<string, string> = { pricing_version: pricingVersion };
  if (from !== null) params.from = from;
  if (to !== null) params.to = to;
  const answer = await request.get('/api/v1/trip-quotes', { params });
  expect(answer.status()).toBe(200);
  return (await answer.json()) as TripQuote;
}

/** What a problem answer says: its status, whether it is a problem document, and its code. */
async function problemOf(response: Awaited<ReturnType<Request['get']>>) {
  return {
    status: response.status(),
    problem: (response.headers()['content-type'] ?? '').includes(problemType),
    code: ((await response.json()) as { code?: string }).code,
  };
}

const isNumber = (number: NumberResource | null) => {
  expect(number).toEqual({
    value: expect.any(Number),
    unit: expect.any(String),
    source: expect.any(String),
    group: expect.any(String),
  });
};

test.describe('Trip quotes · API', () => {
  test('Trip quotes · a priced pair carries matched points and options with their price make-up; every no-price case is a 200 with its status', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, QUOTES_DISTANCE_M);
    const { id } = await finishVersion(request, version, 'Baseline');
    const hubs = await hubsOf(request, version);
    const hub = (hubId: string) => {
      const found = hubs.get(hubId);
      if (found === undefined) throw new Error(`no hub ${hubId}`);
      return found;
    };

    // A priced pair of the fake city: both points matched, three modes, one most taken each.
    const priced = await quote(request, id, at(hub('H2')), at(hub('H3')));
    expect(priced.status).toBe('priced');
    expect(priced.no_car_option).toBe(false);
    expect(priced.origin_hub?.hub_id).toBe('H2');
    expect(priced.destination_hub?.hub_id).toBe('H3');
    for (const [point, hubId] of [
      [priced.from_point, 'H2'],
      [priced.to_point, 'H3'],
    ] as const) {
      expect(point).toMatchObject({ status: 'matched', hub_id: hubId });
      expect(point?.nearest_stop_name).toEqual(expect.any(String));
      isNumber(point?.distance_to_hub_centre_m ?? null);
    }
    expect(new Set(priced.options.map((option) => option.mode))).toEqual(
      new Set(['car', 'pt_only', 'pt_bike']),
    );
    for (const mode of ['car', 'pt_only', 'pt_bike']) {
      expect(priced.options.filter((o) => o.mode === mode && o.most_taken)).toHaveLength(1);
    }
    for (const option of priced.options) {
      for (const number of [option.price, option.duration_s, option.transfers, option.bike_legs]) {
        isNumber(number);
      }
      expect(option.price.source).toBe('derived');
      expect(option.duration_s.source).toBe('trip_planner');
      expect(option.legs.length).toBeGreaterThan(0);
    }
    for (const option of priced.options.filter((o) => o.mode === 'pt_bike')) {
      // The bike price and the flow come from the version's solve; the price is fare + legs × bike price.
      expect(option.bike_price?.source).toBe('model');
      expect(option.flow?.source).toBe('model');
      expect(option.price.value).toBeCloseTo(
        (option.pt_fare?.value ?? Number.NaN) +
          option.bike_legs.value * (option.bike_price?.value ?? Number.NaN),
        6,
      );
    }
    for (const option of priced.options.filter((o) => o.mode === 'pt_only')) {
      expect(option.bike_price).toBeNull();
      expect(option.price.value).toBeCloseTo(option.pt_fare?.value ?? Number.NaN, 6);
    }
    for (const option of priced.options.filter((o) => o.mode === 'car')) {
      expect(option.pt_fare).toBeNull();
      expect(option.price.value).toBeCloseTo(
        (option.car_cost?.value ?? Number.NaN) + (option.car_parking_fee?.value ?? Number.NaN),
        6,
      );
    }

    // One point only: its match, no options.
    const one = await quote(request, id, at(hub('H2')), null);
    expect(one.status).toBe('one_point');
    expect(one.from_point).toMatchObject({ status: 'matched', hub_id: 'H2' });
    expect(one.to_point).toBeNull();
    expect(one.options).toEqual([]);

    // Two names of one hub.
    const names = await request.get('/api/v1/place-names', {
      params: { instance_version: version, q: 'Fake bikes H1-' },
    });
    const [first, second] = ((await names.json()) as { items: PlaceLine[] }).items;
    if (first === undefined || second === undefined) throw new Error('hub H1 has two stations');
    expect((await quote(request, id, at(first), at(second))).status).toBe('same_hub');

    // Point B 5.5 km north of the centre: outside the 3 km circle.
    const instance = (await (await request.get(`/api/v1/instance-versions/${version}`)).json()) as {
      parameters: { center_lat: number; center_lon: number; radius_m: number };
    };
    const centre = { lat: instance.parameters.center_lat, lon: instance.parameters.center_lon };
    const outside = await quote(
      request,
      id,
      at(hub('H2')),
      at({ lat: centre.lat + 0.05, lon: centre.lon }),
    );
    expect(outside.status).toBe('outside_zone');
    expect(outside.to_point?.status).toBe('outside_zone');
    expect(outside.options).toEqual([]);

    // Point B 2 km south of the centre: inside the circle, far from every hub outline.
    const nowhere = await quote(
      request,
      id,
      at(hub('H2')),
      at({ lat: centre.lat - 0.018, lon: centre.lon }),
    );
    expect(nowhere.status).toBe('no_hub_here');
    expect(nowhere.to_point?.status).toBe('no_hub_here');
    expect(nowhere.to_point?.nearest_hub_id).toEqual(expect.any(String));
    expect(nowhere.to_point?.distance_from_outline_m?.value).toBeGreaterThan(300);

    // The fake city's pairs closer than the minimum trip distance, removed by the quality check,
    // and without a bike option.
    const short = await quote(request, id, at(hub('H1')), at(hub('H2')));
    expect(short.status).toBe('under_minimum_distance');
    expect(short.min_trip_distance_m?.value).toBe(QUOTES_DISTANCE_M);
    expect(short.options).toEqual([]);

    const removed = await quote(request, id, at(hub('H3')), at(hub('H4')));
    expect(removed.status).toBe('removed_by_quality_check');
    expect(removed.options).toEqual([]);

    const noBike = await quote(request, id, at(hub('H6')), at(hub('H4')));
    expect(noBike.status).toBe('no_bike_option');
    expect(new Set(noBike.options.map((option) => option.mode))).toEqual(
      new Set(['car', 'pt_only']),
    );

    // Quotes read stored data only: with the solver and the trip planner down they still price.
    await control.makeUnavailable('solver', 'e2e: solver down');
    await control.makeUnavailable('trip_planner', 'e2e: trip planner down');
    const stored = await quote(request, id, at(hub('H2')), at(hub('H3')));
    expect(stored.status).toBe('priced');
    expect(stored.options).toEqual(priced.options);
  });

  test('Trip quotes · a pair whose PT + bike query found no route is no_route; a failed car query sets no_car_option', async ({
    request,
    control,
  }) => {
    await control.setPricingModel({
      route_failures: [
        {
          origin_hub: 'H2',
          destination_hub: 'H5',
          query: 'pt_bike',
          kind: 'no_route',
          message: 'no public transport route',
        },
        {
          origin_hub: 'H4',
          destination_hub: 'H5',
          query: 'car',
          kind: 'no_route',
          message: 'no car route',
        },
      ],
    });
    const { version } = await buildFakeInstance(request, control, FAILURES_DISTANCE_M);
    await control.setPricingModel({});
    const { id } = await finishVersion(request, version, 'Baseline');
    const hubs = await hubsOf(request, version);
    const point = (hubId: string) => {
      const found = hubs.get(hubId);
      if (found === undefined) throw new Error(`no hub ${hubId}`);
      return at(found);
    };

    const noRoute = await quote(request, id, point('H2'), point('H5'));
    expect(noRoute.status).toBe('no_route');
    expect(noRoute.origin_hub?.hub_id).toBe('H2');
    expect(noRoute.destination_hub?.hub_id).toBe('H5');

    const noCar = await quote(request, id, point('H4'), point('H5'));
    expect(noCar.no_car_option).toBe(true);
    expect(noCar.options.some((option) => option.mode === 'car')).toBe(false);
    expect(noCar.options.some((option) => option.mode === 'pt_bike')).toBe(true);
  });

  test('Trip quotes · an unknown version is 404, a draft is 404 no_result; no point, a malformed point and an unpriced period are 422', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, QUOTES_DISTANCE_M);
    const { id } = await finishVersion(request, version, 'Baseline');
    const draft = await createPricingVersion(request, version);
    const point = at((await hubsOf(request, version)).get('H2') ?? { lat: 0, lon: 0 });

    expect(
      await problemOf(
        await request.get('/api/v1/trip-quotes', {
          params: { pricing_version: `${version}.Z`, from: point },
        }),
      ),
    ).toEqual({ status: 404, problem: true, code: 'pricing_version_not_found' });
    expect(
      await problemOf(
        await request.get('/api/v1/trip-quotes', {
          params: { pricing_version: draft.id, from: point },
        }),
      ),
    ).toEqual({ status: 404, problem: true, code: 'no_result' });
    expect(
      await problemOf(
        await request.get('/api/v1/trip-quotes', { params: { pricing_version: id } }),
      ),
    ).toEqual({ status: 422, problem: true, code: 'no_point' });
    for (const text of ['abc', '46.2', '91,6']) {
      expect(
        await problemOf(
          await request.get('/api/v1/trip-quotes', { params: { pricing_version: id, from: text } }),
        ),
      ).toEqual({ status: 422, problem: true, code: 'malformed_point' });
    }
    expect(
      await problemOf(
        await request.get('/api/v1/trip-quotes', {
          params: { pricing_version: id, period: 'tue-17', from: point },
        }),
      ),
    ).toEqual({ status: 422, problem: true, code: 'period_not_priced' });
    expect(
      await problemOf(await request.get('/api/v1/trip-quotes', { params: { from: point } })),
    ).toEqual({ status: 422, problem: true, code: 'validation_failed' });
  });

  test('Place names and route options · names match case-free with kind and hub; a pair lists its legs with their line kind; unknown ids are 404', async ({
    request,
    control,
  }) => {
    const { version } = await buildFakeInstance(request, control, QUOTES_DISTANCE_M);

    const typed = await request.get('/api/v1/place-names', {
      params: { instance_version: version, q: 'fake BIKES h3' },
    });
    expect(typed.status()).toBe(200);
    const lines = ((await typed.json()) as { items: PlaceLine[] }).items;
    expect(lines.length).toBeGreaterThan(0);
    for (const line of lines) {
      expect(line).toMatchObject({ kind: 'bike_station', hub_id: 'H3' });
      expect(line.name).toMatch(/^Fake bikes H3-/);
    }
    const tooShort = await request.get('/api/v1/place-names', {
      params: { instance_version: version, q: 'F' },
    });
    expect(await tooShort.json()).toEqual({ items: [] });
    expect(
      await problemOf(
        await request.get('/api/v1/place-names', {
          params: { instance_version: 'nowhere.v1', q: 'Fake' },
        }),
      ),
    ).toEqual({ status: 404, problem: true, code: 'instance_version_not_found' });

    const options = await request.get('/api/v1/route-options', {
      params: { instance_version: version, origin_hub: 'H2', destination_hub: 'H3' },
    });
    expect(options.status()).toBe(200);
    const listed = (await options.json()) as RouteOptions;
    expect(typeof listed.bus_shapes).toBe('boolean');
    expect(new Set(listed.items.map((item) => item.mode))).toEqual(
      new Set(['car', 'pt_only', 'pt_bike']),
    );
    for (const item of listed.items) {
      expect(item.legs.length).toBeGreaterThan(0);
      for (const leg of item.legs) {
        expect(['street_path', 'timetable_shape', 'straight_line']).toContain(leg.line_kind);
      }
    }

    expect(
      await problemOf(
        await request.get('/api/v1/route-options', {
          params: { instance_version: version, origin_hub: 'H2', destination_hub: 'H99' },
        }),
      ),
    ).toEqual({ status: 404, problem: true, code: 'hub_pair_not_found' });
    expect(
      await problemOf(
        await request.get('/api/v1/route-options', {
          params: { instance_version: 'nowhere.v1', origin_hub: 'H2', destination_hub: 'H3' },
        }),
      ),
    ).toEqual({ status: 404, problem: true, code: 'instance_version_not_found' });
    expect(
      await problemOf(
        await request.get('/api/v1/route-options', {
          params: {
            instance_version: version,
            period: 'tue-17',
            origin_hub: 'H2',
            destination_hub: 'H3',
          },
        }),
      ),
    ).toEqual({ status: 422, problem: true, code: 'unknown_period' });
  });
});
