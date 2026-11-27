import type {
  DatasetInfo,
  InstanceMenuEntry,
  InstanceVersion,
  RouteFailure,
} from '../../domain/city-instance';
import type { MapHub, MapHubPair, MapStation } from '../../domain/map';

/** A hub as L-1 names it (its label) and the map draws it. */
export interface InstanceHub extends MapHub {
  readonly label: string;
}

export interface CityInstanceGateway {
  /** Every instance with its versions. */
  menu(): Promise<InstanceMenuEntry[]>;
  /** One version; null when the API has none by this id. */
  version(id: string): Promise<InstanceVersion | null>;
  /** The data set an instance is built on; null when the API has none by this id. */
  dataset(id: string): Promise<DatasetInfo | null>;
  stations(versionId: string): Promise<MapStation[]>;
  hubs(versionId: string): Promise<InstanceHub[]>;
  hubPairs(versionId: string): Promise<MapHubPair[]>;
  /** The failed trip-planner queries of a run. */
  routeFailures(runId: string): Promise<RouteFailure[]>;
}
