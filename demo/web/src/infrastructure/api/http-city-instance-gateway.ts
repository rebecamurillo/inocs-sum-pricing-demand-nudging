import { ApiProblemError } from '../../application/errors';
import type {
  BuildQueued,
  CityInstanceGateway,
  CreatedDraft,
  CreatedInstance,
  Deleted,
  InstanceHub,
  ParameterChanges,
  StartFrom,
} from '../../application/ports/city-instance-gateway';
import type {
  DatasetInfo,
  InstanceMenuEntry,
  InstanceParameters,
  InstanceVersion,
  ParameterName,
  RouteFailure,
} from '../../domain/city-instance';
import type { ComponentName } from '../../domain/system-status';
import type { MapHubPair, MapStation } from '../../domain/map';
import type { components } from './generated/schema';

type Schemas = components['schemas'];

const apiRoot = '/api/v1';

const componentNames: Readonly<
  Record<Schemas['BlockingReasonResponse']['component'], ComponentName>
> = {
  storage: 'storage',
  runner: 'runner',
  solver: 'solver',
  package: 'package',
  trip_planner: 'tripPlanner',
  city_data: 'cityData',
};

function toParameters(p: Schemas['InstanceParametersResource']): InstanceParameters {
  return {
    centerLat: p.center_lat,
    centerLon: p.center_lon,
    radiusM: p.radius_m,
    clusteringThresholdM: p.clustering_threshold_m,
    clusteringBufferM: p.clustering_buffer_m,
    minOdDistanceM: p.min_od_distance_m,
    minDemand: p.min_demand,
    maxDemand: p.max_demand,
    fixedCapacity: p.fixed_capacity,
    minInventoryPct: p.min_inventory_pct,
    maxInventoryPct: p.max_inventory_pct,
    minParkTimeMin: p.min_park_time_min,
    maxParkTimeMin: p.max_park_time_min,
    seed: p.seed,
  };
}

function toVersion(wire: Schemas['InstanceVersionResource']): InstanceVersion {
  const counts = wire.counts;
  const routes = wire.routes;
  return {
    id: wire.id,
    instanceId: wire.instance_id,
    number: wire.number,
    basedOnId: wire.based_on_id,
    status: wire.status,
    state: wire.state,
    buildRunId: wire.build_run_id,
    createdAt: new Date(wire.created_at),
    sealedAt: wire.sealed_at === null ? null : new Date(wire.sealed_at),
    parameters: toParameters(wire.parameters),
    packageDefaults: wire.package_defaults === null ? null : toParameters(wire.package_defaults),
    rules: wire.rules.map((result) => ({
      rule: result.rule,
      passed: result.passed,
      values: [
        {
          name: result.values[0]?.name ?? '',
          value: result.values[0]?.value ?? 0,
          unit: result.values[0]?.unit ?? null,
        },
        {
          name: result.values[1]?.name ?? '',
          value: result.values[1]?.value ?? 0,
          unit: result.values[1]?.unit ?? null,
        },
      ],
    })),
    changes: wire.changes.map((change) => ({
      parameter: change.parameter as ParameterName,
      before: change.before,
      after: change.after,
    })),
    buildPlan: {
      steps: wire.build_plan.steps.map((planned) => ({
        step: planned.step,
        number: planned.number,
        action: planned.action,
        causes: planned.causes.map((cause) => ({
          kind: cause.kind,
          parameters: cause.parameters as ParameterName[],
        })),
        lastDurationS: planned.last_duration_s,
      })),
      verdict: {
        allowed: wire.build_plan.build_verdict.allowed,
        reasons: wire.build_plan.build_verdict.reasons.map((reason) => ({
          component: componentNames[reason.component],
          reason: reason.reason,
        })),
      },
    },
    periods: wire.periods.map((period) => ({
      id: period.id,
      label: period.label,
      startTime: period.start_time,
      routingDate: period.routing_date,
      routingTime: period.routing_time,
      arriveBy: period.arrive_by,
      provisional: period.routing_date_provisional,
    })),
    counts:
      counts === null
        ? null
        : {
            stops: counts.stops.value,
            bikeStations: counts.bike_stations.value,
            hubs: counts.hubs.value,
            hubPairsWithRoutes: counts.hub_pairs_with_routes.value,
            travellers: counts.travellers.value,
          },
    routes:
      routes === null
        ? null
        : {
            queries: routes.queries,
            queriesFailed: routes.queries_failed,
            failurePct: routes.failure_pct,
            pairsWithoutPublicTransport: routes.pairs_without_public_transport,
            pairsWithoutCar: routes.pairs_without_car,
            retries: routes.retries,
            runId: routes.run_id,
          },
  };
}

