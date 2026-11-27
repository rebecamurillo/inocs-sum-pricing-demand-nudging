/** A saved or draft city instance version as the Lab reads it. */

export interface InstanceMenuVersion {
  readonly id: string;
  readonly number: number;
  readonly status: 'draft' | 'sealed';
  /** `draft`, `ready`, or any other state exactly as the API writes it. */
  readonly state: string;
  readonly pricingVersionCount: number;
}

export interface InstanceMenuEntry {
  readonly id: string;
  readonly name: string;
  readonly datasetId: string;
  readonly versions: readonly InstanceMenuVersion[];
}

/** The 14 numbers of a version, in the package's units (metres, minutes, percent). */
export interface InstanceParameters {
  readonly centerLat: number;
  readonly centerLon: number;
  readonly radiusM: number;
  readonly clusteringThresholdM: number;
  readonly clusteringBufferM: number;
  readonly minOdDistanceM: number;
  readonly minDemand: number;
  readonly maxDemand: number;
  readonly fixedCapacity: number;
  readonly minInventoryPct: number;
  readonly maxInventoryPct: number;
  readonly minParkTimeMin: number;
  readonly maxParkTimeMin: number;
  readonly seed: number;
}

export interface InstancePeriod {
  readonly id: string;
  readonly label: string;
  /** `HH:MM` or `HH:MM:SS`, local. */
  readonly startTime: string;
  /** `YYYY-MM-DD`. */
  readonly routingDate: string;
  /** `HH:MM` or `HH:MM:SS`, local. */
  readonly routingTime: string;
  readonly arriveBy: boolean;
  readonly provisional: boolean;
}

export interface InstanceCounts {
  readonly stops: number;
  readonly bikeStations: number;
  readonly hubs: number;
  readonly hubPairsWithRoutes: number;
  readonly travellers: number;
}

export interface RoutesSummary {
  readonly queries: number;
  readonly queriesFailed: number;
  readonly failurePct: number;
  readonly pairsWithoutPublicTransport: number;
  readonly pairsWithoutCar: number;
  readonly retries: number;
  readonly runId: string | null;
}

export interface InstanceVersion {
  readonly id: string;
  readonly instanceId: string;
  readonly number: number;
  readonly status: 'draft' | 'sealed';
  readonly state: string;
  readonly sealedAt: Date | null;
  readonly parameters: InstanceParameters;
  readonly periods: readonly InstancePeriod[];
  /** Null until the version is built. */
  readonly counts: InstanceCounts | null;
  /** Null until the version is built. */
  readonly routes: RoutesSummary | null;
}

/** The city data set an instance version is built on, as L-1 names it. */
export interface DatasetInfo {
  readonly id: string;
  readonly name: string;
  /** `YYYY-MM-DD`. */
  readonly timetableValidFrom: string;
  /** `YYYY-MM-DD`. */
  readonly timetableValidTo: string;
  /** An ISO date-time. */
  readonly bikeStationsFetchedAt: string;
}

export interface RouteFailure {
  readonly originHub: string;
  readonly destinationHub: string;
  readonly query: 'pt_bike' | 'car';
  readonly kind: 'technical' | 'no_route';
  readonly message: string;
  readonly attempts: number;
}
