import { ApiProblemError } from '../../application/errors';
import type { SystemStatusGateway } from '../../application/ports/system-status-gateway';
import type {
  ComponentName,
  ComponentStatus,
  SystemStatus,
  Verdict,
} from '../../domain/system-status';
import type { components } from './generated/schema';

type SystemStatusResponse = components['schemas']['SystemStatusResponse'];
type ComponentStatusResponse = components['schemas']['ComponentStatusResponse'];
type VerdictResponse = components['schemas']['VerdictResponse'];
type ProblemDetails = components['schemas']['ProblemDetails'];

const systemStatusPath = '/api/v1/system-status';

// Typed over the wire enum: a component added to the contract fails the build here.
const componentNames: Readonly<Record<ComponentStatusResponse['name'], ComponentName>> = {
  storage: 'storage',
  runner: 'runner',
  solver: 'solver',
  package: 'package',
  trip_planner: 'tripPlanner',
  city_data: 'cityData',
};

function toComponentStatus(component: ComponentStatusResponse): ComponentStatus {
  return {
    name: componentNames[component.name],
    state: component.state,
    reason: component.reason,
  };
}

function toVerdict(verdict: VerdictResponse): Verdict {
  return {
    allowed: verdict.allowed,
    reasons: verdict.reasons.map((blocking) => ({
      component: componentNames[blocking.component],
      reason: blocking.reason,
    })),
  };
}

function toSystemStatus(response: SystemStatusResponse): SystemStatus {
  return {
    components: response.components.map(toComponentStatus),
    canBuildInstances: toVerdict(response.can_build_instances),
    canRunPricing: toVerdict(response.can_run_pricing),
    canSimulate: toVerdict(response.can_simulate),
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
