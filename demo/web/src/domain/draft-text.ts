/** The sentences and field rules of the instance draft form, built from values. Wording belongs here, not in JSX. */
import {
  PARAMETER_KEYS,
  type BuildPlan,
  type InstanceParameters,
  type InstancePeriod,
  type ParameterChange,
  type ParameterName,
  type RuleResult,
  type RuleValue,
} from './city-instance';
import { formatDate, formatInstantDay, versionTag } from './l1-text';
import type { ComponentName } from './system-status';

export const STORED_STAY = 'Stored results stay available.';
export const NO_CITY_DATA =
  "No city data is imported yet. A city instance needs a timetable and bike stations; the maintainer imports Geneva's with one command (demo/README.md).";
export const ANOTHER_CITY = 'Another city · not in this version';
export const ANOTHER_CITY_SENTENCE =
  'A city needs a public transport timetable (GTFS) and a shared-bike station feed (GBFS).';
export const START_FROM_DEFAULTS = "The model package's default values";
export const RESTORE_LABEL = 'Restore the package defaults';
export const RESTORE_TITLE =
  "Sets every value of this draft back to the model package's default values. Nothing is saved as a version until Save and build.";
export const CENTRE_SENTENCE = 'Drag the centre on the map or type it.';
export const RADIUS_SENTENCE =
  'From 1 to 5 km. A larger zone has more hubs and takes longer to build.';
export const RULES_HEADING = 'Rules checked before saving';
export const NEW_INSTANCE_ACTION = '+ New city instance';
export const RULE_NOT_MET = 'One rule is not met.';

/** 2 for `geneva-3km.v2`; null for an id that has no version number. */
export function versionNumberOf(versionId: string): number | null {
  const match = /\.v([1-9][0-9]*)$/.exec(versionId);
  return match?.[1] === undefined ? null : Number(match[1]);
}

export function copyOption(name: string, number: number): string {
  return `A copy of ${name} ${versionTag(number)}`;
}

export function draftHeading(name: string): string {
  return `${name} · new version (draft)`;
}

/** "Draft saved · 10:42": the browser's time of the last answer. */
export function draftSaved(time: Date): string {
  const two = (n: number) => String(n).padStart(2, '0');
  return `Draft saved · ${two(time.getHours())}:${two(time.getMinutes())}`;
}

export function oneDraftMessage(basedNumber: number, createdAt: Date): string {
  return `This instance already has a draft, started from ${versionTag(basedNumber)} on ${formatInstantDay(createdAt).replace(/ \d{4}$/, '')}. Continue it, or discard it first.`;
}

export function discardQuestion(basedNumber: number | null): string {
  return basedNumber === null
    ? 'Discard this draft? Its values are removed.'
    : `Discard this draft? Its values are removed; ${versionTag(basedNumber)} stays as it is.`;
}

export function primaryLabel(draftNumber: number): string {
  return draftNumber === 1 ? 'Save as v1 and build' : 'Save and build';
}

// ---- parameters -----------------------------------------------------------------------------

export const PARAMETER_LABELS: Readonly<Record<ParameterName, string>> = {
  center_lat: 'Centre latitude',
  center_lon: 'Centre longitude',
  radius_m: 'Radius',
  clustering_threshold_m: 'Grouping distance',
  clustering_buffer_m: 'Hub outline margin',
  min_od_distance_m: 'Minimum trip distance',
  min_demand: 'Travellers per hub pair, lowest',
  max_demand: 'Travellers per hub pair, highest',
  fixed_capacity: 'Docks per station',
  min_inventory_pct: 'Bikes at 08:00, lowest',
  max_inventory_pct: 'Bikes at 08:00, highest',
  min_park_time_min: 'Car parking search, lowest',
  max_park_time_min: 'Car parking search, highest',
  seed: 'Random seed',
};

/** Round away the float noise of a unit conversion. */
const tidy = (n: number) => Math.round(n * 1e6) / 1e6;

const isInventory = (param: ParameterName) =>
  param === 'min_inventory_pct' || param === 'max_inventory_pct';

/** The text an input shows: the radius in km with one decimal, the bike shares in percent. */
export function inputText(param: ParameterName, value: number): string {
  if (param === 'radius_m') return (value / 1000).toFixed(1);
  if (isInventory(param)) return String(tidy(value * 100));
  return String(value);
}

