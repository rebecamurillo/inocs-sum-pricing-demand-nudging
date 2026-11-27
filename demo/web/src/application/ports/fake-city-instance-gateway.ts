import {
  PARAMETER_KEYS,
  type BuildPlan,
  type DatasetInfo,
  type InstanceMenuEntry,
  type InstanceVersion,
  type ParameterName,
  type RoutesSummary,
} from '../../domain/city-instance';
import type { CityInstanceGateway } from './city-instance-gateway';

/** What tests of the instance views start from; each test overrides what it is about. */
export const sampleVersion: InstanceVersion = {
  id: 'geneva-3km.v1',
  instanceId: 'geneva-3km',
  number: 1,
  status: 'sealed',
  state: 'ready',
  basedOnId: null,
  createdAt: new Date('2026-11-12T09:00:00Z'),
  sealedAt: new Date('2026-11-12T10:00:00Z'),
  packageDefaults: null,
  rules: [],
  changes: [],
  buildPlan: { steps: [], verdict: { allowed: true, reasons: [] } },
  parameters: {
    centerLat: 46.2057,
    centerLon: 6.1489,
    radiusM: 3000,
    clusteringThresholdM: 500,
    clusteringBufferM: 100,
    minOdDistanceM: 900,
    minDemand: 10,
    maxDemand: 70,
    fixedCapacity: 20,
    minInventoryPct: 0,
    maxInventoryPct: 100,
    minParkTimeMin: 1,
    maxParkTimeMin: 5,
    seed: 42,
  },
  periods: [
    {
      id: 'geneva-3km.v1.mon-08',
      label: 'Monday 08:00–09:00',
      startTime: '08:00:00',
      routingDate: '2025-03-10',
      routingTime: '08:30:00',
      arriveBy: true,
      provisional: true,
    },
  ],
  counts: { stops: 1412, bikeStations: 118, hubs: 64, hubPairsWithRoutes: 1806, travellers: 72240 },
  routes: {
    queries: 3960,
    queriesFailed: 0,
    failurePct: 0,
    pairsWithoutPublicTransport: 0,
    pairsWithoutCar: 0,
    retries: 3,
    runId: 'run-1',
  },
};

/** The four steps of a plan, `kept` or `rebuilt` each; the sample has no measured duration. */
export function samplePlan(
  actions: readonly ('kept' | 'rebuilt')[] = ['kept', 'rebuilt', 'rebuilt', 'rebuilt'],
): BuildPlan {
  const names = ['area', 'hubs', 'routes', 'travellers_and_bikes'] as const;
  return {
    steps: actions.map((action, at) => ({
      step: names[at] ?? 'area',
      number: at + 1,
      action,
      causes: action === 'rebuilt' ? [{ kind: 'parameter', parameters: [] }] : [],
      lastDurationS: null,
    })),
    verdict: { allowed: true, reasons: [] },
  };
}

/** The values a draft of the sample instance starts from: the package's defaults. */
export const samplePackageDefaults: InstanceVersion['parameters'] = {
  ...sampleVersion.parameters,
  minOdDistanceM: 500,
  maxInventoryPct: 1,
};

const passingRules = [
  'min_trip_distance_above_grouping',
  'radius_1_to_5_km',
  'travellers_lowest_not_above_highest',
  'bikes_0_to_100_pct',
  'centre_inside_area',
  'routing_date_inside_timetable',
  'docks_at_least_1',
  'bikes_and_parking_lowest_not_above_highest',
  'seed_whole_number',
  'grouping_above_0_margin_0_or_more',
].map((rule) => ({
  rule,
  passed: true,
  values: [
    { name: 'a', value: 1, unit: null },
    { name: 'b', value: 1, unit: null },
  ] as const,
}));

