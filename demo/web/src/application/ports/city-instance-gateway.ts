import type {
  DatasetInfo,
  InstanceMenuEntry,
  InstanceVersion,
  ParameterName,
  RouteFailure,
} from '../../domain/city-instance';
import type { MapHub, MapHubPair, MapStation } from '../../domain/map';

/** A hub as L-1 names it (its label) and the map draws it. */
export interface InstanceHub extends MapHub {
  readonly label: string;
}

/** What a new instance starts from: the package's default values or the values of a saved version. */
export type StartFrom =
  { readonly kind: 'package_defaults' } | { readonly kind: 'copy'; readonly versionId: string };

export type CreatedInstance =
  | { readonly kind: 'created'; readonly version: InstanceVersion }
  | { readonly kind: 'name_taken'; readonly detail: string };

export type CreatedDraft =
  | { readonly kind: 'created'; readonly version: InstanceVersion }
  | { readonly kind: 'draft_exists'; readonly draftId: string };

export type BuildQueued =
  | { readonly kind: 'queued'; readonly runId: string }
  | { readonly kind: 'refused'; readonly detail: string };

export type ParameterChanges = Partial<Record<ParameterName, number>>;

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
  /** The hub pairs the routes step routed: there from step 3 on, before `hubPairs` answers any. */
  routePairs(versionId: string): Promise<MapHubPair[]>;
  /** The failed trip-planner queries of a run. */
  routeFailures(runId: string): Promise<RouteFailure[]>;
  /** Creates an instance and its first draft; a used name creates nothing. */
  createInstance(name: string, datasetId: string, startFrom: StartFrom): Promise<CreatedInstance>;
  /** Creates the draft of a new version based on `basedOnId`; an instance with a draft names it. */
  createDraft(instanceId: string, basedOnId: string): Promise<CreatedDraft>;
  /** Stores the values as sent; the answer carries every rule result. */
  patch(id: string, changes: ParameterChanges): Promise<InstanceVersion>;
  /** Removes a draft. */
  discard(id: string): Promise<void>;
  /** Seals the draft and queues its build. */
  build(id: string): Promise<BuildQueued>;
}
