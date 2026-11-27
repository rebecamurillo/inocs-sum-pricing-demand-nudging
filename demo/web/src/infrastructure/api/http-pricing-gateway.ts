import { ApiProblemError } from '../../application/errors';
import type { PricingGateway, PricingRunQueued } from '../../application/ports/pricing-gateway';
import {
  PRICING_GOAL_NAMES,
  type PricingChanges,
  type PricingGoals,
  type PricingVersion,
} from '../../domain/pricing-version';
import type { components } from './generated/schema';

type Schemas = components['schemas'];

const apiRoot = '/api/v1';

function toGoals(wire: Schemas['PricingGoalsResource']): PricingGoals {
  return Object.fromEntries(PRICING_GOAL_NAMES.map((name) => [name, wire[name]])) as PricingGoals;
}

function toVersion(wire: Schemas['PricingVersionResource']): PricingVersion {
  return {
    id: wire.id,
    instanceVersionId: wire.instance_version_id,
    letter: wire.letter,
    name: wire.name,
    status: wire.status,
    state: wire.state,
    keptFrom:
      wire.kept_from === null ? null : { id: wire.kept_from.id, letter: wire.kept_from.letter },
    goals: toGoals(wire.goals),
    rules: wire.rules.map((rule) => ({
      rule: rule.rule,
      field: rule.field,
      passed: rule.passed,
      message: rule.message,
    })),
    lastDurationS: wire.last_duration_s,
  };
}

function problemOf(body: unknown): Schemas['ProblemDetails'] | null {
  if (typeof body !== 'object' || body === null) return null;
  const candidate = body as Partial<Schemas['ProblemDetails']>;
  return typeof candidate.code === 'string' && typeof candidate.detail === 'string'
    ? (candidate as Schemas['ProblemDetails'])
    : null;
}

function unexpected(status: number, body: unknown, path: string): ApiProblemError {
  const problem = problemOf(body);
  if (problem !== null && typeof problem.title === 'string') return new ApiProblemError(problem);
  return new ApiProblemError({
    code: 'unexpected_response',
    title: `The API answered with status ${String(status)}`,
    detail: `${path} could not be read or written.`,
  });
}

export class HttpPricingGateway implements PricingGateway {
  private readonly fetchImpl: typeof fetch;

  constructor(fetchImpl: typeof fetch) {
    this.fetchImpl = fetchImpl;
  }

  async list(instanceVersionId: string): Promise<PricingVersion[]> {
    const path = `${apiRoot}/instance-versions/${encodeURIComponent(instanceVersionId)}/pricing-versions`;
    const answer = await this.call('GET', path, undefined);
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return (answer.body as Schemas['PricingVersionList']).items.map(toVersion);
  }

  async get(id: string): Promise<PricingVersion | null> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}`;
    const answer = await this.call('GET', path, undefined);
    if (answer.status === 404) return null;
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return toVersion(answer.body as Schemas['PricingVersionResource']);
  }

  async create(instanceVersionId: string): Promise<PricingVersion> {
    const path = `${apiRoot}/instance-versions/${encodeURIComponent(instanceVersionId)}/pricing-versions`;
    const answer = await this.call('POST', path, {});
    if (answer.status !== 201) throw unexpected(answer.status, answer.body, path);
    return toVersion(answer.body as Schemas['PricingVersionResource']);
  }

  async patch(id: string, changes: PricingChanges): Promise<PricingVersion> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}`;
    const answer = await this.call('PATCH', path, changes);
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return toVersion(answer.body as Schemas['PricingVersionResource']);
  }

  async discard(id: string): Promise<void> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}`;
    const answer = await this.call('DELETE', path, undefined);
    if (answer.status !== 204) throw unexpected(answer.status, answer.body, path);
  }

  async run(id: string): Promise<PricingRunQueued> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}/runs`;
    const answer = await this.call('POST', path, undefined);
    if (answer.status === 202) {
      return { kind: 'queued', runId: (answer.body as Schemas['RunResource']).id };
    }
    const problem = problemOf(answer.body);
    if ((answer.status === 409 || answer.status === 503) && problem !== null) {
      return { kind: 'refused', detail: problem.detail };
    }
    throw unexpected(answer.status, answer.body, path);
  }

  /** Every status comes back; only an unreachable API throws. */
  private async call(
    method: string,
    path: string,
    body: unknown,
  ): Promise<{ status: number; body: unknown }> {
    let response: Response;
    try {
      response = await this.fetchImpl(path, {
        method,
        headers:
          body === undefined
            ? { Accept: 'application/json' }
            : { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      throw new ApiProblemError({
        code: 'api_unreachable',
        title: 'The API could not be reached',
        detail: cause instanceof Error ? cause.message : String(cause),
      });
    }
    let parsed: unknown;
    try {
      parsed = (await response.json()) as unknown;
    } catch {
      parsed = undefined;
    }
    return { status: response.status, body: parsed };
  }
}