/** The value a typed text stands for, in the API's unit; null when it is not a number. */
export function parseInput(param: ParameterName, text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === '') return null;
  const typed = Number(trimmed);
  if (!Number.isFinite(typed)) return null;
  if (param === 'radius_m') return tidy(typed * 1000);
  if (isInventory(param)) return tidy(typed / 100);
  return typed;
}

/** A value as the form and the table of changes write it, with its unit. */
export function valueText(param: ParameterName, value: number): string {
  switch (param) {
    case 'radius_m':
      return `${(value / 1000).toFixed(1)} km`;
    case 'clustering_threshold_m':
    case 'clustering_buffer_m':
    case 'min_od_distance_m':
      return `${String(value)} m`;
    case 'min_inventory_pct':
    case 'max_inventory_pct':
      return `${String(tidy(value * 100))} %`;
    case 'min_park_time_min':
    case 'max_park_time_min':
      return `${String(value)} min`;
    default:
      return String(value);
  }
}

export interface DraftInput {
  readonly param: ParameterName;
  readonly label: string;
  readonly unit: string | null;
}

/** The inputs of each field of the saved view, found by the field's package names. */
export const FIELD_INPUTS: Readonly<Record<string, readonly DraftInput[]>> = {
  'center_lat · center_lon': [
    { param: 'center_lat', label: 'Centre latitude', unit: null },
    { param: 'center_lon', label: 'Centre longitude', unit: null },
  ],
  radius_m: [{ param: 'radius_m', label: 'Radius', unit: 'km' }],
  clustering_threshold_m: [
    { param: 'clustering_threshold_m', label: 'Grouping distance', unit: 'm' },
  ],
  clustering_buffer_m: [{ param: 'clustering_buffer_m', label: 'Hub outline margin', unit: 'm' }],
  min_od_distance_m: [{ param: 'min_od_distance_m', label: 'Minimum trip distance', unit: 'm' }],
  'min_demand · max_demand': [
    { param: 'min_demand', label: 'Travellers per hub pair, lowest', unit: null },
    { param: 'max_demand', label: 'Travellers per hub pair, highest', unit: null },
  ],
  fixed_capacity: [{ param: 'fixed_capacity', label: 'Docks per station', unit: null }],
  'min_inventory_pct · max_inventory_pct': [
    { param: 'min_inventory_pct', label: 'Bikes at 08:00, lowest', unit: '% of docks' },
    { param: 'max_inventory_pct', label: 'Bikes at 08:00, highest', unit: '% of docks' },
  ],
  'min_park_time_min · max_park_time_min': [
    { param: 'min_park_time_min', label: 'Car parking search, lowest', unit: 'min' },
    { param: 'max_park_time_min', label: 'Car parking search, highest', unit: 'min' },
  ],
  seed: [{ param: 'seed', label: 'Random seed', unit: null }],
};

/** The wire names of a version's parameters, with the values of `parameters`. */
export function parametersAsWire(
  parameters: InstanceParameters,
): Readonly<Record<ParameterName, number>> {
  const wire = {} as Record<ParameterName, number>;
  for (const [name, key] of Object.entries(PARAMETER_KEYS) as [
    ParameterName,
    keyof InstanceParameters,
  ][]) {
    wire[name] = parameters[key];
  }
  return wire;
}

// ---- rules ----------------------------------------------------------------------------------

export const RULE_TEXTS: Readonly<Record<string, string>> = {
  min_trip_distance_above_grouping: 'Minimum trip distance is greater than the grouping distance',
  radius_1_to_5_km: 'Radius between 1 and 5 km',
  travellers_lowest_not_above_highest: 'Travellers per hub pair: lowest is not above highest',
  bikes_0_to_100_pct: 'Bikes at 08:00: between 0 and 100 % of docks',
  centre_inside_area: 'The centre is inside the area of the Geneva data',
  routing_date_inside_timetable: 'Routing date inside the timetable',
  docks_at_least_1: 'Docks per station: at least 1',
  bikes_and_parking_lowest_not_above_highest:
    'Bikes at 08:00 and car parking search: lowest is not above highest',
  seed_whole_number: 'Random seed: a whole number, 0 or more',
  grouping_above_0_margin_0_or_more: 'Grouping distance above 0; outline margin 0 or more',
};

