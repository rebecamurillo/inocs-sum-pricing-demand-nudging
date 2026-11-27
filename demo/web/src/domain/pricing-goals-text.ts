/** The wording of L-2 (pricing goals) and its details panel, and the figures it computes from the
 * goals. Wording belongs here, not in JSX. */
import { STORED_STAY } from './draft-text';
import { formatDuration } from './run-text';
import { groupThousands } from './l1-text';
import { SIMULATING } from './older-rule-text';
import { ordinal } from './ordinal';
import {
  isDefaultName,
  type PricingGoalName,
  type PricingGoals,
  type PricingRule,
  type PricingVersion,
  type PricingVersionState,
} from './pricing-version';
import type { SystemStatus } from './system-status';

export const PRICING_BRIEF = 'Pricing version · pipeline step 5';
export const PRICING_SENTENCE =
  'The model sets a bike price for each bike option it offers on each hub pair, for the period. These values say what it should look for.';
export const PRICING_HEADING = 'Pricing goals';
export const NAME_LABEL = 'Name';
export const NAME_PLACEHOLDER = 'New version';
export const NEW_PRICING_VERSION = '+ New pricing version';
export const RUN_LABEL = 'Run the pricing model · 08:00–09:00';
export const RULES_BEFORE_RUNNING = 'Rules checked before running';
export const RULE_NOT_MET = 'One rule is not met.';
export const EXPLAIN_LABEL = 'ⓘ Explain';
export const NEXT_VERSION = 'Next version';
export const NEXT_VERSION_TAG = 'NEXT VERSION';
export const DETAILS_HEADING = 'How the model reads these values';
export const SEALED_NOTE = 'This version was run. Its goals cannot change.';

// ---- step 1: the period ---------------------------------------------------------------------

export const PERIOD_HOURS: readonly string[] = Array.from({ length: 17 }, (_, at) =>
  String(at + 6).padStart(2, '0'),
);
export const SELECTED_HOUR = '08';
export const PERIOD_SENTENCE =
  '08:00–09:00 · 1 period, 1 run. The prices the model sets hold for the whole period. The other hours open in the next version, one run per period.';

export function hourLabel(hour: string): string {
  const next = String(Number(hour) + 1).padStart(2, '0');
  return `${hour}:00 to ${next}:00`;
}

// ---- steps and fields -----------------------------------------------------------------------

export interface Step {
  readonly number: number;
  readonly title: string;
  readonly unit: string | null;
}

export const STEP_1: Step = { number: 1, title: 'Period to price', unit: 'Monday, by hour' };
export const STEP_2: Step = {
  number: 2,
  title: 'Cost and lowest price',
  unit: 'CHF per bike ride',
};
export const STEP_3: Step = {
  number: 3,
  title: 'What the model favours',
  unit: 'weights, against profit = 1',
};

export function step4Heading(keptFrom: PricingVersion['keptFrom']): string {
  return keptFrom === null ? 'Default values' : `Kept from Version ${keptFrom.letter}`;
}

export interface GoalField {
  readonly name: PricingGoalName;
  /** The plain name, with its unit when the unit is part of it. */
  readonly label: string;
  readonly unit: string | null;
  /** The package's name for it; null for the flat price, which the solver does not read. */
  readonly packageName: string | null;
  /** Digits kept at least: money 2, weights 1, a count 0. */
  readonly digits: number;
  readonly sentence: (goals: PricingGoals) => string;
}

const chf = (value: number): string => value.toFixed(2);

