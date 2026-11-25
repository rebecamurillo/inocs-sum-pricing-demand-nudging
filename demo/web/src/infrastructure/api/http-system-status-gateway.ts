import { ApiProblemError } from '../../application/errors';
import type { SystemStatusGateway } from '../../application/ports/system-status-gateway';
import type { ComponentName, ComponentStatus, SystemStatus } from '../../domain/system-status';
import type { components } from './generated/schema';

type SystemStatusResponse = components['schemas']['SystemStatusResponse'];
type ComponentStatusResponse = components['schemas']['ComponentStatusResponse'];
type ProblemDetails = components['schemas']['ProblemDetails'];

const systemStatusPath = '/api/v1/system-status';

// Typed over the wire enum: a component added to the contract fails the build here.
const componentNames: Readonly<Record<ComponentStatusResponse['name'], ComponentName>> = {
  storage: 'storage',
  pricing_model: 'pricingModel',
  solver: 'solver',
  trip_planner: 'tripPlanner',
};

function toComponentStatus(component: ComponentStatusResponse): ComponentStatus {
  return {
    name: componentNames[component.name],
    available: component.available,
    reason: component.reason,
  };
}

function toSystemStatus(response: SystemStatusResponse): SystemStatus {
  return {
    apiVersion: response.api_version,
    components: response.components.map(toComponentStatus),
    canReadStoredResults: response.can_read_stored_results,
    canStartRuns: response.can_start_runs,
  };
}

function isProblem(body: unknown): body is ProblemDetails {
  if (typeof body !== 'object' || body === null) return false;
  return (
    'code' in body &&
    typeof body.code === 'string' &&
    'title' in body &&
    typeof body.title === 'string' &&
    'detail' in body &&
    typeof body.detail === 'string'
  );
}

/** The parsed JSON body, or undefined when the body is not JSON (a proxy's error page, say). */
async function readJson(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return undefined;
  }
}

export class HttpSystemStatusGateway implements SystemStatusGateway {
  private readonly fetchImpl: typeof fetch;

  constructor(fetchImpl: typeof fetch) {
    this.fetchImpl = fetchImpl;
  }

  async load(): Promise<SystemStatus> {
    let response: Response;
    try {
      response = await this.fetchImpl(systemStatusPath, {
        headers: { Accept: 'application/json' },
      });
    } catch (cause) {
      throw new ApiProblemError({
        code: 'api_unreachable',
        title: 'The API could not be reached',
        detail: cause instanceof Error ? cause.message : String(cause),
      });
    }

    const body = await readJson(response);

    if (!response.ok) {
      if (isProblem(body)) throw new ApiProblemError(body);
      throw new ApiProblemError({
        code: 'unexpected_response',
        title: `The API answered with status ${String(response.status)}`,
        detail: 'The answer is not a problem document.',
      });
    }

    if (body === undefined) {
      throw new ApiProblemError({
        code: 'unexpected_response',
        title: 'The API answer could not be read',
        detail: 'The answer is not JSON.',
      });
    }

    return toSystemStatus(body as SystemStatusResponse);
  }
}
