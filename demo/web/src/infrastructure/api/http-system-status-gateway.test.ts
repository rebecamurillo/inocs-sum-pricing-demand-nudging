import { describe, expect, it, vi } from 'vitest';
import { ApiProblemError } from '../../application/errors';
import { HttpSystemStatusGateway } from './http-system-status-gateway';

const wireStatus = {
  components: [
    { name: 'storage', state: 'available', reason: null },
    { name: 'runner', state: 'available', reason: null },
    { name: 'solver', state: 'limited', reason: 'Size-limited Gurobi licence.' },
    { name: 'package', state: 'available', reason: null },
    { name: 'trip_planner', state: 'unavailable', reason: 'No answer.' },
  ],
  can_build_instances: {
    allowed: false,
    reasons: [{ component: 'trip_planner', reason: 'No answer.' }],
  },
  can_run_pricing: {
    allowed: false,
    reasons: [{ component: 'solver', reason: 'Size-limited Gurobi licence.' }],
  },
  can_simulate: { allowed: true, reasons: [] },
};

function gatewayAnswering(response: Response | Error) {
  const fetchFake = vi.fn<typeof fetch>(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  return { gateway: new HttpSystemStatusGateway(fetchFake), fetchFake };
}

async function failureOf(promise: Promise<unknown>): Promise<ApiProblemError> {
  const error = await promise.then(
    () => undefined,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiProblemError);
  return error as ApiProblemError;
}

describe('HttpSystemStatusGateway', () => {
  it('reads the system status from the same origin under /api', async () => {
    const { gateway, fetchFake } = gatewayAnswering(Response.json(wireStatus));

    await gateway.load();

    expect(fetchFake).toHaveBeenCalledOnce();
    expect(fetchFake.mock.calls[0]?.[0]).toBe('/api/v1/system-status');
  });

  it('maps the wire shape to the domain type', async () => {
    const { gateway } = gatewayAnswering(Response.json(wireStatus));

    await expect(gateway.load()).resolves.toEqual({
      components: [
        { name: 'storage', state: 'available', reason: null },
        { name: 'runner', state: 'available', reason: null },
        { name: 'solver', state: 'limited', reason: 'Size-limited Gurobi licence.' },
        { name: 'package', state: 'available', reason: null },
        { name: 'tripPlanner', state: 'unavailable', reason: 'No answer.' },
      ],
      canBuildInstances: {
        allowed: false,
        reasons: [{ component: 'tripPlanner', reason: 'No answer.' }],
      },
      canRunPricing: {
        allowed: false,
        reasons: [{ component: 'solver', reason: 'Size-limited Gurobi licence.' }],
      },
      canSimulate: { allowed: true, reasons: [] },
    });
  });

  it('turns a problem document into an error carrying its code, title and detail', async () => {
    const problem = {
      type: 'https://sum-project.eu/problems/component-unavailable',
      title: 'The trip planner is not reachable',
      status: 503,
      detail: 'No answer within 2 s.',
      code: 'component_unavailable',
    };
    const { gateway } = gatewayAnswering(
      Response.json(problem, {
        status: 503,
        headers: { 'Content-Type': 'application/problem+json' },
      }),
    );

    const error = await failureOf(gateway.load());

    expect(error.code).toBe('component_unavailable');
    expect(error.title).toBe('The trip planner is not reachable');
    expect(error.detail).toBe('No answer within 2 s.');
  });

  it('reports the status when an error answer is not a problem document', async () => {
    const { gateway } = gatewayAnswering(new Response('<html>Bad gateway</html>', { status: 502 }));

    const error = await failureOf(gateway.load());

    expect(error.code).toBe('unexpected_response');
    expect(error.title).toBe('The API answered with status 502');
  });

  it('reports an error answer whose JSON lacks the problem fields', async () => {
    const { gateway } = gatewayAnswering(Response.json({ message: 'nope' }, { status: 500 }));

    const error = await failureOf(gateway.load());

    expect(error.code).toBe('unexpected_response');
  });

  it('reports a JSON null error body', async () => {
    const { gateway } = gatewayAnswering(Response.json(null, { status: 500 }));

    const error = await failureOf(gateway.load());

    expect(error.code).toBe('unexpected_response');
  });

  it('reports a success answer that is not JSON', async () => {
    const { gateway } = gatewayAnswering(new Response('not json', { status: 200 }));

    const error = await failureOf(gateway.load());

    expect(error.code).toBe('unexpected_response');
    expect(error.detail).toBe('The answer is not JSON.');
  });

  it('turns a network failure into an error carrying the reason', async () => {
    const { gateway } = gatewayAnswering(new TypeError('Failed to fetch'));

    const error = await failureOf(gateway.load());

    expect(error.code).toBe('api_unreachable');
    expect(error.title).toBe('The API could not be reached');
    expect(error.detail).toBe('Failed to fetch');
  });

  it('turns a rejection that is not an Error into an error carrying its text', async () => {
    // A rejection that is not an Error is legal JavaScript, and the adapter must survive it.
    // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
    const fetchFake = vi.fn<typeof fetch>(() => Promise.reject('offline'));
    const gateway = new HttpSystemStatusGateway(fetchFake);

    const error = await failureOf(gateway.load());

    expect(error.detail).toBe('offline');
  });
});
