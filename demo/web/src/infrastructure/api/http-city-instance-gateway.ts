import { ApiProblemError } from '../../application/errors';
import type {
  CityInstanceGateway,
  InstanceHub,
} from '../../application/ports/city-instance-gateway';
import type {
  DatasetInfo,
  InstanceMenuEntry,
  InstanceVersion,
  RouteFailure,
} from '../../domain/city-instance';
import type { MapHubPair, MapStation } from '../../domain/map';
import type { components } from './generated/schema';

type Schemas = components['schemas'];

const apiRoot = '/api/v1';

function toVersion(wire: Schemas['InstanceVersionResource']): InstanceVersion {
  const p = wire.parameters;
  const counts = wire.counts;
  const routes = wire.routes;
  return {
    id: wire.id,
    instanceId: wire.instance_id,
    number: wire.number,
    status: wire.status,
    state: wire.state,
    sealedAt: wire.sealed_at === null ? null : new Date(wire.sealed_at),
    parameters: {
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
