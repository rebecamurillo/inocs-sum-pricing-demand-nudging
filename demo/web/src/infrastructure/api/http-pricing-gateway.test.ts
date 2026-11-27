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
        travellers: { car: 30, ptOnly: 20, ptBike: 10 },
        displaced: 7,
        unserved: 2,
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
});
