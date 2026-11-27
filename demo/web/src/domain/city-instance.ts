/** A saved or draft city instance version as the Lab reads it. */
import type { ComponentName } from './system-status';

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

/** The 14 parameters as the API writes them: what a `PATCH` sends and a change names. */
export type ParameterName =
  | 'center_lat'
  | 'center_lon'
  | 'radius_m'
  | 'clustering_threshold_m'
  | 'clustering_buffer_m'
  | 'min_od_distance_m'
  | 'min_demand'
  | 'max_demand'
  | 'fixed_capacity'
  | 'min_inventory_pct'
  | 'max_inventory_pct'
  | 'min_park_time_min'
  | 'max_park_time_min'
  | 'seed';

/** Which `InstanceParameters` key holds each wire name; in the API's column order. */
export const PARAMETER_KEYS: Readonly<Record<ParameterName, keyof InstanceParameters>> = {
  center_lat: 'centerLat',
  center_lon: 'centerLon',
  radius_m: 'radiusM',
  clustering_threshold_m: 'clusteringThresholdM',
  clustering_buffer_m: 'clusteringBufferM',
  min_od_distance_m: 'minOdDistanceM',
  min_demand: 'minDemand',
  max_demand: 'maxDemand',
  fixed_capacity: 'fixedCapacity',
  min_inventory_pct: 'minInventoryPct',
  max_inventory_pct: 'maxInventoryPct',
  min_park_time_min: 'minParkTimeMin',
  max_park_time_min: 'maxParkTimeMin',
  seed: 'seed',
};

export const PARAMETER_NAMES = Object.keys(PARAMETER_KEYS) as readonly ParameterName[];

/** One of the two values a rule compares. */
export interface RuleValue {
  readonly name: string;
  readonly value: number | string;
  readonly unit: string | null;
}

export interface RuleResult {
  readonly rule: string;
  readonly passed: boolean;
  readonly values: readonly [RuleValue, RuleValue];
}

export interface ParameterChange {
  readonly parameter: ParameterName;
  readonly before: number;
  readonly after: number;
}

export type StepName =
  'area' | 'hubs' | 'routes' | 'travellers_and_bikes' | 'pricing_model' | 'traveller_simulation';

export interface PlannedStep {
  readonly step: StepName;
  /** 1 to 4. */
  readonly number: number;
  readonly action: 'kept' | 'rebuilt';
  readonly causes: readonly {
    readonly kind: 'parameter' | 'city_data' | 'package' | 'trip_planner_graph';
    readonly parameters: readonly ParameterName[];
  }[];
  /** Seconds the same step last took on the same data set and radius. */
  readonly lastDurationS: number | null;
}

export interface BuildPlan {
  readonly steps: readonly PlannedStep[];
  readonly verdict: {
    readonly allowed: boolean;
    readonly reasons: readonly { readonly component: ComponentName; readonly reason: string }[];
  };
}

export interface InstanceVersion {
  readonly id: string;
  readonly instanceId: string;
  readonly number: number;
  /** The version a draft was started from; null for a version based on none. */
  readonly basedOnId: string | null;
  readonly status: 'draft' | 'sealed';
  readonly state: string;
  /** The version's latest build run; null for a draft or a version never built. */
  readonly buildRunId: string | null;
  readonly createdAt: Date;
  readonly sealedAt: Date | null;
  /** The package's default values for a draft; null for a saved version. */
  readonly packageDefaults: InstanceParameters | null;
  readonly rules: readonly RuleResult[];
  /** The parameters that differ from the version this one is based on. */
  readonly changes: readonly ParameterChange[];
  readonly buildPlan: BuildPlan;
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
