/** The sentences of the instance view L-1, built from values. Wording belongs here, not in JSX. */
import type {
  DatasetInfo,
  InstanceMenuEntry,
  InstanceParameters,
  InstancePeriod,
  RouteFailure,
  RoutesSummary,
} from './city-instance';

const SHORT_MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;
const LONG_MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;
const WEEKDAYS = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
] as const;

const DISPLAY_ZONE = 'Europe/Zurich';
const ZONE_DAY = new Intl.DateTimeFormat('en-GB', {
  timeZone: DISPLAY_ZONE,
  day: 'numeric',
  month: 'numeric',
  year: 'numeric',
});

/** 1412 → "1 412": a plain space groups the thousands. */
export function groupThousands(n: number): string {
  const digits = String(Math.abs(Math.trunc(n)));
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return n < 0 ? `-${grouped}` : grouped;
}

function datePart(date: string): { year: number; month: number; day: number } {
  const [year = 0, month = 1, day = 1] = date.slice(0, 10).split('-').map(Number);
  return { year, month, day };
}

/** "12 Nov 2026" from an ISO calendar date (`YYYY-MM-DD`): no time zone is involved. */
export function formatDate(date: string): string {
  const { year, month, day } = datePart(date);
  return `${String(day)} ${SHORT_MONTHS[month - 1] ?? ''} ${String(year)}`;
}

/** "12 Nov 2026": the calendar day an instant falls on in Europe/Zurich. */
export function formatInstantDay(instant: Date | string): string {
  const parts = ZONE_DAY.formatToParts(new Date(instant));
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return `${String(value('day'))} ${SHORT_MONTHS[value('month') - 1] ?? ''} ${String(value('year'))}`;
}

export function usedBy(n: number): string {
  return n === 1 ? 'used by 1 pricing version' : `used by ${String(n)} pricing versions`;
}

export function readyLine(sealedAt: Date | null, pricingVersions: number): string {
  const saved = sealedAt === null ? '' : ` · saved ${formatInstantDay(sealedAt)}`;
  return `Ready${saved} · ${usedBy(pricingVersions)}`;
}

export function timetableSentence(from: string, to: string, fetchedAt: string): string {
  return `Timetable valid ${formatDate(from)} to ${formatDate(to)} · bike stations fetched ${formatInstantDay(fetchedAt)}.`;
}

export function centreText(lat: number, lon: number): string {
  return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}

export function radiusText(radiusM: number): string {
  return `${(radiusM / 1000).toFixed(1)} km`;
}

/** Package units are degrees of latitude scaled: at the centre's latitude a unit is cos(lat) m. */
export function packageUnitsCaption(value: number, centreLat: number): string {
  const ground = Math.round(value * Math.cos((centreLat * Math.PI) / 180));
  return `package units, about 0.69 m on the ground at Geneva: ${String(value)} is about ${String(ground)} m`;
}

function hhmm(time: string): string {
  return time.slice(0, 5);
}

export function routingMomentSentence(period: InstancePeriod): string {
  const { year, month, day } = datePart(period.routingDate);
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()] ?? '';
  const when = `${weekday} ${String(day)} ${LONG_MONTHS[month - 1] ?? ''} ${String(year)}`;
  const direction = period.arriveBy ? 'arrive by' : 'leave at';
  const provisional = period.provisional ? ' · provisional' : '';
  return `Routes planned for ${when}, ${direction} ${hhmm(period.routingTime)}${provisional}.`;
}

function pairsWithoutPublicTransport(n: number): string {
  return n === 1
    ? '1 hub pair has no public transport route and is not priced'
    : `${groupThousands(n)} hub pairs have no public transport route and are not priced`;
}

function pairsWithoutCar(n: number): string {
  return n === 1 ? '1 has no car option' : `${groupThousands(n)} have no car option`;
}

export function routesLine(routes: RoutesSummary): string {
  if (routes.queriesFailed === 0) {
    return `Routes: all ${groupThousands(routes.queries)} trip-planner queries gave a route.`;
  }
  return (
    `Routes: ${groupThousands(routes.queriesFailed)} of ${groupThousands(routes.queries)} trip-planner queries gave no route ` +
    `(${routes.failurePct.toFixed(1)} %). ${pairsWithoutPublicTransport(routes.pairsWithoutPublicTransport)}; ` +
    `${pairsWithoutCar(routes.pairsWithoutCar)}. ` +
    `A technical error is tried ${String(routes.retries)} times before it counts.`
  );
}

export function showPairsLink(n: number): string {
  return n === 1
    ? 'Show the 1 hub pair without a route'
    : `Show the ${groupThousands(n)} hub pairs without a route`;
}

export interface FailureRowTexts {
  readonly fromTo: string;
  readonly query: string;
  readonly whatHappened: string;
  readonly effect: string;
}

export function failureRowTexts(
  failure: RouteFailure,
  retries: number,
  hubLabel: (hubId: string) => string,
): FailureRowTexts {
  return {
    fromTo: `${hubLabel(failure.originHub)} → ${hubLabel(failure.destinationHub)}`,
    query: failure.query === 'pt_bike' ? 'Public transport' : 'Car',
    whatHappened:
      failure.kind === 'no_route'
        ? 'No route found'
        : `Trip planner error after ${String(retries)} tries: ${failure.message}`,
    effect: failure.query === 'pt_bike' ? 'Not in the instance: not priced' : 'No car option',
  };
}

export function breadcrumb(name: string, number: number): string {
  return `${name} v${String(number)} › Instance set-up`;
}