export const COST_FIELD: GoalField = {
  name: 'cost_bike_chf',
  label: 'Cost of one ride for the operator',
  unit: 'CHF',
  packageName: 'cost_bike',
  digits: 2,
  sentence: () =>
    'What one bike ride costs to operate. The model subtracts it from the price of every ride.',
};
export const LOWEST_FIELD: GoalField = {
  name: 'lowest_price_chf',
  label: 'Lowest price of a ride',
  unit: 'CHF',
  packageName: 'P_bar',
  digits: 2,
  sentence: () => 'The model never prices an offered bike ride under this.',
};
export const RIDERSHIP_FIELD: GoalField = {
  name: 'ridership_weight',
  label: 'Ridership',
  unit: null,
  packageName: 'ridership_weight',
  digits: 1,
  sentence: (goals) =>
    `One more traveller on public transport + bike counts like CHF ${chf(goals.ridership_weight)} of profit.`,
};
export const BALANCE_FIELD: GoalField = {
  name: 'station_balance_weight',
  label: 'Station balance',
  unit: null,
  packageName: 'theta',
  digits: 1,
  sentence: (goals) =>
    `A ride from a full station to an empty one counts like up to CHF ${chf(goals.station_balance_weight)} of profit; the opposite ride counts against as much.`,
};
export const PROFIT_LABEL = 'Profit';
export const PROFIT_FIXED = '1 · fixed';
export const PROFIT_SENTENCE = 'Price minus cost, on every bike ride.';

export const KEPT_FIELDS: readonly GoalField[] = [
  {
    name: 'pt_fare_chf',
    label: 'Public transport fare, CHF',
    unit: null,
    packageName: 'pt_price',
    digits: 2,
    sentence: () =>
      'Price of a public transport trip, added to the bike price on combined trips. Also used by the traveller simulation.',
  },
  {
    name: 'car_parking_fee_chf',
    label: 'Car parking fee, CHF',
    unit: null,
    packageName: 'parking_fee',
    digits: 2,
    sentence: () => 'Cost added to every car trip. Also used by the traveller simulation.',
  },
  {
    name: 'max_displayed_options',
    label: 'Options shown per hub pair',
    unit: null,
    packageName: 'max_displayed_alternatives',
    digits: 0,
    sentence: () =>
      'The most options the pricing model may offer a traveller on one hub pair; the model chooses which ones.',
  },
  {
    name: 'flat_price_per_ride_chf',
    label: 'Flat price for the comparison, CHF per ride',
    unit: null,
    packageName: null,
    digits: 2,
    sentence: () =>
      "Not used by the pricing model. After the run, the same travellers are simulated twice: with the model's prices and with this price on every bike ride.",
  },
];

export const ALL_FIELDS: readonly GoalField[] = [
  COST_FIELD,
  LOWEST_FIELD,
  RIDERSHIP_FIELD,
  BALANCE_FIELD,
  ...KEPT_FIELDS,
];

/** A value as the input shows it: at least the field's digits, more when the value has more. */
export function goalText(field: GoalField, value: number): string {
  const decimals = String(value).split('.')[1]?.length ?? 0;
  return value.toFixed(Math.max(decimals, field.digits));
}

