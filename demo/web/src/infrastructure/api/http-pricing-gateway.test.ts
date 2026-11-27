import { describe, expect, it, vi } from 'vitest';
import { ApiProblemError } from '../../application/errors';
import { HttpPricingGateway } from './http-pricing-gateway';

const wire = {
  id: 'geneva-3km.v1.B',
  instance_version_id: 'geneva-3km.v1',
  letter: 'B',
  name: 'Version B',
  status: 'draft',
  state: 'draft',
  based_on_id: 'geneva-3km.v1.A',
  run_id: 'run-9',
  kept_from: { id: 'geneva-3km.v1.A', letter: 'A' },
  last_duration_s: 404.5,
  created_at: '2026-11-27T10:00:00Z',
  sealed_at: null,
  goals: {
    cost_bike_chf: 0.6,
    lowest_price_chf: 0.6,
    ridership_weight: 8,
    station_balance_weight: 0.5,
    pt_fare_chf: 2,
    car_parking_fee_chf: 2.8,
    max_displayed_options: 10,
    flat_price_kind: 'per_ride',
    flat_price_per_ride_chf: 1,
  },
  periods: [],
  rules: [
    {
      rule: 'options_shown_at_least_1',
      field: 'max_displayed_options',
      passed: true,
      message: 'ok',
    },
  ],
};

function answering(status: number, body: unknown) {
  return vi.fn<typeof fetch>(() =>
    Promise.resolve(new Response(body === undefined ? null : JSON.stringify(body), { status })),
  );
}