/** A draft of the sample instance: v2, based on v1, nothing changed yet, every rule passing. */
export const sampleDraft: InstanceVersion = {
  ...sampleVersion,
  id: 'geneva-3km.v2',
  number: 2,
  basedOnId: 'geneva-3km.v1',
  status: 'draft',
  state: 'draft',
  createdAt: new Date('2026-11-24T10:00:00Z'),
  sealedAt: null,
  counts: null,
  routes: null,
  packageDefaults: samplePackageDefaults,
  rules: passingRules,
  changes: [],
  buildPlan: samplePlan(['kept', 'kept', 'kept', 'kept']),
};

/** The draft with the changed values applied: the answer a `PATCH` gives. */
export function patchedDraft(
  draft: InstanceVersion,
  changes: Partial<Record<ParameterName, number>>,
): InstanceVersion {
  const parameters = { ...draft.parameters };
  for (const [name, value] of Object.entries(changes) as [ParameterName, number][]) {
    (parameters as Record<string, number>)[PARAMETER_KEYS[name]] = value;
  }
  return { ...draft, parameters };
}

export const sampleFailedRoutes: RoutesSummary = {
  queries: 48,
  queriesFailed: 2,
  failurePct: 4.1666,
  pairsWithoutPublicTransport: 1,
  pairsWithoutCar: 1,
  retries: 3,
  runId: 'run-1',
};

export const sampleDataset: DatasetInfo = {
  id: 'geneva-2026-11-26',
  name: 'Geneva · tpg + Donkey Republic',
  timetableValidFrom: '2024-12-15',
  timetableValidTo: '2025-12-13',
  bikeStationsFetchedAt: '2026-11-10T09:30:00Z',
};

export const sampleMenu: InstanceMenuEntry[] = [
  {
    id: 'geneva-3km',
    name: 'Geneva 3 km',
    datasetId: 'geneva-2026-11-26',
    versions: [
      { id: 'geneva-3km.v1', number: 1, status: 'sealed', state: 'ready', pricingVersionCount: 3 },
    ],
  },
  {
    id: 'geneva-2km',
    name: 'Geneva 2 km',
    datasetId: 'geneva-2026-11-26',
    versions: [
      { id: 'geneva-2km.v1', number: 1, status: 'sealed', state: 'ready', pricingVersionCount: 0 },
    ],
  },
];

/** A gateway that answers with the samples; `overrides` replace single methods. */
export function fakeCityInstances(
  overrides: Partial<CityInstanceGateway> = {},
): CityInstanceGateway {
  return {
    menu: () => Promise.resolve(sampleMenu),
    version: (id) =>
      Promise.resolve(
        id === sampleVersion.id ? sampleVersion : id === sampleDraft.id ? sampleDraft : null,
      ),
    dataset: () => Promise.resolve(sampleDataset),
    stations: () =>
      Promise.resolve([
        { id: 'p1', kind: 'pt', lat: 46.21, lon: 6.14 },
        { id: 'b1', kind: 'bs', lat: 46.2, lon: 6.15 },
      ]),
    hubs: () =>
      Promise.resolve([
        { id: 'H1', label: 'Hub H1', lat: 46.2, lon: 6.14, outline: null },
        { id: 'H2', label: 'Hub H2', lat: 46.22, lon: 6.16, outline: null },
      ]),
    hubPairs: () => Promise.resolve([{ originHub: 'H1', destinationHub: 'H2' }]),
    routeFailures: () => Promise.resolve([]),
    createInstance: () => Promise.resolve({ kind: 'created', version: sampleDraft }),
    createDraft: () => Promise.resolve({ kind: 'created', version: sampleDraft }),
    patch: (_id, changes) => Promise.resolve(patchedDraft(sampleDraft, changes)),
    discard: () => Promise.resolve(),
    build: () => Promise.resolve({ kind: 'queued', runId: 'run-2' }),
    ...overrides,
  };
}

/** The gateway with no instance at all: the empty Lab. */
export const emptyCityInstances: CityInstanceGateway = fakeCityInstances({
  menu: () => Promise.resolve([]),
  version: () => Promise.resolve(null),
});
