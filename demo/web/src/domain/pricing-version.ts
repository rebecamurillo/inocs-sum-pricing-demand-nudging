/** A pricing version as the Lab reads it: the eight goals of one built instance version. */

export const PRICING_GOAL_NAMES = [
  'cost_bike_chf',
  'lowest_price_chf',
  'ridership_weight',
  'station_balance_weight',
  'pt_fare_chf',
  'car_parking_fee_chf',
  'max_displayed_options',
  'flat_price_per_ride_chf',
] as const;

export type PricingGoalName = (typeof PRICING_GOAL_NAMES)[number];
export type PricingGoals = Readonly<Record<PricingGoalName, number>>;
export type PricingChanges = Partial<Record<PricingGoalName, number>> & { name?: string };

export type PricingVersionState =
  'draft' | 'queued' | 'running' | 'failed' | 'cancelled' | 'result';

export interface PricingRule {
  readonly rule: string;
  readonly field: string;
  readonly passed: boolean;
  /** Names the value, as a failure reads on the form. */
  readonly message: string;
}

export interface PricingPeriod {
  readonly id: string;
  readonly key: string;
  readonly label: string;
}

export interface PricingVersion {
  /** `{instance version}.{letter}`. */
  readonly id: string;
  readonly instanceVersionId: string;
  readonly letter: string;
  readonly name: string;
  readonly status: 'draft' | 'sealed';
  readonly state: PricingVersionState;
  /** The version this one was duplicated from; null when it is based on none. */
  readonly basedOnId: string | null;
  /** The version's latest pricing run; null for a draft. */
  readonly runId: string | null;
  /** The sealed version whose fare, parking fee, options and flat price this draft kept. */
  readonly keptFrom: { readonly id: string; readonly letter: string } | null;
  readonly goals: PricingGoals;
  /** The periods the version prices, as the API keys them (`mon-08`). */
  readonly periods: readonly PricingPeriod[];
  readonly rules: readonly PricingRule[];
  /** Seconds the pricing model last took on this data set and radius; null when it has not run. */
  readonly lastDurationS: number | null;
}

export function pricingVersionId(instanceVersionId: string, letter: string): string {
  return `${instanceVersionId}.${letter}`;
}

/** A draft still named `Version {letter}` has not been named by the visitor. */
export function isDefaultName(version: Pick<PricingVersion, 'name' | 'letter'>): boolean {
  return version.name === `Version ${version.letter}`;
}
