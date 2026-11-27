import type {
  DatasetInfo,
  InstanceVersion,
  RouteFailure,
  RoutesSummary,
} from '../../domain/city-instance';
import type { InstanceMenuEntry } from '../../domain/city-instance';
import type { MapHubPair, MapStation } from '../../domain/map';
import { latestDataset } from '../../domain/map';
import type { CityDatasetGateway } from '../ports/city-dataset-gateway';
import type { CityInstanceGateway, InstanceHub } from '../ports/city-instance-gateway';

/** Everything the saved instance card writes, read in one go. */
export interface InstanceView {
  readonly version: InstanceVersion;
  /** The instance's name; its id when the menu does not list it. */
  readonly instanceName: string;
  readonly dataset: DatasetInfo;
  readonly pricingVersionCount: number;
}

/** The version, its instance's name and pricing versions, and its data set; null for no such version. */
export async function loadInstanceView(
  gateways: { cityInstances: CityInstanceGateway },
  versionId: string,
): Promise<InstanceView | null> {
  const { cityInstances } = gateways;
  const version = await cityInstances.version(versionId);
  if (version === null) return null;
  const menu = await cityInstances.menu();
  const entry = menu.find((candidate) => candidate.id === version.instanceId);
  const dataset = entry === undefined ? null : await cityInstances.dataset(entry.datasetId);
  if (entry === undefined || dataset === null) {
    throw new Error(`The instance or the city data of ${versionId} could not be found.`);
  }
  const listed = entry.versions.find((candidate) => candidate.id === version.id);
  return {
    version,
    instanceName: entry.name,
    dataset,
    pricingVersionCount: listed?.pricingVersionCount ?? 0,
  };
}

/** The failed queries of the run that produced the routes; none when none failed. */
export async function loadRouteFailures(
  gateways: { cityInstances: CityInstanceGateway },
  routes: RoutesSummary | null,
): Promise<RouteFailure[]> {
  const runId = routes?.runId ?? null;
  if (runId === null || routes?.queriesFailed === 0) return [];
  return gateways.cityInstances.routeFailures(runId);
}

/** The instances with their versions, for the menu. */
export function loadInstanceMenu(gateways: {
  cityInstances: CityInstanceGateway;
}): Promise<InstanceMenuEntry[]> {
  return gateways.cityInstances.menu();
}

/** What the map draws of a version: its stations, hubs and hub pairs. */
export interface InstanceGeometry {
  readonly stations: readonly MapStation[];
  readonly hubs: readonly InstanceHub[];
  readonly hubPairs: readonly MapHubPair[];
}

export async function loadInstanceGeometry(
  gateways: { cityInstances: CityInstanceGateway },
  versionId: string,
): Promise<InstanceGeometry> {
  const { cityInstances } = gateways;
  const [stations, hubs, hubPairs] = await Promise.all([
    cityInstances.stations(versionId),
    cityInstances.hubs(versionId),
    cityInstances.hubPairs(versionId),
  ]);
  // The hub pairs are stored with the last step; the routed pairs are there from step 3.
  const pairs = hubPairs.length > 0 ? hubPairs : await cityInstances.routePairs(versionId);
  return { stations, hubs, hubPairs: pairs };
}

/** What the new-instance form offers: the city data to build on and the saved versions to copy. */
export interface NewInstanceBasis {
  /** The latest city data set; null while none is imported. */
  readonly dataset: DatasetInfo | null;
  readonly copies: readonly {
    readonly versionId: string;
    readonly name: string;
    readonly number: number;
  }[];
}

export async function loadNewInstanceBasis(gateways: {
  cityInstances: CityInstanceGateway;
  cityDatasets: CityDatasetGateway;
}): Promise<NewInstanceBasis> {
  const [datasets, menu] = await Promise.all([
    gateways.cityDatasets.list(),
    gateways.cityInstances.menu(),
  ]);
  const latest = latestDataset(datasets);
  const dataset = latest === null ? null : await gateways.cityInstances.dataset(latest.id);
  const copies = menu.flatMap((entry) =>
    entry.versions
      .filter((version) => version.status === 'sealed')
      .map((version) => ({ versionId: version.id, name: entry.name, number: version.number })),
  );
  return { dataset, copies };
}
