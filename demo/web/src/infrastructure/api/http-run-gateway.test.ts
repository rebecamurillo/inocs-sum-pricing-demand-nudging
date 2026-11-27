import { describe, expect, it, vi } from 'vitest';
import { ApiProblemError } from '../../application/errors';
import { HttpRunGateway } from './http-run-gateway';

const runWire = {
  id: 'run-2',
  kind: 'build',
  subject: { type: 'instance_version', id: 'geneva-3km.v2' },
  state: 'running',
  attempt: 2,
  queued_at: '2026-11-27T09:59:00Z',
  started_at: '2026-11-27T10:00:00Z',
  finished_at: null,
  server_time: '2026-11-27T10:04:12Z',
  queue_position: null,
  failure_pct: null,
  runner: { alive: false, last_heartbeat_at: '2026-11-27T10:03:00Z' },
  failure: null,
  steps: [
    {
      step: 'routes',
      number: 3,
      state: 'running',
      started_at: '2026-11-27T10:01:00Z',
      finished_at: null,
      period: 'p',
      reason: null,
      last_duration_s: 61,
      counts: { queries_failed: 2 },
      progress: { done: 12, total: 48 },
    },
    {
      step: 'travellers_and_bikes',
      number: 4,
      state: 'failed',
      started_at: null,
      finished_at: '2026-11-27T10:02:00Z',
      period: null,
      reason: 'boom',
      last_duration_s: null,
      counts: {},
      progress: null,
    },
  ],
};

function answering(answer: Response | Error) {
  const fetchFake = vi.fn<typeof fetch>(() =>
    answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer),
  );
  return { gateway: new HttpRunGateway(fetchFake), fetchFake };
}

describe('HttpRunGateway', () => {
  it('maps a run with its steps, its runner and its clock', async () => {
    const { gateway, fetchFake } = answering(Response.json(runWire));

    const run = await gateway.get('run-2');

    expect(fetchFake).toHaveBeenCalledWith('/api/v1/runs/run-2', {
      headers: { Accept: 'application/json' },
    });
    expect(run).toMatchObject({
      id: 'run-2',
      kind: 'build',
      subject: { type: 'instance_version', id: 'geneva-3km.v2' },
      state: 'running',
      attempt: 2,
      queuePosition: null,
      finishedAt: null,
      failure: null,
      runner: { alive: false },
    });
    expect(run.startedAt?.toISOString()).toBe('2026-11-27T10:00:00.000Z');
    expect(run.serverTime.toISOString()).toBe('2026-11-27T10:04:12.000Z');
    expect(run.runner.lastHeartbeatAt?.toISOString()).toBe('2026-11-27T10:03:00.000Z');
    expect(run.steps[0]).toMatchObject({
      step: 'routes',
      number: 3,
      state: 'running',
      counts: { queries_failed: 2 },
      progress: { done: 12, total: 48 },
      finishedAt: null,
    });
    expect(run.steps[1]?.finishedAt?.toISOString()).toBe('2026-11-27T10:02:00.000Z');
  });

  it('maps a failure and a queue position', async () => {
    const { gateway } = answering(
      Response.json({
        ...runWire,
        state: 'queued',
        queue_position: 2,
        started_at: null,
        runner: { alive: true, last_heartbeat_at: null },
        failure: { step: 'routes', code: 'stage_error', reason: 'Boom: it broke' },
      }),
    );

    expect(await gateway.get('run-2')).toMatchObject({
      queuePosition: 2,
      startedAt: null,
      runner: { alive: true, lastHeartbeatAt: null },
      failure: { step: 'routes', code: 'stage_error', reason: 'Boom: it broke' },
    });
  });

  it('lists the queued and running runs', async () => {
    const { gateway, fetchFake } = answering(Response.json({ items: [runWire] }));

    expect((await gateway.listActive()).map((run) => run.id)).toEqual(['run-2']);
    expect(fetchFake.mock.calls[0]?.[0]).toBe('/api/v1/runs?state=queued,running');
  });

  it('cancels with a PUT and takes a 200 and a 202 for the run', async () => {
    for (const status of [200, 202]) {
      const { gateway, fetchFake } = answering(Response.json(runWire, { status }));

      expect((await gateway.cancel('run-2')).id).toBe('run-2');
      expect(fetchFake).toHaveBeenCalledWith('/api/v1/runs/run-2/cancellation', {
        method: 'PUT',
        headers: { Accept: 'application/json' },
      });
    }
  });

  it('turns an unreachable API and a refusal into typed errors', async () => {
    const down = answering(new TypeError('network'));
    await expect(down.gateway.get('run-2')).rejects.toMatchObject({ code: 'api_unreachable' });

    const refused = answering(
      Response.json(
        { code: 'run_not_found', title: 'No such run', detail: 'run-9' },
        { status: 404 },
      ),
    );
    const error: unknown = await refused.gateway.cancel('run-9').catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiProblemError);
    expect(error).toMatchObject({ code: 'run_not_found' });

    const broken = answering(new Response('not json', { status: 200 }));
    await expect(broken.gateway.listActive()).rejects.toMatchObject({
      code: 'unexpected_response',
    });
  });
});