function toRing(outline: Schemas['HubResource']['outline']): InstanceHub['outline'] {
  const coordinates = outline?.coordinates;
  if (!Array.isArray(coordinates)) return null;
  const ring = (coordinates as unknown[])[0];
  if (!Array.isArray(ring)) return null;
  return (ring as number[][]).map((position) => [position[0] ?? 0, position[1] ?? 0] as const);
}

type Problem = Schemas['ProblemDetails'];

function problemOf(body: unknown): Problem | null {
  if (typeof body !== 'object' || body === null) return null;
  const candidate = body as Partial<Problem>;
  return typeof candidate.code === 'string' && typeof candidate.detail === 'string'
    ? (candidate as Problem)
    : null;
}

/** The typed error for an answer no caller handles: the problem document when there is one. */
function unexpected(answer: { status: number; body: unknown }, path: string): ApiProblemError {
  const problem = problemOf(answer.body);
  if (problem !== null && typeof problem.title === 'string') return new ApiProblemError(problem);
  return new ApiProblemError({
    code: 'unexpected_response',
    title: `The API answered with status ${String(answer.status)}`,
    detail: `${path} could not be written.`,
  });
}

export class HttpCityInstanceGateway implements CityInstanceGateway {
  private readonly fetchImpl: typeof fetch;

  constructor(fetchImpl: typeof fetch) {
    this.fetchImpl = fetchImpl;
  }

  async menu(): Promise<InstanceMenuEntry[]> {
    const body = await this.read<Schemas['CityInstanceMenu']>(`${apiRoot}/city-instances`, false);
    return (body?.items ?? []).map((item) => ({
      id: item.id,
      name: item.name,
      datasetId: item.dataset_id,
      versions: item.versions.map((version) => ({
        id: version.id,
        number: version.number,
        status: version.status,
        state: version.state,
        pricingVersionCount: version.pricing_version_count,
      })),
    }));
  }

  async version(id: string): Promise<InstanceVersion | null> {
    const body = await this.read<Schemas['InstanceVersionResource']>(
      `${apiRoot}/instance-versions/${encodeURIComponent(id)}`,
      true,
    );
    return body === null ? null : toVersion(body);
  }

  async dataset(id: string): Promise<DatasetInfo | null> {
    const body = await this.read<Schemas['CityDatasetList']>(`${apiRoot}/city-datasets`, false);
    const found = body?.items.find((item) => item.id === id);
    if (found === undefined) return null;
    return {
      id: found.id,
      name: found.name,
      timetableValidFrom: found.gtfs_valid_from,
      timetableValidTo: found.gtfs_valid_to,
      bikeStationsFetchedAt: found.gbfs_fetched_at,
    };
  }

  async stations(versionId: string): Promise<MapStation[]> {
    const body = await this.read<Schemas['StationList']>(
      `${apiRoot}/instance-versions/${encodeURIComponent(versionId)}/stations`,
      false,
    );
    return (body?.items ?? []).map((item) => ({
      id: item.station_id,
      kind: item.kind,
      lat: item.lat,
      lon: item.lon,
    }));
  }

  async hubs(versionId: string): Promise<InstanceHub[]> {
    const body = await this.read<Schemas['HubList']>(
      `${apiRoot}/instance-versions/${encodeURIComponent(versionId)}/hubs`,
      false,
    );
    return (body?.items ?? []).map((item) => ({
      id: item.hub_id,
      label: item.label,
      lat: item.lat,
      lon: item.lon,
      outline: toRing(item.outline),
    }));
  }

  async hubPairs(versionId: string): Promise<MapHubPair[]> {
    const body = await this.read<Schemas['HubPairList']>(
      `${apiRoot}/instance-versions/${encodeURIComponent(versionId)}/hub-pairs`,
      false,
    );
    return (body?.items ?? []).map((item) => ({
      originHub: item.origin_hub,
      destinationHub: item.destination_hub,
    }));
  }

  async routePairs(versionId: string): Promise<MapHubPair[]> {
    const body = await this.read<Schemas['RoutePairList']>(
      `${apiRoot}/instance-versions/${encodeURIComponent(versionId)}/route-pairs`,
      false,
    );
    return (body?.items ?? []).map((item) => ({
      originHub: item.origin_hub,
      destinationHub: item.destination_hub,
    }));
  }