describe('HttpPricingGateway', () => {
  it('maps a pricing version, its kept-from version, its rules and its last duration', async () => {
    const fetchImpl = answering(200, wire);

    const version = await new HttpPricingGateway(fetchImpl).get('geneva-3km.v1.B');

    expect(fetchImpl.mock.calls[0]?.[0]).toBe('/api/v1/pricing-versions/geneva-3km.v1.B');
    expect(version).toMatchObject({
      id: 'geneva-3km.v1.B',
      instanceVersionId: 'geneva-3km.v1',
      keptFrom: { id: 'geneva-3km.v1.A', letter: 'A' },
      lastDurationS: 404.5,
      basedOnId: 'geneva-3km.v1.A',
      runId: 'run-9',
      state: 'draft',
    });
    expect(version?.goals.max_displayed_options).toBe(10);
    expect(version?.goals).not.toHaveProperty('flat_price_kind');
    expect(version?.rules).toEqual([
      {
        rule: 'options_shown_at_least_1',
        field: 'max_displayed_options',
        passed: true,
        message: 'ok',
      },
    ]);
  });

  it('answers null for a 404', async () => {
    expect(await new HttpPricingGateway(answering(404, {})).get('x.v1.Q')).toBeNull();
  });

  it('lists the pricing versions of an instance version', async () => {
    const fetchImpl = answering(200, { items: [wire] });

    const versions = await new HttpPricingGateway(fetchImpl).list('geneva-3km.v1');

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(
      '/api/v1/instance-versions/geneva-3km.v1/pricing-versions',
    );
    expect(versions.map((version) => version.letter)).toEqual(['B']);
  });

  it('posts a new draft with an empty body', async () => {
    const fetchImpl = answering(201, wire);

    await new HttpPricingGateway(fetchImpl).create('geneva-3km.v1');

    const [path, init] = fetchImpl.mock.calls[0] ?? [];
    expect(path).toBe('/api/v1/instance-versions/geneva-3km.v1/pricing-versions');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe('{}');
  });

  it('posts a duplicate with the version it is based on', async () => {
    const fetchImpl = answering(201, wire);

    await new HttpPricingGateway(fetchImpl).create('geneva-3km.v1', 'geneva-3km.v1.A');

    expect(JSON.parse(fetchImpl.mock.calls[0]?.[1]?.body as string)).toEqual({
      based_on: 'geneva-3km.v1.A',
    });
  });

  it('patches the goals and the name as sent', async () => {
    const fetchImpl = answering(200, wire);

    await new HttpPricingGateway(fetchImpl).patch('geneva-3km.v1.B', {
      lowest_price_chf: 0.4,
      name: 'Cheaper',
    });

    const [path, init] = fetchImpl.mock.calls[0] ?? [];
    expect(path).toBe('/api/v1/pricing-versions/geneva-3km.v1.B');
    expect(init?.method).toBe('PATCH');
    expect(JSON.parse(init?.body as string)).toEqual({ lowest_price_chf: 0.4, name: 'Cheaper' });
  });

  it('deletes a draft', async () => {
    const fetchImpl = answering(204, undefined);

    await new HttpPricingGateway(fetchImpl).discard('geneva-3km.v1.B');

    expect(fetchImpl.mock.calls[0]?.[1]?.method).toBe('DELETE');
  });

  it('queues the run, or reports a refusal with its reason', async () => {
    expect(await new HttpPricingGateway(answering(202, { id: 'run-9' })).run('x.v1.B')).toEqual({
      kind: 'queued',
      runId: 'run-9',
    });
    const refused = answering(503, {
      code: 'component_unavailable',
      title: 'A component is missing',
      detail: 'The solver is size-limited.',
    });
    expect(await new HttpPricingGateway(refused).run('x.v1.B')).toEqual({
      kind: 'refused',
      detail: 'The solver is size-limited.',
    });
    const broken = answering(409, {
      code: 'rule_broken',
      title: 'A rule is broken',
      detail: 'Options shown per hub pair must be at least 1: now 0',
    });
    expect((await new HttpPricingGateway(broken).run('x.v1.B')).kind).toBe('refused');
  });

  it('posts a simulation run, or reports a refusal with its reason', async () => {
    const fetchImpl = answering(202, { id: 'run-sim' });
    expect(await new HttpPricingGateway(fetchImpl).simulate('x.v1.B')).toEqual({
      kind: 'queued',
      runId: 'run-sim',
    });
    const [path, init] = fetchImpl.mock.calls[0] ?? [];
    expect(path).toBe('/api/v1/pricing-versions/x.v1.B/simulations');
    expect(init?.method).toBe('POST');

    for (const [status, code] of [
      [409, 'run_active'],
      [409, 'simulation_current'],
      [503, 'component_unavailable'],
    ] as const) {
      const refused = answering(status, { code, title: 'No', detail: `Because ${code}.` });
      expect(await new HttpPricingGateway(refused).simulate('x.v1.B')).toEqual({
        kind: 'refused',
        detail: `Because ${code}.`,
      });
    }
    const broken = answering(500, { code: 'boom', title: 'Boom', detail: 'It broke.' });
    await expect(new HttpPricingGateway(broken).simulate('x.v1.B')).rejects.toMatchObject({
      code: 'boom',
    });
  });

  it('deletes a version: gone on 204, or the refusal the 409 code names', async () => {
    const fetchImpl = answering(204, undefined);
    expect(await new HttpPricingGateway(fetchImpl).remove('x.v1.B')).toEqual({ kind: 'deleted' });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe('/api/v1/pricing-versions/x.v1.B');
    expect(fetchImpl.mock.calls[0]?.[1]?.method).toBe('DELETE');

    for (const code of ['run_active', 'is_showcase'] as const) {
      const refused = answering(409, { code, title: 'No', detail: 'Refused.' });
      expect(await new HttpPricingGateway(refused).remove('x.v1.B')).toEqual({ kind: code });
    }
    const other = answering(409, { code: 'other', title: 'No', detail: 'Refused.' });
    await expect(new HttpPricingGateway(other).remove('x.v1.B')).rejects.toMatchObject({
      code: 'other',
    });
    const missing = answering(404, { code: 'not_found', title: 'None', detail: 'No version.' });
    await expect(new HttpPricingGateway(missing).remove('x.v1.B')).rejects.toMatchObject({
      code: 'not_found',
    });
  });

  it('throws the problem document for any other answer, and for an unreachable API', async () => {
    const problem = answering(500, { code: 'boom', title: 'Boom', detail: 'It broke.' });
    await expect(new HttpPricingGateway(problem).create('x.v1')).rejects.toMatchObject({
      code: 'boom',
    });
    const down = vi.fn<typeof fetch>(() => Promise.reject(new Error('offline')));
    const error = await new HttpPricingGateway(down).list('x.v1').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiProblemError);
    expect(error).toMatchObject({ code: 'api_unreachable' });
  });

  describe('result', () => {
    const num = (value: number, source: string, unit = 'travellers') => ({
      value,
      unit,
      source,
      group: 'headline',
    });
    const simulation = (scheme: string, car: number) => ({
      price_scheme: scheme,
      rule_id: 'balanced-score',
      rule_version: 1,
      rule_current: true,
      rule_parameters: { price_weight: 0.5, time_weight: 0.5 },
      created_at: '2026-11-10T09:00:00Z',
      bike_rides: num(40, 'simulation', 'bike_rides'),
      revenue: num(50, 'simulation', 'chf'),
      cost: num(20, 'simulation', 'chf'),
      travellers: {
        pt_bike: num(10, 'simulation'),
        pt_only: num(20, 'simulation'),
        car: num(car, 'simulation'),
      },
      displaced: num(7, 'simulation'),
      unserved: num(2, 'simulation'),
    });
    const body = {
      pricing_version_id: 'x.v1.B',
      period_id: 'monday-08',
      headline: { profit: num(4175, 'derived', 'chf') },
      goals: [
        {
          name: 'ridership',
          model: num(12281, 'model'),
          model_prices: num(12, 'simulation'),
          flat: num(10, 'simulation'),
          change: num(2, 'simulation'),
        },
        { name: 'profit', model: null, model_prices: null, flat: null, change: null },
      ],
      simulations: [simulation('model_prices', 30), simulation('flat', 40)],
      model_split: {
        travellers_car: num(31, 'model'),
        travellers_pt_only: num(21, 'model'),
        travellers_pt_bike: num(11, 'model'),
      },
      advanced: {
        solver_status_name: 'TIME_LIMIT',
        numbers: { gap_pct: num(1.5, 'model', 'percent') },
      },
      coefficients: { ASC_PT: num(-0.756, 'input', 'coefficient'), B_TIME: null },
      provenance: {
        package_version: '0.4.2',
        package_commit: null,
        gurobi_version: '12.0.1',
        licence_kind: 'limited',
        demonstrator_version: '0.1.0',
        timetable_operator: 'tpg',
        timetable_valid_from: '2024-12-15',
        timetable_valid_to: '2025-12-13',
        routing_date: '2025-03-10',
        routing_time: '08:30:00',
        routing_date_provisional: true,
        bike_stations_source_url: 'https://example.org/gbfs.json',
        bike_stations_fetched_at: '2026-11-10T00:00:00Z',
        simulations: [
          {
            price_scheme: 'flat',
            rule_id: 'balanced-score',
            rule_version: 1,
            created_at: '2026-11-10T09:00:00Z',
          },
        ],
      },
    };

    it('reads the route and maps the simulations, the split, the goals and the headline', async () => {
      const fetchImpl = answering(200, body);

      const result = await new HttpPricingGateway(fetchImpl).result('x.v1.B');

      expect(fetchImpl.mock.calls[0]?.[0]).toBe('/api/v1/pricing-versions/x.v1.B/result');
      expect(result?.pricingVersionId).toBe('x.v1.B');
      expect(result?.periodId).toBe('monday-08');
      expect(result?.simulations.modelPrices).toEqual({
        ruleId: 'balanced-score',
        ruleVersion: 1,
        ruleCurrent: true,
        ruleParameters: { price_weight: 0.5, time_weight: 0.5 },
        travellers: { car: 30, ptOnly: 20, ptBike: 10 },
        bikeRides: num(40, 'simulation', 'bike_rides'),
        revenue: num(50, 'simulation', 'chf'),
        cost: num(20, 'simulation', 'chf'),
        displaced: 7,
        unserved: 2,
        createdAt: '2026-11-10T09:00:00Z',
      });
      expect(result?.simulations.flat.travellers.car).toBe(40);
      expect(result?.modelSplit).toEqual({ car: 31, ptOnly: 21, ptBike: 11 });
      expect(result?.goals.ridership.model?.source).toBe('model');
      expect(result?.goals.ridership.change?.value).toBe(2);
      expect(result?.goals.profit.modelPrices).toBeNull();
      expect(result?.goals.cost.flat).toBeNull();
      expect(result?.headline.profit?.value).toBe(4175);
      expect(result?.headline).not.toHaveProperty('revenue');
    });

    it('maps the solver numbers, the coefficients and the provenance', async () => {
      const result = await new HttpPricingGateway(answering(200, body)).result('x.v1.B');

      expect(result?.advanced.solverStatusName).toBe('TIME_LIMIT');
      expect(result?.advanced.numbers.gap_pct?.value).toBe(1.5);
      expect(result?.coefficients?.ASC_PT?.value).toBe(-0.756);
      expect(result?.coefficients?.B_TIME).toBeNull();
      expect(result?.provenance).toEqual({
        packageVersion: '0.4.2',
        packageCommit: null,
        gurobiVersion: '12.0.1',
        licenceKind: 'limited',
        demonstratorVersion: '0.1.0',
        timetableOperator: 'tpg',
        timetableValidFrom: '2024-12-15',
        timetableValidTo: '2025-12-13',
        routingDate: '2025-03-10',
        routingTime: '08:30:00',
        routingDateProvisional: true,
        bikeStationsSourceUrl: 'https://example.org/gbfs.json',
        bikeStationsFetchedAt: '2026-11-10T00:00:00Z',
        simulations: [
          {
            priceScheme: 'flat',
            ruleId: 'balanced-score',
            ruleVersion: 1,
            createdAt: '2026-11-10T09:00:00Z',
          },
        ],
      });
    });

    it('has no coefficients when the API sends none', async () => {
      const found = await new HttpPricingGateway(
        answering(200, { ...body, coefficients: null }),
      ).result('x.v1.B');

      expect(found?.coefficients).toBeNull();
    });

    it('has no model split when one mode is absent', async () => {
      const partial = { ...body, model_split: { travellers_car: num(31, 'model') } };
      expect(
        (await new HttpPricingGateway(answering(200, partial)).result('x.v1.B'))?.modelSplit,
      ).toBeNull();
    });

    it('answers null for a 404 and throws for another status', async () => {
      const none = answering(404, { code: 'no_result', title: 'No result', detail: 'x' });
      expect(await new HttpPricingGateway(none).result('x.v1.B')).toBeNull();
      const broken = answering(500, { code: 'boom', title: 'Boom', detail: 'It broke.' });
      await expect(new HttpPricingGateway(broken).result('x.v1.B')).rejects.toMatchObject({
        code: 'boom',
      });
    });
  });

  describe('hub-pair results and hub results', () => {
    const num = (value: number, source: string, unit = 'travellers') => ({
      value,
      unit,
      source,
      group: 'advanced',
    });
    const leg = (mode: string, extra: object) => ({
      mode,
      duration_s: 300,
      distance_m: 900,
      line_kind: 'street',
      ...extra,
    });
    const pair = {
      origin_hub: 'H4',
      destination_hub: 'H9',
      mean_bike_price: num(0.95, 'derived', 'chf'),
      min_bike_price: num(0.6, 'model', 'chf'),
      max_bike_price: num(1.4, 'model', 'chf'),
      travellers: { car: num(310, 'model'), pt_only: num(220, 'model'), pt_bike: num(42, 'model') },
      options: [
        {
          arc_id: 'a',
          mode: 'pt_bike',
          legs: [
            leg('TRAM', { line: '12', from_place: 'Plainpalais', to_place: 'Rive' }),
            leg('BICYCLE', { line: null, from_place: null, to_place: null }),
            leg('FOOT', {}),
          ],
          duration: num(780, 'trip_planner', 's'),
          bike_legs: num(1, 'input', 'bike_legs'),
          bike_price: num(1.4, 'model', 'chf'),
          riders: null,
        },
      ],
    };

    it('reads the hub-pair route and maps the pair, its options and its legs', async () => {
      const fetchImpl = answering(200, { items: [pair] });

      const found = await new HttpPricingGateway(fetchImpl).hubPairResults('x.v1.B');

      expect(fetchImpl.mock.calls[0]?.[0]).toBe('/api/v1/pricing-versions/x.v1.B/hub-pair-results');
      const [first] = found ?? [];
      expect(first).toMatchObject({ originHub: 'H4', destinationHub: 'H9' });
      expect(first?.meanBikePrice?.value).toBe(0.95);
      expect(first?.travellers).toEqual({ car: 310, ptOnly: 220, ptBike: 42 });
      const option = first?.options[0];
      expect(option?.legs[0]).toEqual({
        mode: 'TRAM',
        line: '12',
        fromPlace: 'Plainpalais',
        toPlace: 'Rive',
        durationS: 300,
      });
      expect(option?.legs[1]).toMatchObject({ line: null, fromPlace: null });
      expect(option?.legs[2]).toMatchObject({ line: null, fromPlace: null, toPlace: null });
      expect(option?.bikePrice?.value).toBe(1.4);
      expect(option?.riders).toBeNull();
    });

    it('maps a pair with nothing offered', async () => {
      const bare = { ...pair, mean_bike_price: null, min_bike_price: null, max_bike_price: null };
      const found = await new HttpPricingGateway(answering(200, { items: [bare] })).hubPairResults(
        'x.v1.B',
      );
      expect(found?.[0]?.minBikePrice).toBeNull();
    });

    it('reads the hub route', async () => {
      const hub = {
        hub_id: 'H4',
        label: 'H4 Plainpalais',
        lat: 46.2,
        lon: 6.1,
        rides_starting: num(42, 'derived', 'bike_rides'),
        rides_ending: num(10, 'derived', 'bike_rides'),
        mean_bike_price: null,
      };
      const fetchImpl = answering(200, { items: [hub] });

      const found = await new HttpPricingGateway(fetchImpl).hubResults('x.v1.B');

      expect(fetchImpl.mock.calls[0]?.[0]).toBe('/api/v1/pricing-versions/x.v1.B/hub-results');
      expect(found).toEqual([
        {
          hubId: 'H4',
          label: 'H4 Plainpalais',
          lat: 46.2,
          lon: 6.1,
          ridesStarting: num(42, 'derived', 'bike_rides'),
          ridesEnding: num(10, 'derived', 'bike_rides'),
          meanBikePrice: null,
        },
      ]);
    });

    it('answers null for a 404 and throws for another status', async () => {
      const none = answering(404, { code: 'no_result', title: 'No result', detail: 'x' });
      expect(await new HttpPricingGateway(none).hubPairResults('x.v1.B')).toBeNull();
      expect(await new HttpPricingGateway(none).hubResults('x.v1.B')).toBeNull();
      const broken = answering(500, { code: 'boom', title: 'Boom', detail: 'It broke.' });
      await expect(new HttpPricingGateway(broken).hubResults('x.v1.B')).rejects.toMatchObject({
        code: 'boom',
      });
      await expect(new HttpPricingGateway(broken).hubPairResults('x.v1.B')).rejects.toMatchObject({
        code: 'boom',
      });
    });
  });

  describe('simulations', () => {
    it('reads every stored simulation with its rule parameters', async () => {
      const item = {
        simulation_key: 'k',
        period_id: 'monday-08',
        price_scheme: 'flat',
        rule_id: 'balanced-score',
        rule_version: 0,
        rule_parameters: { price_weight: 1, time_weight: 0 },
        rule_current: false,
        created_at: '2026-11-09T09:00:00Z',
      };
      const fetchImpl = answering(200, { items: [item] });

      const found = await new HttpPricingGateway(fetchImpl).simulations('x.v1.B');

      expect(fetchImpl.mock.calls[0]?.[0]).toBe('/api/v1/pricing-versions/x.v1.B/simulations');
      expect(found).toEqual([
        {
          periodId: 'monday-08',
          priceScheme: 'flat',
          ruleId: 'balanced-score',
          ruleVersion: 0,
          ruleParameters: { price_weight: 1, time_weight: 0 },
          ruleCurrent: false,
          createdAt: '2026-11-09T09:00:00Z',
        },
      ]);
    });

    it('answers null for a 404 and throws for another status', async () => {
      const none = answering(404, { code: 'pricing_version_not_found', title: 'x', detail: 'x' });
      expect(await new HttpPricingGateway(none).simulations('x.v1.B')).toBeNull();
      const broken = answering(500, { code: 'boom', title: 'Boom', detail: 'It broke.' });
      await expect(new HttpPricingGateway(broken).simulations('x.v1.B')).rejects.toMatchObject({
        code: 'boom',
      });
    });
  });
});
