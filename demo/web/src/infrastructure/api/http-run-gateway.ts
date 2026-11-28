import { ApiProblemError } from '../../application/errors';
import type { RunGateway } from '../../application/ports/run-gateway';
import type { Run } from '../../domain/run';
import type { components } from './generated/schema';

type Schemas = components['schemas'];

const runsPath = '/api/v1/runs';

const instant = (value: string | null): Date | null => (value === null ? null : new Date(value));

function toRun(wire: Schemas['RunResource']): Run {
  return {
    id: wire.id,
    kind: wire.kind,
    subject: { type: wire.subject.type, id: wire.subject.id },
    state: wire.state,
    attempt: wire.attempt,
    queuedAt: new Date(wire.queued_at),
    startedAt: instant(wire.started_at),
    finishedAt: instant(wire.finished_at),
    serverTime: new Date(wire.server_time),
    queuePosition: wire.queue_position,
    runner: { alive: wire.runner.alive, lastHeartbeatAt: instant(wire.runner.last_heartbeat_at) },
    steps: wire.steps.map((step) => ({
      step: step.step,
      number: step.number,
      state: step.state,
      startedAt: instant(step.started_at),
      finishedAt: instant(step.finished_at),
      counts: step.counts,
      progress:
        step.progress === null ? null : { done: step.progress.done, total: step.progress.total },
      lastDurationS: step.last_duration_s,
    })),
    failure:
      wire.failure === null
        ? null
        : { step: wire.failure.step, code: wire.failure.code, reason: wire.failure.reason },
  };
}

function problemOf(body: unknown): Schemas['ProblemDetails'] | null {
  if (typeof body !== 'object' || body === null) return null;
  const candidate = body as Partial<Schemas['ProblemDetails']>;
  return typeof candidate.code === 'string' && typeof candidate.title === 'string'
    ? (candidate as Schemas['ProblemDetails'])
    : null;
}

export class HttpRunGateway implements RunGateway {
  private readonly fetchImpl: typeof fetch;

  constructor(fetchImpl: typeof fetch) {
    this.fetchImpl = fetchImpl;
  }

  async get(id: string): Promise<Run> {
    return toRun(await this.call<Schemas['RunResource']>(`${runsPath}/${encodeURIComponent(id)}`));
  }

  async listActive(): Promise<Run[]> {
    const body = await this.call<Schemas['RunList']>(`${runsPath}?state=queued,running`);
    return body.items.map(toRun);
  }

  async cancel(id: string): Promise<Run> {
    const path = `${runsPath}/${encodeURIComponent(id)}/cancellation`;
    return toRun(await this.call<Schemas['RunResource']>(path, 'PUT'));
  }

  /** A request whose 200 and 202 answers are JSON; anything else is a typed error. */
  private async call<T>(path: string, method?: 'PUT'): Promise<T> {
    let response: Response;
    try {
      response = await this.fetchImpl(
        path,
        method === undefined
          ? { headers: { Accept: 'application/json' } }
          : { method, headers: { Accept: 'application/json' } },
      );
    } catch (cause) {
      throw new ApiProblemError({
        code: 'api_unreachable',
        title: 'The API could not be reached',
        detail: cause instanceof Error ? cause.message : String(cause),
      });
    }
    let body: unknown;
    try {
      body = (await response.json()) as unknown;
    } catch {
      body = undefined;
    }
    if (response.status === 200 || response.status === 202) {
      if (body === undefined) {
        throw new ApiProblemError({
          code: 'unexpected_response',
          title: 'The API answer could not be read',
          detail: 'The answer is not JSON.',
        });
      }
      return body as T;
    }
    const problem = problemOf(body);
    if (problem !== null) {
      throw new ApiProblemError({
        code: problem.code,
        title: problem.title,
        detail: problem.detail,
      });
    }
    throw new ApiProblemError({
      code: 'unexpected_response',
      title: `The API answered with status ${String(response.status)}`,
      detail: `${path} could not be read.`,
    });
  }
}