  async routeFailures(runId: string): Promise<RouteFailure[]> {
    const body = await this.read<Schemas['RouteFailureList']>(
      `${apiRoot}/runs/${encodeURIComponent(runId)}/route-failures`,
      false,
    );
    return (body?.items ?? []).map((item) => ({
      originHub: item.origin_hub,
      destinationHub: item.destination_hub,
      query: item.query,
      kind: item.kind,
      message: item.message,
      attempts: item.attempts,
    }));
  }

  async createInstance(
    name: string,
    datasetId: string,
    startFrom: StartFrom,
  ): Promise<CreatedInstance> {
    const answer = await this.send('POST', `${apiRoot}/city-instances`, {
      name,
      dataset_id: datasetId,
      start_from:
        startFrom.kind === 'copy'
          ? { kind: 'copy', instance_version_id: startFrom.versionId }
          : { kind: 'package_defaults' },
    });
    if (answer.status === 201) {
      return {
        kind: 'created',
        version: toVersion(answer.body as Schemas['InstanceVersionResource']),
      };
    }
    const problem = problemOf(answer.body);
    if (answer.status === 409 && problem?.code === 'name_taken') {
      return { kind: 'name_taken', detail: problem.detail };
    }
    throw unexpected(answer, `${apiRoot}/city-instances`);
  }

  async createDraft(instanceId: string, basedOnId: string): Promise<CreatedDraft> {
    const path = `${apiRoot}/city-instances/${encodeURIComponent(instanceId)}/versions`;
    const answer = await this.send('POST', path, { based_on_id: basedOnId });
    if (answer.status === 201) {
      return {
        kind: 'created',
        version: toVersion(answer.body as Schemas['InstanceVersionResource']),
      };
    }
    const problem = problemOf(answer.body);
    if (answer.status === 409 && problem?.code === 'draft_exists' && problem.draft_id) {
      return { kind: 'draft_exists', draftId: problem.draft_id };
    }
    throw unexpected(answer, path);
  }

  async patch(id: string, changes: ParameterChanges): Promise<InstanceVersion> {
    const path = `${apiRoot}/instance-versions/${encodeURIComponent(id)}`;
    const answer = await this.send('PATCH', path, changes);
    if (answer.status !== 200) throw unexpected(answer, path);
    return toVersion(answer.body as Schemas['InstanceVersionResource']);
  }

  async discard(id: string): Promise<void> {
    const path = `${apiRoot}/instance-versions/${encodeURIComponent(id)}`;
    const answer = await this.send('DELETE', path, undefined);
    if (answer.status !== 204) throw unexpected(answer, path);
  }

  async deleteVersion(id: string): Promise<Deleted> {
    return this.delete(`${apiRoot}/instance-versions/${encodeURIComponent(id)}`);
  }

  async deleteInstance(id: string): Promise<Deleted> {
    return this.delete(`${apiRoot}/city-instances/${encodeURIComponent(id)}`);
  }

  private async delete(path: string): Promise<Deleted> {
    const answer = await this.send('DELETE', path, undefined);
    if (answer.status === 204) return { kind: 'deleted' };
    if (answer.status === 409 && problemOf(answer.body)?.code === 'run_active') {
      return { kind: 'run_active' };
    }
    throw unexpected(answer, path);
  }

  async build(id: string): Promise<BuildQueued> {
    const path = `${apiRoot}/instance-versions/${encodeURIComponent(id)}/builds`;
    const answer = await this.send('POST', path, undefined);
    if (answer.status === 202) {
      return { kind: 'queued', runId: (answer.body as Schemas['RunResource']).id };
    }
    const problem = problemOf(answer.body);
    if ((answer.status === 409 || answer.status === 503) && problem !== null) {
      return { kind: 'refused', detail: problem.detail };
    }
    throw unexpected(answer, path);
  }

  /** A request with a JSON body; every status comes back, only an unreachable API throws. */
  private async send(
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

  /** GET and parse; a 404 gives null when `nullOn404`, any other failure throws a typed error. */
  private async read<T>(path: string, nullOn404: boolean): Promise<T | null> {
    let response: Response;
    try {
      response = await this.fetchImpl(path, { headers: { Accept: 'application/json' } });
    } catch (cause) {
      throw new ApiProblemError({
        code: 'api_unreachable',
        title: 'The API could not be reached',
        detail: cause instanceof Error ? cause.message : String(cause),
      });
    }
    if (nullOn404 && response.status === 404) return null;
    if (!response.ok) {
      throw new ApiProblemError({
        code: 'unexpected_response',
        title: `The API answered with status ${String(response.status)}`,
        detail: `${path} could not be read.`,
      });
    }
    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiProblemError({
        code: 'unexpected_response',
        title: 'The API answer could not be read',
        detail: 'The answer is not JSON.',
      });
    }
  }
}
