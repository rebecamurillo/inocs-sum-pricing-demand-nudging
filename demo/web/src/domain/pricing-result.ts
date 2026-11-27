/** The stored result of a pricing version, as the Lab's L-3 reads it: only what that screen shows. */

export type ResultSource =
  'model' | 'package_summary' | 'input' | 'trip_planner' | 'derived' | 'simulation';

export interface ResultNumber {
  readonly value: number;
  readonly unit: string;
  readonly source: ResultSource;
  readonly group: 'headline' | 'advanced';
}

export type ModeKey = 'car' | 'ptOnly' | 'ptBike';
export type ModeCounts = Readonly<Record<ModeKey, number>>;

export interface SimulationOutcome {
  readonly ruleId: string;
  readonly ruleVersion: number;
  readonly ruleCurrent: boolean;
  readonly travellers: ModeCounts;
  readonly displaced: number;
  readonly unserved: number;
}

export const GOAL_NAMES = [
  'ridership',
  'revenue',
  'cost',
  'profit',
  'mean_bike_price',
  'stations_empty',
  'stations_full',
] as const;
export type GoalName = (typeof GOAL_NAMES)[number];

/** One goal: the model's own value, the two simulated values and the change between them. */
export interface GoalComparison {
  readonly model: ResultNumber | null;
  readonly modelPrices: ResultNumber | null;
  readonly flat: ResultNumber | null;
  readonly change: ResultNumber | null;
}

export const HEADLINE_NAMES = [
  'bike_price_min',
  'bike_price_max',
  'mean_bike_price',
  'profit',
  'revenue',
  'cost',
  'ridership',
  'rides_under_cost',
  'rides_under_cost_share',
  'stations_empty_end',
  'stations_full_end',
  'stations_empty_start',
  'stations_full_start',
] as const;
export type HeadlineName = (typeof HEADLINE_NAMES)[number];

export interface PricingResult {
  readonly pricingVersionId: string;
  readonly periodId: string;
  readonly simulations: {
    /** The traveller simulation with the pricing model's prices. */
    readonly modelPrices: SimulationOutcome;
    /** The same travellers with the flat bike price. */
    readonly flat: SimulationOutcome;
  };
  /** The pricing model's own split of the travellers; null when one mode is missing. */
  readonly modelSplit: ModeCounts | null;
  readonly goals: Readonly<Record<GoalName, GoalComparison>>;
  readonly headline: Readonly<Partial<Record<HeadlineName, ResultNumber>>>;
}

export interface ModeInfo {
  readonly key: ModeKey;
  readonly label: string;
  readonly colour: string;
  readonly icon: string;
}

/** The three modes in the order every bar and legend shows them (UX-SPEC § Mode colours). */
export const MODES: readonly ModeInfo[] = [
  { key: 'car', label: 'Car', colour: '#eb6834', icon: '🚗' },
  { key: 'ptOnly', label: 'Public transport', colour: '#2a78d6', icon: '🚋' },
  { key: 'ptBike', label: 'Public transport + shared bike', colour: '#1baf7a', icon: '🚋+🚲' },
];

export function sumModes(counts: ModeCounts): number {
  return counts.car + counts.ptOnly + counts.ptBike;
}

/** The period's travellers: every mode plus those left with no option (the simulation's own check). */
export function periodTravellers(simulation: SimulationOutcome): number {
  return sumModes(simulation.travellers) + simulation.unserved;
}