/** What the visitor typed as a number; null while it is not one (the draft keeps the last number). */
export function parseGoalInput(text: string): number | null {
  const trimmed = text.trim().replace(',', '.');
  if (trimmed === '') return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

// ---- step 2: the cost message ---------------------------------------------------------------

export type CostTone = 'covers' | 'break-even' | 'incentive';

export interface CostMessage {
  readonly tone: CostTone;
  readonly lead: string;
  readonly rest: string;
  readonly text: string;
}

function message(tone: CostTone, lead: string, rest: string): CostMessage {
  return { tone, lead, rest, text: `${lead} ${rest}` };
}

/** The one message by the difference between the lowest price and the cost. */
export function costMessage(cost: number, lowest: number): CostMessage {
  const margin = Math.round((lowest - cost) * 1e6) / 1e6;
  if (margin > 0) {
    return message(
      'covers',
      'Every ride covers its cost.',
      `At the lowest price the operator still earns CHF ${chf(margin)} on a ride.`,
    );
  }
  if (margin === 0) {
    return message(
      'break-even',
      'Break-even at the lowest price.',
      'The lowest price equals the cost: no ride is sold at a loss, and the cheapest rides bring no profit.',
    );
  }
  return message(
    'incentive',
    'Incentive: the lowest price is under the cost.',
    `On a ride sold at CHF ${chf(lowest)} the operator loses CHF ${chf(-margin)}. The model may do so where a new rider or a better-placed bike is worth more than the loss.`,
  );
}

// ---- step 3: the weights --------------------------------------------------------------------

export interface WeightBar {
  readonly label: string;
  readonly value: number;
  /** 0 to 1 of the one scale all three bars share. */
  readonly share: number;
}

/** Profit (1), ridership and station balance, each against the largest of 1 and the two weights. */
export function goalBars(goals: PricingGoals): readonly WeightBar[] {
  const scale = Math.max(1, goals.ridership_weight, goals.station_balance_weight);
  const bar = (label: string, value: number): WeightBar => ({
    label,
    value,
    share: Math.min(1, Math.max(0, value / scale)),
  });
  return [
    bar(PROFIT_LABEL, 1),
    bar(RIDERSHIP_FIELD.label, goals.ridership_weight),
    bar(BALANCE_FIELD.label, goals.station_balance_weight),
  ];
}

/** Profit, ridership and station balance by value, highest first; a tie keeps this order. */
function ranked<T extends { readonly value: number }>(entries: readonly T[]): T[] {
  return [...entries].sort((a, b) => b.value - a.value);
}

export function rankingLine(goals: PricingGoals): string {
  const order = ranked([
    { label: PROFIT_LABEL, value: 1 },
    { label: RIDERSHIP_FIELD.label, value: goals.ridership_weight },
    { label: BALANCE_FIELD.label, value: goals.station_balance_weight },
  ]);
  return `The model favours, in this order: ${order
    .map((entry, at) => `${String(at + 1)} ${entry.label}`)
    .join(' · ')}`;
}

// ---- the example ride (details panel, tab 3) ------------------------------------------------

export const EXAMPLE_PRICE = 1.4;
export const EXAMPLE_BALANCE_EFFECT = 0.4;

export interface ExamplePart {
  readonly label: string;
  readonly value: number;
  /** -1 to 1 of the largest absolute part: negative bars are drawn left of zero. */
  readonly share: number;
  readonly amount: string;
}

export interface ExampleRide {
  readonly parts: readonly ExamplePart[];
  readonly total: number;
  readonly totalText: string;
  readonly sentence: string;
}

/** A signed amount in CHF with a real minus: `0.80`, `−0.60`. */
export function signedAmount(value: number): string {
  return value < 0 ? `−${chf(-value)}` : chf(value);
}

const rounded = (value: number): number => Math.round(value * 1e6) / 1e6;

export function exampleRide(goals: PricingGoals): ExampleRide {
  const values = [
    {
      label: 'Profit: price − cost',
      name: 'profit',
      value: rounded(EXAMPLE_PRICE - goals.cost_bike_chf),
    },
    { label: 'Ridership: one more rider', name: 'ridership', value: goals.ridership_weight },
    {
      label: 'Station balance: weight × 0.40',
      name: 'station balance',
      value: rounded(goals.station_balance_weight * EXAMPLE_BALANCE_EFFECT),
    },
  ];
  const widest = Math.max(...values.map((part) => Math.abs(part.value)), Number.EPSILON);
  const parts = values.map((part) => ({
    label: part.label,
    value: part.value,
    share: part.value / widest,
    amount: signedAmount(part.value),
  }));
  const total = rounded(values.reduce((sum, part) => sum + part.value, 0));
  const [first, second, third] = ranked(values);
  const sentence =
    first === undefined || second === undefined || third === undefined
      ? ''
      : `On this ride, ${first.name} counts most (CHF ${signedAmount(first.value)}), then ${second.name} (CHF ${signedAmount(second.value)}), then ${third.name} (CHF ${signedAmount(third.value)}).`;
  return { parts, total, totalText: signedAmount(total), sentence };
}

// ---- the number line (details panel, tab 2) -------------------------------------------------

export interface NumberLine {
  readonly max: number;
  readonly ticks: readonly { readonly at: number; readonly label: string }[];
  /** Positions in percent of the line. */
  readonly costAt: number;
  readonly lowestAt: number;
  /** The span of rides sold under their cost, null when the lowest price is not under the cost. */
  readonly loss: { readonly from: number; readonly to: number } | null;
  readonly caption: string;
}

export function numberLine(cost: number, lowest: number): NumberLine {
  const max = Math.max(2, Math.ceil(Math.max(cost, lowest) * 2) / 2);
  const at = (value: number) => Math.min(100, Math.max(0, (value / max) * 100));
  const ticks = Array.from({ length: Math.round(max * 2) + 1 }, (_, index) => {
    const value = index / 2;
    return { at: at(value), label: `${chf(value)}${value === max ? '+' : ''}` };
  });
  const under = lowest < cost;
  return {
    max,
    ticks,
    costAt: at(cost),
    lowestAt: at(lowest),
    loss: under ? { from: at(lowest), to: at(cost) } : null,
    caption: `CHF per bike ride. Green: prices the model may set.${under ? ' Hatched: rides sold under their cost.' : ''}`,
  };
}

// ---- the details panel ----------------------------------------------------------------------

export type ExplainTopic = 'period' | 'price' | 'weights';

export const EXPLAIN_TABS: readonly { topic: ExplainTopic; label: string }[] = [
  { topic: 'period', label: '1 Period' },
  { topic: 'price', label: '2 Cost and price' },
  { topic: 'weights', label: '3 Weights' },
];

export const PERIOD_TEXTS = {
  heading: 'One period in this version',
  prices:
    'The model sets a price for each bike option it offers, and those prices hold for the whole period: Monday 08:00–09:00.',
  instance:
    "The city instance holds what the period needs: the routes of that hour's timetable, its travellers and the bikes at each station at 08:00.",
  next: 'Several periods: one run per period, each starting with the bikes the period before left at the stations. The hours shown in grey open then.',
};

export const PRICE_TEXTS = {
  lineHeading: 'Lowest price against cost',
  profitHeading: 'Profit is not typed in',
  profit: 'It is the price the model sets minus the cost of the ride.',
  highestHeading: 'The highest price is not typed in either',
  highest:
    'On each trip the model stops at the price where the bike option loses against the car or public transport.',
  costMark: (cost: number) => `cost ${chf(cost)}`,
  lowestMark: (lowest: number) => `lowest price ${chf(lowest)}`,
};

export const WEIGHT_TEXTS = {
  heading: 'What one bike ride is worth to the model',
  example:
    'Example: a ride sold at CHF 1.40 that takes a bike from a station 70 % full to a station 30 % full.',
  total: 'Total',
  readingHeading: 'Reading a weight',
  reading:
    'Profit counts as 1. A weight of 1.5 on ridership means one more rider counts like CHF 1.50 of profit. A station balance weight above the ridership weight puts bikes where they are needed before new riders.',
};

export const SOURCE_LINE =
  "Read from the model's package, unmodified: it maximises ridership weight × riders + price × riders − cost × riders + balance weight × balance effect, counted on public transport + bike trips.";

// ---- this run, discard ---------------------------------------------------------------------

export function thisRunLine(
  instanceLabel: string,
  hubPairs: number | null,
  lastDurationS: number | null,
): readonly string[] {
  return [
    `This run: ${instanceLabel}`,
    ...(hubPairs === null ? [] : [`${groupThousands(hubPairs)} hub pairs with routes`]),
    '1 period · Monday 08:00–09:00',
    ...(lastDurationS === null
      ? []
      : [`Last run on this instance: ${formatDuration(lastDurationS)}`]),
  ];
}

export function discardQuestion(keptFrom: PricingVersion['keptFrom']): string {
  return keptFrom === null
    ? 'Discard this draft? Its values are removed.'
    : `Discard this draft? Its values are removed; Version ${keptFrom.letter} stays as it is.`;
}

// ---- the rules box --------------------------------------------------------------------------

export interface RuleLine {
  readonly key: string;
  readonly passed: boolean;
  readonly text: string;
}

const AMOUNTS_SUFFIX = '_zero_or_more';
const OPTIONS_RULE = 'options_shown_at_least_1';

/** "Every amount is 0 or more" and "Options shown per hub pair: at least 1"; a failure is the API's sentence naming its value. */
export function ruleLines(rules: readonly PricingRule[]): readonly RuleLine[] {
  const amounts = rules.filter((rule) => rule.rule.endsWith(AMOUNTS_SUFFIX));
  const options = rules.filter((rule) => rule.rule === OPTIONS_RULE);
  const lines: RuleLine[] = [];
  const failedAmounts = amounts.filter((rule) => !rule.passed);
  if (failedAmounts.length === 0) {
    lines.push({ key: 'amounts', passed: true, text: 'Every amount is 0 or more' });
  } else {
    lines.push(
      ...failedAmounts.map((rule) => ({ key: rule.rule, passed: false, text: rule.message })),
    );
  }
  const failedOptions = options.filter((rule) => !rule.passed);
  if (failedOptions.length === 0) {
    lines.push({ key: OPTIONS_RULE, passed: true, text: 'Options shown per hub pair: at least 1' });
  } else {
    lines.push(
      ...failedOptions.map((rule) => ({ key: rule.rule, passed: false, text: rule.message })),
    );
  }
  return lines;
}

/** The goals whose inputs turn red: the fields of the rules that failed. */
export function failedFields(rules: readonly PricingRule[]): ReadonlySet<string> {
  return new Set(rules.filter((rule) => !rule.passed).map((rule) => rule.field));
}

// ---- banner and primary ---------------------------------------------------------------------

const BANNER_TEXTS = {
  solverUnavailable: 'Pricing runs are off: no Gurobi licence was found on this machine.',
  solverLimited:
    "Pricing runs are off: this machine has Gurobi's size-limited licence, which cannot solve a city instance.",
  package: "Pricing runs are off: the pricing model's package does not load on this machine.",
  runner: 'Pricing runs are off: the runner is not running. Queued runs wait.',
};

/** One sentence per reason that stops a pricing run; the trip planner is not a reason (§ 10.1). */
export function pricingBannerSentences(status: SystemStatus | undefined): readonly string[] {
  if (status === undefined) return [];
  return status.canRunPricing.reasons.map((reason) => {
    switch (reason.component) {
      case 'solver': {
        const solver = status.components.find((component) => component.name === 'solver');
        return solver?.state === 'limited'
          ? BANNER_TEXTS.solverLimited
          : BANNER_TEXTS.solverUnavailable;
      }
      case 'package':
        return BANNER_TEXTS.package;
      case 'runner':
        return BANNER_TEXTS.runner;
      default:
        return `Pricing runs are off: ${reason.reason}`;
    }
  });
}

export function bannerWithStoredResults(sentence: string): string {
  return `${sentence} ${STORED_STAY}`;
}

export interface PrimaryState {
  readonly disabled: boolean;
  readonly note: string | null;
}

/** Why "Run the pricing model" is disabled, or that it is not: a broken rule first, then a banner. */
export function pricingPrimaryState(
  rules: readonly PricingRule[],
  status: SystemStatus | undefined,
): PrimaryState {
  if (rules.some((rule) => !rule.passed)) return { disabled: true, note: RULE_NOT_MET };
  const [first] = pricingBannerSentences(status);
  if (first !== undefined) return { disabled: true, note: first };
  return { disabled: false, note: null };
}

// ---- the menu -------------------------------------------------------------------------------

/**
 * The state a menu row shows; `queuedPlace` counts the running run as 1st. A version with a
 * result whose simulation is queued or running again shows `● simulating`.
 */
export function pricingMenuState(
  state: PricingVersionState,
  queuedPlace: number | null = null,
  simulating = false,
): string {
  switch (state) {
    case 'draft':
      return 'draft';
    case 'running':
      return '● running';
    case 'queued':
      return queuedPlace === null ? '◷ queued' : `◷ queued · ${ordinal(queuedPlace)}`;
    case 'failed':
      return '✕ failed';
    case 'cancelled':
      return 'cancelled';
    case 'result':
      return simulating ? SIMULATING : '✓ result';
  }
}

/** The name a row and the breadcrumb show: a draft still on its default name is "New version". */
export function pricingVersionName(version: PricingVersion): string {
  return version.status === 'draft' && isDefaultName(version) ? NAME_PLACEHOLDER : version.name;
}

/** The letter a menu row shows next to the name: only once sealed, and not twice in "Version A". */
export function pricingRowLetter(version: PricingVersion): string | null {
  return version.status === 'sealed' && !isDefaultName(version) ? version.letter : null;
}

export function pricingBreadcrumb(instanceName: string, number: number, name: string): string {
  return `${instanceName} v${String(number)} › Pricing versions › ${name}`;
}