export function periodChip(label: string): string {
  return `Period ${label}`;
}

export function menuVersionState(state: string): string {
  return state;
}

export function collapsedCount(n: number): string {
  return n === 1 ? '1 version' : `${String(n)} versions`;
}

/** The instance a menu entry names, with its latest version, for the collapsed row. */
export function latestVersion(entry: InstanceMenuEntry) {
  return entry.versions.reduce<InstanceMenuEntry['versions'][number] | null>(
    (latest, version) => (latest === null || version.number > latest.number ? version : latest),
    null,
  );
}

export interface L1Field {
  readonly name: string;
  readonly packageNames: string;
  readonly value: string;
  readonly sentence: string | null;
  readonly caption: string | null;
}

export interface L1Group {
  readonly number: number;
  readonly name: string;
  readonly fields: readonly L1Field[];
}

const CITY_DATA_SENTENCE =
  'Public transport timetable (GTFS) and shared-bike stations (GBFS), preloaded for Geneva.';

function field(
  name: string,
  packageNames: string,
  value: string,
  sentence: string | null,
  caption: string | null = null,
): L1Field {
  return { name, packageNames, value, sentence, caption };
}

const metres = (value: number) => `${String(value)} m`;

/** The four read-only groups of the saved instance, as data. */
export function l1Groups(
  version: { readonly parameters: InstanceParameters; readonly periods: readonly InstancePeriod[] },
  dataset: DatasetInfo,
): readonly L1Group[] {
  const p = version.parameters;
  const [first] = version.periods;
  const periods = version.periods.length;
  const periodsSentence = [
    'The periods this instance has routes and travellers for; a pricing version chooses among them.',
    periods === 1 ? 'One in this version.' : `${String(periods)} in this version.`,
    ...(first === undefined ? [] : [routingMomentSentence(first)]),
  ].join(' ');
  const startHour = first === undefined ? '08:00' : hhmm(first.startTime);

  return [
    {
      number: 1,
      name: 'Area',
      fields: [
        field(
          'City data',
          'gtfs_path · gbfs_path',
          dataset.name,
          `${CITY_DATA_SENTENCE} ${timetableSentence(dataset.timetableValidFrom, dataset.timetableValidTo, dataset.bikeStationsFetchedAt)}`,
        ),
        field('Centre', 'center_lat · center_lon', centreText(p.centerLat, p.centerLon), null),
        field(
          'Radius',
          'radius_m',
          radiusText(p.radiusM),
          'From 1 to 5 km. A larger zone has more hubs and takes longer to build.',
        ),
      ],
    },
    {
      number: 2,
      name: 'Hubs',
      fields: [
        field(
          'Grouping distance',
          'clustering_threshold_m',
          metres(p.clusteringThresholdM),
          'Stops and stations closer than this form one hub.',
          packageUnitsCaption(p.clusteringThresholdM, p.centerLat),
        ),
        field(
          'Hub outline margin',
          'clustering_buffer_m',
          metres(p.clusteringBufferM),
          "Space drawn around a hub's stops and stations.",
          packageUnitsCaption(p.clusteringBufferM, p.centerLat),
        ),
      ],
    },
    {
      number: 3,
      name: 'Routes',
      fields: [
        field(
          'Minimum trip distance',
          'min_od_distance_m',
          metres(p.minOdDistanceM),
          'Hub pairs closer than this are not priced. Must be greater than the grouping distance.',
        ),
        field(
          'Periods prepared',
          'otp_timestamp',
          version.periods.map((period) => period.label).join(', '),
          periodsSentence,
        ),
      ],
    },
    {
      number: 4,
      name: 'Travellers and bikes',
      fields: [
        field(
          'Travellers per hub pair',
          'min_demand · max_demand',
          `${String(p.minDemand)} to ${String(p.maxDemand)}`,
          'Drawn at random for the period.',
        ),
        field(
          'Docks per station',
          'fixed_capacity',
          String(p.fixedCapacity),
          'Places for bikes at each station.',
        ),
        field(
          `Bikes at ${startHour}`,
          'min_inventory_pct · max_inventory_pct',
          `${String(p.minInventoryPct)} to ${String(p.maxInventoryPct)} % of docks`,
          'Drawn at random for each station.',
        ),
        field(
          'Car parking search',
          'min_park_time_min · max_park_time_min',
          `${String(p.minParkTimeMin)} to ${String(p.maxParkTimeMin)} min`,
          'Time added to a car trip, drawn at random.',
        ),
        field(
          'Random seed',
          'seed',
          String(p.seed),
          'The same seed draws the same travellers and bikes.',
        ),
      ],
    },
  ];
}

export const COUNT_LABELS = [
  ['stops', 'Stops and platforms'],
  ['bikeStations', 'Bike stations'],
  ['hubs', 'Hubs'],
  ['hubPairsWithRoutes', 'Hub pairs with routes'],
  ['travellers', 'Travellers in the period'],
] as const;

export type CountKey = (typeof COUNT_LABELS)[number][0];

export const L1_BRIEF = 'City instance · pipeline steps 1 to 4';
export const L1_SENTENCE =
  'The study area prepared for the pricing model: stops and bike stations, hubs, routes between hubs, and the travellers and bikes of the period.';
export const NEVER_REUSED = 'Version numbers are never reused.';
export const NEVER_CHANGED =
  'A saved instance is never changed: editing it saves a new version, so every pricing version keeps the instance it was run on.';

export function versionTag(number: number): string {
  return `v${String(number)}`;
}