export const ROUTING_DATE_RULE = 'routing_date_inside_timetable';

/** A rule's value with its unit: metres, minutes, travellers, docks, shares as percent, the radius in km. */
export function ruleValueText(value: RuleValue): string {
  if (typeof value.value === 'string') return value.value;
  const n = value.value;
  if (value.name === 'radius') return `${(n / 1000).toFixed(1)} km`;
  switch (value.unit) {
    case 'm':
    case 'min':
    case 'travellers':
    case 'docks':
      return `${String(n)} ${value.unit}`;
    case 'share of docks':
      return `${String(tidy(n * 100))} %`;
    default:
      return String(n);
  }
}

/** The rule's text; a failed rule adds the two values it compared. */
export function ruleLine(result: RuleResult): string {
  const text = RULE_TEXTS[result.rule] ?? result.rule;
  if (result.passed) return text;
  const [a, b] = result.values;
  return `${text}: now ${ruleValueText(a)} against ${ruleValueText(b)}`;
}

/** The parameters whose fields turn red when this rule fails. */
export function ruleFields(result: RuleResult): readonly ParameterName[] {
  switch (result.rule) {
    case 'min_trip_distance_above_grouping':
      return ['min_od_distance_m', 'clustering_threshold_m'];
    case 'radius_1_to_5_km':
      return ['radius_m'];
    case 'travellers_lowest_not_above_highest':
      return ['min_demand', 'max_demand'];
    case 'bikes_0_to_100_pct':
      return ['min_inventory_pct', 'max_inventory_pct'];
    case 'centre_inside_area':
      return ['center_lat', 'center_lon'];
    case 'docks_at_least_1':
      return ['fixed_capacity'];
    case 'bikes_and_parking_lowest_not_above_highest':
      return result.values[0].name === 'lowest parking time'
        ? ['min_park_time_min', 'max_park_time_min']
        : ['min_inventory_pct', 'max_inventory_pct'];
    case 'seed_whole_number':
      return ['seed'];
    case 'grouping_above_0_margin_0_or_more':
      return ['clustering_threshold_m', 'clustering_buffer_m'];
    default:
      return [];
  }
}

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
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
];

/** "Monday 10 March 2025" from `YYYY-MM-DD`. */
function longDate(date: string): string {
  const [year = 0, month = 1, day = 1] = date.slice(0, 10).split('-').map(Number);
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()] ?? '';
  return `${weekday} ${String(day)} ${LONG_MONTHS[month - 1] ?? ''} ${String(year)}`;
}

/** The routing-date rule as the Periods line writes it; a failed one names both values. */
export function routingDateLine(
  result: RuleResult | undefined,
  period: InstancePeriod,
  timetable: { readonly from: string; readonly to: string },
): { readonly passed: boolean; readonly text: string } {
  const passed = result?.passed ?? true;
  const rule = RULE_TEXTS[ROUTING_DATE_RULE] ?? '';
  const range = `${formatDate(timetable.from)} – ${formatDate(timetable.to)}`;
  const text = passed
    ? `${rule}: ${longDate(period.routingDate)} is within ${range}`
    : `${rule}: now ${longDate(period.routingDate)} against ${range}`;
  return { passed, text };
}

// ---- save box, changes, banners -------------------------------------------------------------

const STEP_NAMES = ['Area', 'Hubs', 'Routes', 'Travellers and bikes'] as const;

function keptClause(kept: readonly number[]): string | null {
  if (kept.length === 0) return null;
  const [only] = kept;
  if (kept.length === 1 && only !== undefined) return `step ${String(only)} is kept`;
  const head = kept.slice(0, -1).map(String).join(', ');
  return `steps ${head} and ${String(kept.at(-1))} are kept`;
}

export function saveBox(
  name: string,
  draftNumber: number,
  basedNumber: number,
  pricingVersions: number,
  plan: BuildPlan,
): string {
  const rebuilt = plan.steps
    .filter((step) => step.action === 'rebuilt')
    .map((step) => `${String(step.number)} ${STEP_NAMES[step.number - 1] ?? step.step}`);
  const kept = keptClause(
    plan.steps.filter((step) => step.action === 'kept').map((step) => step.number),
  );
  const pricing =
    pricingVersions === 1 ? '1 pricing version' : `${String(pricingVersions)} pricing versions`;
  return (
    `Saving creates ${name} ${versionTag(draftNumber)}. ${versionTag(basedNumber)} and its ${pricing} stay as they are. ` +
    `Will rebuild: ${rebuilt.length === 0 ? 'none' : rebuilt.join(', ')}${kept === null ? '' : `; ${kept}`}.`
  );
}

/** "Last build of this size: about 9 min.", when every rebuilt step has a measured duration. */
export function measuredSentence(plan: BuildPlan): string | null {
  const rebuilt = plan.steps.filter((step) => step.action === 'rebuilt');
  if (rebuilt.length === 0) return null;
  let seconds = 0;
  for (const step of rebuilt) {
    if (step.lastDurationS === null) return null;
    seconds += step.lastDurationS;
  }
  return `Last build of this size: about ${String(Math.max(1, Math.round(seconds / 60)))} min.`;
}

export interface ChangeRow {
  readonly name: string;
  readonly before: string;
  readonly after: string;
}

export function changeRows(changes: readonly ParameterChange[]): ChangeRow[] {
  return changes.map((change) => ({
    name: PARAMETER_LABELS[change.parameter],
    before: valueText(change.parameter, change.before),
    after: valueText(change.parameter, change.after),
  }));
}

/** One sentence per cause that is not a parameter, in a fixed order. */
export function causeRows(
  plan: BuildPlan,
  basedNumber: number,
  bikeStationsFetchedAt: string,
): string[] {
  const kinds = new Set(plan.steps.flatMap((step) => step.causes.map((cause) => cause.kind)));
  const based = versionTag(basedNumber);
  const rows: string[] = [];
  if (kinds.has('package')) {
    rows.push(`The pricing model's package changed since ${based}: every step is rebuilt.`);
  }
  if (kinds.has('trip_planner_graph')) {
    rows.push(
      `The trip planner's graph changed since ${based}: Routes and the steps after it are rebuilt.`,
    );
  }
  if (kinds.has('city_data')) {
    rows.push(
      `New city data (bike stations fetched ${formatInstantDay(bikeStationsFetchedAt)}): every step is rebuilt.`,
    );
  }
  return rows;
}

export const BANNER_TEXTS: Readonly<Partial<Record<ComponentName, string>>> = {
  runner: 'New builds are off: the runner is not running. Queued runs wait.',
  tripPlanner:
    'This change rebuilds the routes, and the trip planner is not reachable. A change to the travellers and bikes only can still be built.',
  cityData: NO_CITY_DATA,
  package: "New builds are off: the pricing model's package does not load on this machine.",
};

/** One sentence per reason that stops the build; a component without a text gives the API's own. */
export function bannerSentences(plan: BuildPlan): string[] {
  return plan.verdict.reasons.map(
    (reason) => BANNER_TEXTS[reason.component] ?? `New builds are off: ${reason.reason}`,
  );
}

export interface PrimaryState {
  readonly disabled: boolean;
  readonly note: string | null;
}

/** Why the primary is disabled, or that it is not. A broken rule comes first, then "nothing differs", then a banner. */
export function primaryState(input: {
  readonly rules: readonly RuleResult[];
  readonly edit: boolean;
  readonly basedNumber: number | null;
  readonly plan: BuildPlan;
  readonly changes: readonly ParameterChange[];
}): PrimaryState {
  if (input.rules.some((rule) => !rule.passed)) return { disabled: true, note: RULE_NOT_MET };
  const parameterOnly = input.plan.steps.every((step) =>
    step.causes.every((cause) => cause.kind === 'parameter'),
  );
  if (input.edit && input.basedNumber !== null && input.changes.length === 0 && parameterOnly) {
    return { disabled: true, note: `Nothing differs from ${versionTag(input.basedNumber)} yet.` };
  }
  const [first] = bannerSentences(input.plan);
  if (first !== undefined) return { disabled: true, note: first };
  return { disabled: false, note: null };
}
